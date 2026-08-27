import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const transport = readFileSync(new URL("../app/security-transport.ts", import.meta.url), "utf8");
const provider = readFileSync(new URL("../app/security-transport-provider.tsx", import.meta.url), "utf8");
const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");


test("browser security credential remains memory-only", () => {
  assert.match(transport, /let bearerToken: string \| null = null/);
  assert.doesNotMatch(transport, /setItem\([^\n]*(?:token|credential)/i);
  assert.doesNotMatch(provider, /localStorage|sessionStorage/);
});


test("gateway fetches receive bearer authentication and durable command identity", () => {
  assert.match(transport, /headers\.set\("Authorization", `Bearer \$\{bearerToken\}`\)/);
  assert.match(transport, /headers\.set\("Idempotency-Key", commandId\)/);
  assert.match(transport, /ambiguousCommandIds\.get\(identity\)/);
  assert.match(transport, /response\.status !== 409/);
});


test("authenticated readback downloads cannot bypass the fetch security boundary", () => {
  assert.match(transport, /outputDownloadAnchor/);
  assert.match(transport, /document\.addEventListener\("click", onClick, true\)/);
  assert.match(transport, /response\.blob\(\)/);
});


test("security transport is installed at the application shell", () => {
  assert.match(layout, /SecurityTransportProvider/);
  assert.match(layout, /<SecurityTransportProvider>/);
  assert.match(provider, /installSecurityTransport\(\)/);
});
