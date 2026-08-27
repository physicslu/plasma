import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const transport = readFileSync(new URL("../app/security-transport.ts", import.meta.url), "utf8");
const provider = readFileSync(new URL("../app/security-transport-provider.tsx", import.meta.url), "utf8");
const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");


test("browser security credential remains memory-only and masked", () => {
  assert.match(transport, /let bearerToken: string \| null = null/);
  assert.doesNotMatch(transport, /(?:localStorage|sessionStorage)\.setItem\([^\n]*(?:token|credential)/i);
  assert.doesNotMatch(provider, /(?:localStorage|sessionStorage)\.(?:getItem|setItem|removeItem)\(/);
  assert.match(provider, /type="password"/);
});


test("security headers activate only after the backend E4101 boundary is detected", () => {
  assert.match(transport, /response\.status === 401 && errorCode === "E4101"/);
  assert.match(transport, /securityDetected && bearerToken/);
  assert.match(transport, /securityDetected && isStateChanging\(method\)/);
  assert.match(provider, /state\.securityDetected &&/);
});


test("gateway fetches receive bearer authentication and durable command identity", () => {
  assert.match(transport, /headers\.set\("Authorization", `Bearer \$\{bearerToken\}`\)/);
  assert.match(transport, /headers\.set\("Idempotency-Key", commandIdFor\(identity\)\)/);
  assert.match(transport, /ambiguousCommandIds\.get\(identity\)/);
  assert.match(transport, /errorCode !== "E4104"/);
});


test("authenticated readback downloads cannot bypass the fetch security boundary", () => {
  assert.match(transport, /outputDownloadAnchor/);
  assert.match(transport, /engineering\\\/targets/);
  assert.match(transport, /!anchor \|\| !securityDetected/);
  assert.match(transport, /document\.addEventListener\("click", onClick, true\)/);
  assert.match(transport, /response\.blob\(\)/);
});


test("security transport is installed before child Gateway effects", () => {
  assert.match(layout, /SecurityTransportProvider/);
  assert.match(layout, /<SecurityTransportProvider>/);
  assert.match(transport, /if \(typeof window !== "undefined"\) installSecurityTransport\(\)/);
  assert.match(provider, /installSecurityTransport\(\)/);
});
