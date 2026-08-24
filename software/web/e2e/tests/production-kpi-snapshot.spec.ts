import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;
const batchId = "batch-kpi-snapshot-test";

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 1,
    site_count: 1,
    programming_asset_scope: "connection-session-and-ppu",
    facilities: [{
      facility_id: facilityId,
      display_name: "Mock Facility 01",
      ppus: [{
        ppu_id: ppuId,
        display_name: "Mock PPU 01",
        model: "MOCK-PPU",
        site_count: 1,
        provider: "mock",
      }],
    }],
  };
}

function targetStatus() {
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: "Mock PPU 01",
      site_count: 1,
      enabled_site_count: 1,
      capabilities: { max_supported_sites: 1, operations: ["erase", "program", "verify", "read"] },
    },
    sites: [{
      site_id: 1,
      enabled: true,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: "mock",
      target: "MOCK-IC",
    }],
  };
}

function batchSnapshot(stage: "initial" | "pass" | "faulted") {
  const completedRounds = stage === "initial" ? 0 : 1;
  const finalFailures = stage === "faulted" ? 1 : 0;
  const siteState = stage === "faulted" ? "faulted" : "running";
  const batchState = stage === "faulted" ? "partial" : "running";
  const counts = {
    ready: 0,
    running: siteState === "running" ? 1 : 0,
    success: 0,
    faulted: siteState === "faulted" ? 1 : 0,
    error: 0,
    stopped: 0,
    cancelled: 0,
  };

  return {
    batch_id: batchId,
    state: batchState,
    created_at: "2026-08-24T00:00:00Z",
    started_at: "2026-08-24T00:00:00Z",
    finished_at: stage === "faulted" ? "2026-08-24T00:00:03Z" : null,
    operations: ["erase"],
    execution_policy: {
      repeat_count: 100,
      site_retry_limit: 3,
      failed_site_stop_threshold: null,
    },
    asset: null,
    read: { offset: 0, length: 256 },
    cancel_requested: false,
    stop_reason: null,
    error: null,
    faulted_site_count: counts.faulted,
    site_counts: counts,
    operation_statistics: {},
    sites: [{
      facility_id: facilityId,
      ppu_id: ppuId,
      site_id: 1,
      key: `${facilityId}::${ppuId}::SITE1`,
      state: siteState,
      current_round: stage === "initial" ? 1 : 2,
      completed_rounds: completedRounds,
      current_operation: siteState === "running" ? "erase" : null,
      current_job_id: siteState === "running" ? "job-kpi" : null,
      progress_percent: siteState === "running" ? 35 : 100,
      total_attempts: stage === "initial" ? 1 : 2,
      retry_count: stage === "faulted" ? 3 : 0,
      final_failures: finalFailures,
      faulted_round: stage === "faulted" ? 2 : null,
      faulted_operation: stage === "faulted" ? "erase" : null,
      last_failure_source: stage === "faulted" ? "injected" : null,
      error: stage === "faulted"
        ? { message: "retry exhausted", error_code: "E6002", failure_source: "injected" }
        : null,
      operation_statistics: {},
    }],
  };
}

async function installApi(page: Page) {
  let batchPolls = 0;

  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: "0123456789abcdef0123456789abcdef",
            programming_asset_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: false,
          },
        }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }
    if (url.pathname === `/api/engineering/targets/${facilityId}/${ppuId}/api/status` && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(targetStatus()) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled engineering route" } }) });
  });

  await page.route("**/api/batches**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/batches" && request.method() === "POST") {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: batchSnapshot("initial") }),
      });
      return;
    }
    if (path === `/api/batches/${batchId}` && request.method() === "GET") {
      batchPolls += 1;
      if (batchPolls === 1) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: batchSnapshot("pass") }),
        });
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 2_000));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: batchSnapshot("faulted") }),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "missing batch" } }) });
  });
}

test("Production KPI cards update from the authoritative server Batch snapshot while the Site is still running", async ({ page }) => {
  await installApi(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();

  await page.getByRole("checkbox", { name: `${facilityId} ${ppuId} SITE-01`, exact: true }).check();
  await page.getByRole("button", { name: "確定選取", exact: true }).click();
  await page.getByLabel("Repeat Count").fill("100");
  await page.locator(".batchOperations label").filter({ hasText: "E" }).getByRole("checkbox").check();
  await page.locator(".executeBatchButton").click();

  const summary = page.getByRole("region", { name: "Mock topology summary" });
  await expect(summary).toHaveAttribute("data-kpi-source", "server-batch-snapshot");
  await expect(summary.locator('[data-production-kpi="total"] b')).toHaveText("1");
  await expect(summary.locator('[data-production-kpi="pass"] b')).toHaveText("1");
  await expect(summary.locator('[data-production-kpi="fail"] b')).toHaveText("0");
  await expect(summary.locator('[data-production-kpi="yield"] b')).toHaveText("100.0%");
  await expect(page.locator(`[data-production-target="${facilityId}::${ppuId}"] [data-production-site="1"]`)).toHaveAttribute("data-site-state", "running");

  await expect(summary.locator('[data-production-kpi="total"] b')).toHaveText("2", { timeout: 5_000 });
  await expect(summary.locator('[data-production-kpi="pass"] b')).toHaveText("1");
  await expect(summary.locator('[data-production-kpi="fail"] b')).toHaveText("1");
  await expect(summary.locator('[data-production-kpi="yield"] b')).toHaveText("50.0%");
  await expect(page.locator(`[data-production-target="${facilityId}::${ppuId}"] [data-production-site="1"]`)).toHaveAttribute("data-site-state", "faulted");
});
