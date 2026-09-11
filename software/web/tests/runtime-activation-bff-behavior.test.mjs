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

test("runtime activation uses the exact Manager allowlisted path and forwards only security headers", async () => {
  const { relayManagerPpuAliasRequest } = await loadManagerBff();
  const previousMode = process.env.PLASMA_CONTROL_STATION_MODE;
  const previousManager = process.env.PLASMA_MANAGER_API_URL;
  process.env.PLASMA_CONTROL_STATION_MODE = "managed";
  process.env.PLASMA_MANAGER_API_URL = "http://127.0.0.1:18180";

  const originalFetch = globalThis.fetch;
  let observedUrl = "";
  let observedInit;
  globalThis.fetch = async (input, init) => {
    observedUrl = String(input);
    observedInit = init;
    return Response.json({ ok: true, runtime_activation: { state: "in_sync" } });
  };

  const revision = `sha256:${"a".repeat(64)}`;
  const body = JSON.stringify({
    action: "activate",
    expected_revision: revision,
    expected_ppu_id: "ppu-a",
  });
  try {
    const request = new Request("https://console.example/api/manager/registry/ppu-a/sites/activation", {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: "Bearer engineer-token",
        "Content-Type": "application/json",
        "Idempotency-Key": "runtime-activation-1",
        "X-Do-Not-Forward": "private-hop-header",
      },
      body,
    });

    const response = await relayManagerPpuAliasRequest(
      request,
      "ppu-a",
      "/api/settings/sites/activation",
    );
    assert.equal(response.status, 200);
    assert.equal(
      observedUrl,
      "http://127.0.0.1:18180/api/ppus/ppu-a/gateway/api/settings/sites/activation",
    );
    assert.equal(observedInit.method, "POST");
    assert.equal(observedInit.headers.get("Authorization"), "Bearer engineer-token");
    assert.equal(observedInit.headers.get("Idempotency-Key"), "runtime-activation-1");
    assert.equal(observedInit.headers.get("Content-Type"), "application/json");
    assert.equal(observedInit.headers.get("X-Do-Not-Forward"), null);
    assert.equal(new TextDecoder().decode(observedInit.body), body);
  } finally {
    globalThis.fetch = originalFetch;
    if (previousMode === undefined) delete process.env.PLASMA_CONTROL_STATION_MODE;
    else process.env.PLASMA_CONTROL_STATION_MODE = previousMode;
    if (previousManager === undefined) delete process.env.PLASMA_MANAGER_API_URL;
    else process.env.PLASMA_MANAGER_API_URL = previousManager;
  }
});
