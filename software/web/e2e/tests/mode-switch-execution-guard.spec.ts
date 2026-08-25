import { expect, test, type Page, type Route } from "@playwright/test";
import {
  chooseTestTarget,
  commitProductionSites,
  factoryConsoleHeading,
  installTestDeviceCatalog,
  productionOperation,
  programmingJob,
} from "./production-console-helpers";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

type MutableJobState = "running" | "cancelled" | "success";
type MutableBatchState = "running" | "stopping" | "cancelled" | "success";

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

function jobPayload(jobId: string, state: "queued" | MutableJobState, cancelRequested = false) {
  const terminal = state === "cancelled" || state === "success";
  return {
    ok: true,
    job: {
      job_id: jobId,
      site_id: 1,
      operation: "erase",
      state,
      cancel_requested: cancelRequested,
      stage: state === "running" ? "erase" : null,
      stage_state: state === "running" ? "running" : null,
      stage_progress_percent: state === "running" ? 45 : terminal ? 100 : 0,
      progress_percent: state === "running" ? 45 : terminal ? 100 : 0,
      bytes_done: null,
      bytes_total: null,
      result: terminal ? { state, output_files: [], error: null } : undefined,
    },
  };
}

function batchPayload(state: "queued" | MutableBatchState, cancelRequested = false) {
  const siteState = state === "cancelled" ? "cancelled" : state === "success" ? "success" : "running";
  const terminal = state === "cancelled" || state === "success";
  const counts = {
    ready: 0,
    running: terminal ? 0 : 1,
    success: state === "success" ? 1 : 0,
    faulted: 0,
    error: 0,
    stopped: 0,
    cancelled: state === "cancelled" ? 1 : 0,
  };
  return {
    ok: true,
    rest_contract_version: "3",
    batch: {
      batch_id: "batch-mode-guard",
      state,
      created_at: "2026-08-21T00:00:00Z",
      started_at: state === "queued" ? null : "2026-08-21T00:00:00Z",
      finished_at: terminal ? "2026-08-21T00:00:01Z" : null,
      operations: ["erase"],
      execution_policy: { repeat_count: 1, site_retry_limit: 0, failed_site_stop_threshold: null },
      asset: null,
      read: { offset: 0, length: 256 },
      cancel_requested: cancelRequested,
      stop_reason: cancelRequested ? "operator_cancel" : null,
      error: null,
      faulted_site_count: 0,
      site_counts: counts,
      operation_statistics: {
        erase: {
          logical_executions: 1,
          attempts: 1,
          retries: 0,
          successful_executions: state === "success" ? 1 : 0,
          failed_executions: 0,
          error_executions: 0,
          cancelled_executions: state === "cancelled" ? 1 : 0,
          failed_attempts: 0,
          error_attempts: 0,
          cancelled_attempts: state === "cancelled" ? 1 : 0,
          attempt_failure_rate: 0,
        },
      },
      sites: [{
        facility_id: facilityId,
        ppu_id: ppuId,
        site_id: 1,
        key: `${facilityId}::${ppuId}::SITE1`,
        state: siteState,
        current_round: terminal ? 1 : 1,
        completed_rounds: state === "success" ? 1 : 0,
        current_operation: terminal ? null : "erase",
        current_job_id: terminal ? null : "batch-owned-job",
        progress_percent: terminal ? 100 : 45,
        total_attempts: 1,
        retry_count: 0,
        final_failures: 0,
        faulted_round: null,
        faulted_operation: null,
        last_failure_source: null,
        error: null,
        operation_statistics: {},
      }],
    },
  };
}

async function installExecutionApi(page: Page) {
  let jobState: MutableJobState = "running";
  let jobCancelRequested = false;
  let jobCounter = 0;
  let activeJobId = "";
  let batchState: MutableBatchState = "running";
  let batchCancelRequested = false;
  let remainingBatchPollFailures = 0;
  let remainingJobPollFailures = 0;
  let failJobPollsUntilCancel = false;
  let completeJobOnCancel = false;
  let returnSuccessOnBatchCancel = false;
  let gatewayOffline = false;
  await installTestDeviceCatalog(page);

  await page.route("**/api/settings/gateway", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        gateway_settings: { revision: 1, ppu_request_timeout_ms: 1_000, ppu_retry_count: 1 },
      }),
    });
  });

  await page.route("**/api/health/live", async route => {
    if (gatewayOffline) {
      await route.abort("failed");
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, gateway: "alive" }),
    });
  });

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

    const targetMatch = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/(.*)$/.exec(url.pathname);
    if (!targetMatch) {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
      return;
    }

    const tail = targetMatch[3];
    if (gatewayOffline && request.method() === "GET" && tail === "status") {
      await route.abort("failed");
      return;
    }
    if (request.method() === "GET" && tail === "status" && !url.searchParams.has("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(targetStatus()) });
      return;
    }

    if (request.method() === "POST" && tail === "jobs") {
      jobCounter += 1;
      activeJobId = `guard-job-${jobCounter}`;
      jobCancelRequested = false;
      jobState = "running";
      await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(jobPayload(activeJobId, "queued")) });
      return;
    }

    if (request.method() === "GET" && tail === "status" && url.searchParams.has("job")) {
      if ((failJobPollsUntilCancel && !jobCancelRequested) || remainingJobPollFailures > 0) {
        if (remainingJobPollFailures > 0) remainingJobPollFailures -= 1;
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ error: { error_code: "E2002", message: "simulated PPU communication timeout" } }),
        });
        return;
      }
      const jobId = url.searchParams.get("job") ?? activeJobId;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(jobPayload(jobId, jobState, jobCancelRequested)) });
      return;
    }

    const cancelMatch = /^jobs\/([^/]+)\/cancel$/.exec(tail);
    if (request.method() === "POST" && cancelMatch) {
      jobCancelRequested = true;
      if (completeJobOnCancel) jobState = "cancelled";
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, job: { job_id: cancelMatch[1], cancel_requested: true } }) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });

  await page.route("**/api/batches**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/batches" && request.method() === "POST") {
      batchState = "running";
      batchCancelRequested = false;
      await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(batchPayload("queued")) });
      return;
    }
    if (path === "/api/batches/batch-mode-guard" && request.method() === "GET") {
      if (remainingBatchPollFailures > 0) {
        remainingBatchPollFailures -= 1;
        await route.abort("timedout");
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(batchPayload(batchState, batchCancelRequested)) });
      return;
    }
    if (path === "/api/batches/batch-mode-guard/cancel" && request.method() === "POST") {
      batchCancelRequested = true;
      if (returnSuccessOnBatchCancel) {
        batchState = "success";
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(batchPayload("success")) });
        return;
      }
      batchState = "stopping";
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(batchPayload("stopping", true)) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "missing batch" } }) });
  });

  return {
    finishBatch(state: "cancelled" | "success") { batchState = state; },
    failNextBatchPolls(count: number) { remainingBatchPollFailures = count; },
    finishOnBatchAbort() { returnSuccessOnBatchCancel = true; },
    failNextJobPolls(count: number) { remainingJobPollFailures = count; },
    failJobPollsUntilCancelled() {
      failJobPollsUntilCancel = true;
      completeJobOnCancel = true;
    },
    finishJob(state: "cancelled" | "success") { jobState = state; },
    setGatewayOffline(offline: boolean) { gatewayOffline = offline; },
    get batchCancelRequested() { return batchCancelRequested; },
    get jobCancelRequested() { return jobCancelRequested; },
  };
}

async function expectModeLocked(page: Page, linkName: string) {
  const link = page.getByRole("link", { name: linkName, exact: true });
  await expect(link).toHaveAttribute("aria-disabled", "true");
  await expect(page.locator(".globalExecutionGuard")).toContainText("EXECUTION BUSY · 1");
  const before = page.url();
  await link.click({ force: true });
  await expect.poll(() => page.url()).toBe(before);
}

async function expectModeUnlocked(page: Page, linkName: string) {
  const link = page.getByRole("link", { name: linkName, exact: true });
  await expect(link).not.toHaveAttribute("aria-disabled", "true");
  await expect(page.locator(".globalExecutionGuard")).toHaveCount(0);
}

test("Pmod server Batch locks Emode through running and stopping until terminal", async ({ page }) => {
  const api = await installExecutionApi(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await commitProductionSites(page, facilityId, ppuId, [1]);
  await chooseTestTarget(page);

  const job = programmingJob(page);
  await productionOperation(page, "E").check();
  await expect(job.locator(".factoryBatchStatus b")).toHaveText("BATCH READY");
  await job.locator(".factoryStartButton").click();

  await expectModeLocked(page, "工程模式");
  await job.locator(".factoryAbortButton").click();
  await expect.poll(() => api.batchCancelRequested).toBe(true);
  await expectModeLocked(page, "工程模式");

  api.finishBatch("cancelled");
  await expectModeUnlocked(page, "工程模式");
});

test("successful Pmod Batch releases its execution lease and restores Engineering mode", async ({ page }) => {
  const api = await installExecutionApi(page);
  await page.goto("/fleet");
  await commitProductionSites(page, facilityId, ppuId, [1]);
  const job = programmingJob(page);
  await productionOperation(page, "E").check();
  await job.locator(".factoryStartButton").click();
  await expectModeLocked(page, "工程模式");

  api.finishBatch("success");
  await expect(job.locator(".factoryBatchStatus b")).toHaveText("SUCCESS");
  await expectModeUnlocked(page, "工程模式");
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("plasma-production-active-batch-v1"))).toBeNull();
});

test("temporary Batch observation failures reconnect and still release the terminal mode guard", async ({ page }) => {
  const api = await installExecutionApi(page);
  await page.goto("/fleet");
  await commitProductionSites(page, facilityId, ppuId, [1]);
  const job = programmingJob(page);
  await productionOperation(page, "E").check();
  await job.locator(".factoryStartButton").click();
  await expectModeLocked(page, "工程模式");

  api.failNextBatchPolls(2);
  await expect(job.locator(".factoryBatchStatus b")).toHaveText("RECONNECTING");
  api.finishBatch("success");
  await expect(job.locator(".factoryBatchStatus b")).toHaveText("SUCCESS");
  await expectModeUnlocked(page, "工程模式");
  await expect(page.getByText(/OBSERVATION RESTORED/)).toBeVisible();
});

test("ABORT receiving an already successful Batch performs terminal cleanup immediately", async ({ page }) => {
  const api = await installExecutionApi(page);
  await page.goto("/fleet");
  await commitProductionSites(page, facilityId, ppuId, [1]);
  const job = programmingJob(page);
  await productionOperation(page, "E").check();
  await job.locator(".factoryStartButton").click();
  await expectModeLocked(page, "工程模式");

  api.finishOnBatchAbort();
  await job.locator(".factoryAbortButton").click();
  await expect(job.locator(".factoryBatchStatus b")).toHaveText("SUCCESS");
  await expectModeUnlocked(page, "工程模式");
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("plasma-production-active-batch-v1"))).toBeNull();
});

test("restoring an already successful Batch clears its stale execution lease", async ({ page }) => {
  const api = await installExecutionApi(page);
  api.finishBatch("success");
  await page.addInitScript(() => {
    sessionStorage.setItem("plasma-production-active-batch-v1", JSON.stringify({
      apiBase: "https://plasma.open4th.com",
      batchId: "batch-mode-guard",
    }));
  });
  await page.goto("/fleet");
  await expect(programmingJob(page).locator(".factoryBatchStatus b")).toHaveText("SUCCESS");
  await expectModeUnlocked(page, "工程模式");
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("plasma-production-active-batch-v1"))).toBeNull();
});

test("Emode single-Site PPU action still locks Pmod through cancel until terminal", async ({ page }) => {
  const api = await installExecutionApi(page);
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  await page.getByRole("button", { name: "SITE 1 擦除", exact: true }).click();
  await expectModeLocked(page, "量產模式");

  await page.getByRole("button", { name: "Cancel SITE 1", exact: true }).click();
  await expect.poll(() => api.jobCancelRequested).toBe(true);
  await expectModeLocked(page, "量產模式");

  api.finishJob("cancelled");
  await expectModeUnlocked(page, "量產模式");
});

test("Emode retries transient PPU communication errors and restores its mode guard", async ({ page }) => {
  const api = await installExecutionApi(page);
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await page.getByLabel("Batch select SITE 2").uncheck();
  await page.getByLabel("Engineering batch erase").check();
  api.failNextJobPolls(1);
  await page.getByRole("button", { name: /START PROGRAMMING/ }).click();

  await expect(page.getByText(/RECONNECTING.*retry 1\/1/)).toBeVisible();
  api.finishJob("success");
  await expect(page.getByRole("region", { name: "Engineering Batch Summary" }).locator('[data-kpi="pass"] b')).toHaveText("1");
  await expectModeUnlocked(page, "量產模式");
});

test("Emode exhausted PPU communication retry cancels accepted Jobs and releases its mode guard", async ({ page }) => {
  const api = await installExecutionApi(page);
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await page.getByLabel("Batch select SITE 2").uncheck();
  await page.getByLabel("Engineering batch erase").check();
  api.failJobPollsUntilCancelled();
  await page.getByRole("button", { name: /START PROGRAMMING/ }).click();

  await expect.poll(() => api.jobCancelRequested, { timeout: 10_000 }).toBe(true);
  await expect(page.getByText(/\[PPU\] ISOLATED/)).toBeVisible();
  await expect(page.locator(".channelTable tbody tr").first().locator(".engineeringResult")).toHaveText("ERROR");
  await expectModeUnlocked(page, "量產模式");
});

test("Emode Gateway outage preserves accepted Jobs until authoritative observation returns", async ({ page }) => {
  const api = await installExecutionApi(page);
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await page.getByLabel("Batch select SITE 2").uncheck();
  await page.getByLabel("Engineering batch erase").check();
  await page.getByRole("button", { name: /START PROGRAMMING/ }).click();
  await expectModeLocked(page, "量產模式");

  api.setGatewayOffline(true);
  await expect(page.getByText(/\[NET\] GATEWAY RECONNECTING/)).toBeVisible({ timeout: 10_000 });
  await expectModeLocked(page, "量產模式");
  expect(api.jobCancelRequested).toBe(false);

  api.finishJob("success");
  api.setGatewayOffline(false);
  await expect(page.getByRole("region", { name: "Engineering Batch Summary" }).locator('[data-kpi="pass"] b')).toHaveText("1", { timeout: 10_000 });
  await expectModeUnlocked(page, "量產模式");
  expect(api.jobCancelRequested).toBe(false);
});
