import { expect, test, type Page } from "@playwright/test";
import { FIRMWARE, mockFleet, mockManager } from "./managed-programming-helpers";
import { programmingJobAction } from "./programming-job-test-helpers";
import { commitProductionSites, programmingJob } from "./production-console-helpers";

// U10: PMode is Manager-managed only. The KPI cards follow the authoritative
// Manager Batch Cycle counters (the PPU-local Batch rounds are gone). Scripted
// Manager Batch views at the Browser boundary: one Site, Repeat 100, the
// Manager settles Cycles while the Site Lane stays open.

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

type Stage = { settled: number; pass: number; fail: number; ended: boolean };

async function installScriptedBatch(page: Page) {
  await mockManager(page, { ppus: mockFleet(1, [1]) });
  const stage: Stage = { settled: 0, pass: 0, fail: 0, ended: false };
  let started: Record<string, unknown> = {};
  const view = () => {
    const outcome = stage.ended ? (stage.fail ? "FAIL" : "PASS") : null;
    return {
      schema: "plasma.manager.programming-batch.v2", batch_id: "8".repeat(32), start_id: started.start_id,
      targets: started.targets, icpn: started.icpn, operations: started.operations, source: "image",
      policy: { repeat: 100, replace_ic_before_next_cycle: true, retry_limit: 0, stop_policy: { kind: "never" } },
      state: outcome ? "finished" : "running", execution_status: outcome ? "COMPLETED" : "RUNNING",
      outcome, reason: outcome === "FAIL" ? "JOB_NOT_SUCCESS" : null, failure_domain: null, stop_requested: false,
      units: [{
        ppu_alias: ppuId, site_id: 1, status: outcome ? "COMPLETED" : "RUNNING", outcome,
        reason: outcome === "FAIL" ? "JOB_NOT_SUCCESS" : null, failure_domain: null, progress: null,
        // The next Cycle's attempt is in flight while the Site Lane is open.
        attempts: outcome ? [] : [{
          attempt: 1, cycle_index: stage.settled + 1, state: "running", outcome: null, reason: null,
          run_id: String(stage.settled + 1).padStart(32, "a"), job_id: `job-c${stage.settled + 1}`,
          plan_id: `plan-c${stage.settled + 1}`, job_binding_sha256: "3".repeat(64), safe_off: null, safe_off_state: null, retry: null,
        }],
        cycle: {
          planned: 100, index: stage.settled + 1, cycle_id: String(stage.settled + 1).padStart(32, "0"),
          state: outcome ? "ENDED" : "ACTIVE", disposition: outcome, settled: stage.settled, pass: stage.pass,
          fail: stage.fail, retry_attempts: 0, remaining: 100 - stage.settled, continue_seq: 0, continued_seq: 0,
          wait_reason: null, last: null,
        },
      }],
      attempts: [], current_run: null,
      counts: { pass: outcome === "PASS" ? 1 : 0, fail: outcome === "FAIL" ? 1 : 0, blocked: 0, unknown: 0, sites: 1, attempts: stage.settled },
      cycles: { planned: 100, settled: stage.settled, pass: stage.pass, fail: stage.fail, retry_attempts: 0,
        remaining: 100 - stage.settled, awaiting_continue: 0 },
      auto_retry: "DISABLED", created_at: null, started_at: "2026-11-23T00:00:00+00:00",
      finished_at: outcome ? "2026-11-23T00:01:00+00:00" : null,
    };
  };
  await page.route(/\/api\/manager\/programming\/batches$/, async route => {
    started = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 202, json: { ok: true, batch: view() } });
  });
  await page.route(/\/api\/manager\/programming\/batches\/[0-9a-f]{32}$/, route => route.fulfill({ json: { ok: true, batch: view() } }));
  await page.route(/\/api\/manager\/programming\/batches\/[0-9a-f]{32}\/cycles\?/, route => route.fulfill({
    json: { ok: true, batch_id: "8".repeat(32), total: 0, offset: 0, next_offset: 0, records: [] },
  }));
  return stage;
}

test("Production KPI cards update from authoritative Manager Batch Cycles while a Site is still running", async ({ page }) => {
  const stage = await installScriptedBatch(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "PMODE · FACTORY CONSOLE" })).toBeVisible();

  await commitProductionSites(page, facilityId, ppuId, [1]);
  const target = page.getByLabel("Target IC");
  await target.fill("STM32F103C8T6");
  await page.getByRole("option", { name: /STM32F103C8T6/ }).click();
  await programmingJob(page).getByLabel("Production Programming Image file").setInputFiles({
    name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE,
  });
  await page.getByLabel("Repeat Count").fill("100");
  await programmingJobAction(programmingJob(page), "start").click();

  // Cycle 1 settled PASS; the Site Lane is still open.
  stage.settled = 1;
  stage.pass = 1;
  await expect(page.locator('[data-kpi="pass"] b')).toHaveText("1");
  await expect(page.locator('[data-kpi="fail"] b')).toHaveText("0");
  await expect(page.locator('[data-kpi="processed-ic"] b')).toHaveText("1");
  await expect(page.locator('[data-kpi="yield"] b')).toHaveText("100.0%");
  await expect(page.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "running");

  // Cycle 2 settled FAIL and the Manager ends the Site Lane.
  stage.settled = 2;
  stage.fail = 1;
  stage.ended = true;
  await expect(page.locator('[data-kpi="pass"] b')).toHaveText("1", { timeout: 5_000 });
  await expect(page.locator('[data-kpi="fail"] b')).toHaveText("1", { timeout: 5_000 });
  await expect(page.locator('[data-kpi="processed-ic"] b')).toHaveText("2", { timeout: 5_000 });
  await expect(page.locator('[data-kpi="yield"] b')).toHaveText("50.0%", { timeout: 5_000 });
  await expect(page.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "faulted");
});
