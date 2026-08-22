import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;
const batchId = "batch-synthetic-browser";

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 1,
    site_count: 2,
    programming_asset_scope: "connection-session-and-ppu",
    facilities: [{
      facility_id: facilityId,
      display_name: "Mock Facility 01",
      ppus: [{
        ppu_id: ppuId,
        display_name: "Mock PPU 01",
        model: "MOCK-PPU",
        site_count: 2,
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
      site_count: 2,
      enabled_site_count: 2,
      capabilities: { max_supported_sites: 2, operations: ["erase", "program", "verify", "read"] },
    },
    sites: [1, 2].map(siteId => ({
      site_id: siteId,
      enabled: true,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: "mock",
      target: "MOCK-IC",
    })),
  };
}

function terminalBatch() {
  const operationStatistics = {
    logical_executions: 1,
    attempts: 1,
    retries: 0,
    successful_executions: 1,
    failed_executions: 0,
    error_executions: 0,
    cancelled_executions: 0,
    failed_attempts: 0,
    error_attempts: 0,
    cancelled_attempts: 0,
    attempt_failure_rate: 0,
  };
  return {
    batch_id: batchId,
    state: "success",
    created_at: "2026-08-22T00:00:00Z",
    started_at: "2026-08-22T00:00:00Z",
    finished_at: "2026-08-22T00:00:01Z",
    operations: ["program"],
    execution_policy: {
      repeat_count: 1,
      site_retry_limit: 0,
      failed_site_stop_threshold: null,
    },
    asset: {
      name: "mock-synthetic-256KiB.bin",
      size_bytes: 256 * 1024,
      sha256: "a".repeat(64),
      asset_type: "image",
      asset_format: "binary",
    },
    read: { offset: 0, length: 256 },
    cancel_requested: false,
    stop_reason: null,
    error: null,
    faulted_site_count: 0,
    site_counts: {
      ready: 0,
      running: 0,
      success: 1,
      faulted: 0,
      error: 0,
      stopped: 0,
      cancelled: 0,
    },
    operation_statistics: { program: operationStatistics },
    sites: [{
      facility_id: facilityId,
      ppu_id: ppuId,
      site_id: 1,
      key: `${facilityId}::${ppuId}::SITE1`,
      state: "success",
      current_round: 1,
      completed_rounds: 1,
      current_operation: null,
      current_job_id: null,
      progress_percent: 100,
      total_attempts: 1,
      retry_count: 0,
      final_failures: 0,
      faulted_round: null,
      faulted_operation: null,
      last_failure_source: null,
      error: null,
      operation_statistics: { program: operationStatistics },
    }],
  };
}

async function installApi(page: Page) {
  let submittedBatch: Record<string, unknown> | null = null;

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
    const targetMatch = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/status$/.exec(url.pathname);
    if (targetMatch && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(targetStatus()) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled Engineering route" } }) });
  });

  await page.route("**/api/batches**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/batches" && request.method() === "POST") {
      submittedBatch = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, batch: terminalBatch() }),
      });
      return;
    }
    if (url.pathname === `/api/batches/${batchId}` && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, batch: terminalBatch() }),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled Batch route" } }) });
  });

  return { get submittedBatch() { return submittedBatch; } };
}

test("Production Mock submits Synthetic Image intent without browser-generated asset bytes", async ({ page }) => {
  const api = await installApi(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();

  await page.getByRole("checkbox", { name: `${facilityId} ${ppuId} SITE-01`, exact: true }).check();
  await page.getByRole("button", { name: "確定選取", exact: true }).click();

  const toolbar = page.locator(".programmingBatchToolbar");
  await toolbar.locator(".programmingBatchOperations input").nth(1).check();
  await expect(toolbar.locator(".programmingFileName")).toHaveText("Mock Synthetic Image");
  await expect(toolbar.locator(".programmingFileName")).toHaveAttribute("data-image-source", "mock_synthetic");
  await expect(toolbar.getByRole("status", { name: "Batch readiness" })).toContainText("BATCH READY");
  await toolbar.locator(".executeBatchButton").click();

  await expect.poll(() => api.submittedBatch).not.toBeNull();
  const submitted = api.submittedBatch!;
  expect(submitted.operations).toEqual(["program"]);
  expect(submitted.session_id).toBe("0123456789abcdef0123456789abcdef");
  expect(submitted).not.toHaveProperty("asset");

  await expect(page.locator("[data-batch-state=\"success\"]")).toBeVisible();
  await expect(page.locator(".programmingFileName")).toHaveAttribute("data-image-source", "mock_synthetic");
});
