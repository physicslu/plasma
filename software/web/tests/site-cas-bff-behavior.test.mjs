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

test("Site CAS If-Match crosses the same-origin BFF without forwarding unrelated headers", async () => {
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
    return Response.json({ ok: true });
  };

  const revision = `sha256:${"a".repeat(64)}`;
  try {
    const request = new Request("https://console.example/api/manager/registry/ppu-a/sites/1", {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: "Bearer browser-token",
        "Content-Type": "application/json",
        "Idempotency-Key": "site-write-1",
        "If-Match": `"${revision}"`,
        "X-Do-Not-Forward": "private-hop-header",
      },
      body: JSON.stringify({ enabled: true, interface: "mock", target: "TARGET-NEW" }),
    });

    const response = await relayManagerPpuAliasRequest(request, "ppu-a", "/api/settings/sites/1");
    assert.equal(response.status, 200);
    assert.equal(
      observedUrl,
      "http://127.0.0.1:18180/api/ppus/ppu-a/gateway/api/settings/sites/1",
    );
    assert.equal(observedInit.headers.get("If-Match"), `"${revision}"`);
    assert.equal(observedInit.headers.get("Idempotency-Key"), "site-write-1");
    assert.equal(observedInit.headers.get("Authorization"), "Bearer browser-token");
    assert.equal(observedInit.headers.get("X-Do-Not-Forward"), null);
  } finally {
    globalThis.fetch = originalFetch;
    if (previousMode === undefined) delete process.env.PLASMA_CONTROL_STATION_MODE;
    else process.env.PLASMA_CONTROL_STATION_MODE = previousMode;
    if (previousManager === undefined) delete process.env.PLASMA_MANAGER_API_URL;
    else process.env.PLASMA_MANAGER_API_URL = previousManager;
  }
});
