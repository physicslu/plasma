import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const gateway = await readFile(new URL("../../python/plasma_web/gateway.py", import.meta.url), "utf8");
const communication = await readFile(new URL("../../python/plasma_web/gateway_communication.py", import.meta.url), "utf8");
const settingsApi = await readFile(new URL("../app/gateway-settings-api.ts", import.meta.url), "utf8");
const plasmaApi = await readFile(new URL("../app/plasma-api.ts", import.meta.url), "utf8");
const pmodRecovery = await readFile(new URL("../app/fleet/ppu-status-recovery.ts", import.meta.url), "utf8");

test("Gateway owns Engineering PPU status timeout and retry policy", () => {
  assert.match(gateway, /request_with_gateway_policy/);
  assert.match(gateway, /self\.gateway_settings\.snapshot\(\)/);
  assert.match(gateway, /engineering_status_retry_backoff_s/);
  assert.match(gateway, /engineering_ppu_status_retry/);
  assert.match(gateway, /HTTPStatus\.SERVICE_UNAVAILABLE/);
  assert.match(gateway, /ErrorCode\.CONNECTION_TIMEOUT/);
  assert.match(gateway, /ErrorCode\.CONNECTION_FAILED/);

  assert.match(communication, /async def request_with_gateway_policy/);
  assert.match(communication, /asyncio\.wait_for/);
  assert.match(communication, /policy\.ppu_retry_count/);
  assert.match(communication, /policy\.request_timeout_s/);
  assert.match(communication, /PPU_RETRY_BACKOFF_CAP_MULTIPLIER = 4/);
});

test("Browser status timeout is only an outer watchdog derived from Gateway response budget", () => {
  assert.match(settingsApi, /ppu_response_budget_ms/);
  assert.match(settingsApi, /gatewayStatusObservationTimeoutMs/);
  assert.match(settingsApi, /GATEWAY_STATUS_TRANSPORT_MARGIN_MS = 5_000/);
  assert.match(settingsApi, /GATEWAY_SETTINGS_FALLBACK_TTL_MS = 5_000/);
  assert.match(plasmaApi, /statusObservationTimeoutMs/);
  assert.match(plasmaApi, /ensureGatewaySettings/);
  assert.match(plasmaApi, /gatewayStatusObservationTimeoutMs/);

  assert.match(pmodRecovery, /PPU_STATUS_REQUEST_TIMEOUT_MS = undefined/);
  assert.doesNotMatch(pmodRecovery, /PPU_STATUS_REQUEST_TIMEOUT_MS = 5_000/);
});
