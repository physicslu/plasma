import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

async function loadManagerBff() {
  const source = await readFile(new URL("../app/api/manager/manager-bff.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
    },
  }).outputText;
  return await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
}

function withManagedEnvironment() {
  const snapshot = {
    mode: process.env.PLASMA_CONTROL_STATION_MODE,
    manager: process.env.PLASMA_MANAGER_API_URL,
    alias: process.env.PLASMA_MANAGER_PPU_ALIAS,
  };
  process.env.PLASMA_CONTROL_STATION_MODE = "managed";
  process.env.PLASMA_MANAGER_API_URL = "http://127.0.0.1:18180";
  process.env.PLASMA_MANAGER_PPU_ALIAS = "swpc-ppu";
  return () => {
    for (const [name, value] of [
      ["PLASMA_CONTROL_STATION_MODE", snapshot.mode],
      ["PLASMA_MANAGER_API_URL", snapshot.manager],
      ["PLASMA_MANAGER_PPU_ALIAS", snapshot.alias],
    ]) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  };
}

test("managed Engineering session keeps Manager routing authoritative and sanitizes upstream HTML 404", async () => {
  const { relayManagerPpuRequest } = await loadManagerBff();
  const restoreEnvironment = withManagedEnvironment();
  const originalFetch = globalThis.fetch;
  let observedUrl = "";
  let observedInit;

  globalThis.fetch = async (input, init) => {
    observedUrl = String(input);
    observedInit = init;
    return new Response("<html><h1>404 Not Found</h1></html>", {
      status: 404,
      headers: { "Content-Type": "text/html" },
    });
  };

  try {
    const request = new Request(
      "https://plasma-control-station-lab.onrender.com/api/manager/ppu/api/engineering/session",
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          Authorization: "Bearer browser-token",
          "Content-Type": "application/json",
          "Idempotency-Key": "engineering-session-1",
        },
        body: "{}",
      },
    );

    const response = await relayManagerPpuRequest(request, "/api/engineering/session");
    const payload = await response.json();

    assert.equal(response.status, 404);
    assert.match(response.headers.get("Content-Type") ?? "", /^application\/json\b/);
    assert.equal(payload.ok, false);
    assert.equal(payload.error.code, "managed_upstream_non_json");
    assert.equal(payload.error.upstream_status, 404);
    assert.equal(
      observedUrl,
      "http://127.0.0.1:18180/api/ppus/swpc-ppu/gateway/api/engineering/session",
    );
    assert.equal(observedInit.method, "POST");
    assert.equal(observedInit.headers.get("Authorization"), "Bearer browser-token");
    assert.equal(observedInit.headers.get("Idempotency-Key"), "engineering-session-1");
    assert.doesNotMatch(observedUrl, /ppu-lab\.open4th\.com/);
  } finally {
    globalThis.fetch = originalFetch;
    restoreEnvironment();
  }
});

test("managed PPU binary readback remains byte-for-byte pass-through", async () => {
  const { relayManagerPpuRequest } = await loadManagerBff();
  const restoreEnvironment = withManagedEnvironment();
  const originalFetch = globalThis.fetch;
  const bytes = Uint8Array.from([0, 1, 2, 3, 254, 255]);

  globalThis.fetch = async () =>
    new Response(bytes, {
      status: 200,
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": 'attachment; filename="readback.bin"',
      },
    });

  try {
    const request = new Request(
      "https://plasma-control-station-lab.onrender.com/api/manager/ppu/api/engineering/targets/fac-a/ppu-a/api/jobs/job-1/files/readback.bin",
    );
    const response = await relayManagerPpuRequest(
      request,
      "/api/engineering/targets/fac-a/ppu-a/api/jobs/job-1/files/readback.bin",
    );

    assert.equal(response.status, 200);
    assert.equal(response.headers.get("Content-Type"), "application/octet-stream");
    assert.equal(response.headers.get("Content-Disposition"), 'attachment; filename="readback.bin"');
    assert.deepEqual(new Uint8Array(await response.arrayBuffer()), bytes);
  } finally {
    globalThis.fetch = originalFetch;
    restoreEnvironment();
  }
});

test("managed PPU non-JSON success is promoted to a deterministic gateway-contract failure", async () => {
  const { relayManagerPpuRequest } = await loadManagerBff();
  const restoreEnvironment = withManagedEnvironment();
  const originalFetch = globalThis.fetch;

  globalThis.fetch = async () =>
    new Response("proxy landing page", {
      status: 200,
      headers: { "Content-Type": "text/plain" },
    });

  try {
    const response = await relayManagerPpuRequest(
      new Request("https://plasma-control-station-lab.onrender.com/api/manager/ppu/api/status"),
      "/api/status",
    );
    const payload = await response.json();

    assert.equal(response.status, 502);
    assert.equal(payload.error.code, "managed_upstream_non_json");
    assert.equal(payload.error.upstream_status, 200);
  } finally {
    globalThis.fetch = originalFetch;
    restoreEnvironment();
  }
});
