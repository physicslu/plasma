import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

test("PMode retries transient PPU status failures without requiring Production Set reselection", async () => {
  const consoleSource = await fs.readFile(new URL("../app/fleet/factory-console-v2.tsx", import.meta.url), "utf8");
  const recoverySource = await fs.readFile(new URL("../app/fleet/ppu-status-recovery.ts", import.meta.url), "utf8");

  assert.match(consoleSource, /runtimeRecoveryGenerationRef/);
  assert.match(consoleSource, /isRecoverablePPUStatusError/);
  assert.match(consoleSource, /ppuRetryDelayMs/);
  assert.match(consoleSource, /PPU_STATUS_REQUEST_TIMEOUT_MS/);
  assert.match(consoleSource, /STATUS ERROR .* RECONNECTING/);
  assert.match(consoleSource, /STATUS RESTORED/);
  assert.match(consoleSource, /runtimeRecoveryGenerationRef\.current \+= 1/);

  assert.match(recoverySource, /PPU_STATUS_RETRY_DELAYS_MS = \[1_000, 2_000, 4_000, 5_000\]/);
  assert.match(recoverySource, /PPU_STATUS_REQUEST_TIMEOUT_MS = 5_000/);
  assert.match(recoverySource, /error instanceof PlasmaApiError && error\.transient/);
});
