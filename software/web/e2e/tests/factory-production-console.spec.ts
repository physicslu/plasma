import { expect, test, type Page, type Route } from "@playwright/test";

const siteCounts = [2, 4, 6, 8];

function catalog() {
  const facilities = Array.from({ length: 3 }, (_, facilityIndex) => {
    const number = facilityIndex + 1;
    const facilityId = `mock-facility-${String(number).padStart(2, "0")}`;
    return {
      facility_id: facilityId,
      display_name: `Mock Facility ${String(number).padStart(2, "0")}`,
      ppus: siteCounts.map((siteCount, ppuIndex) => ({
        ppu_id: `${facilityId}-ppu-${String(ppuIndex + 1).padStart(2, "0")}`,
        display_name: `Mock PPU ${String(ppuIndex + 1).padStart(2, "0")}`,
        model: "MOCK-PPU",
        site_count: siteCount,
        provider: "mock",
      })),
    };
  });
  return { ok: true, provider: "mock", facility_count: 3, ppu_count: 12, site_count: 60, facilities };
}

function targetStatus(facilityId: string, ppuId: string) {
  const match = /-ppu-(\d+)$/.exec(ppuId);
  const ppuIndex = Number(match?.[1] ?? 1) - 1;
  const siteCount = siteCounts[ppuIndex] ?? 2;
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: `Mock PPU ${String(ppuIndex + 1).padStart(2, "0")}`,
      site_count: siteCount,
      enabled_site_count: siteCount,
      capabilities: { max_supported_sites: siteCount, operations: ["erase", "program", "verify", "read"] },
    },
    sites: Array.from({ length: siteCount }, (_, index) => ({
      site_id: index + 1,
      enabled: true,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: "mock",
      target: "MOCK-IC",
    })),
  };
}

type BatchRequest = {
  targets: Array<{ facility_id: string; ppu_id: string; site_ids: number[] }>;
  operations: string[];
  execution_policy: {
    repeat_count: number;
    site_retry_limit: number;
    failed_site_stop_threshold: number | null;
  };
};

type MockRuntimeOptions = {
  keepFirstPpuRunningUntilCancel?: boolean;
};

function siteCountMap(sites: Array<{ state: string }>) {
  const states = ["ready", "running", "success", "faulted", "error", "stopped", "cancelled"];
  return Object.fromEntries(states.map(state => [state, sites.filter(site => site.state === state).length]));
}

async function installProductionMock(page: Page, options: MockRuntimeOptions = {}) {
  const submittedBatches: BatchRequest[] = [];
  const cancelledPpus: string[] = [];
  let batchRequest: BatchRequest | null = null;
  let batchId = "batch-browser-test";
  let polls = 0;
  let cancelAll = false;
  const cancelledPpuSet = new Set<string>();

  function batchSnapshot() {
    if (!batchRequest) throw new Error("Batch has not been submitted");
    const allSites = batchRequest.targets.flatMap(target => target.site_ids.map(siteId => ({
      facility_id: target.facility_id,
      ppu_id: target.ppu_id,
      site_id: siteId,
    })));
    const firstPpu = batchRequest.targets[0]?.ppu_id;
    const terminal = polls >= 2 && !options.keepFirstPpuRunningUntilCancel;
    const sites = allSites.map(site => {
      let state = "running";
      let progress = 40;
      if (cancelAll) {
        state = "cancelled";
        progress = 100;
      } else if (cancelledPpuSet.has(site.ppu_id)) {
        state = "cancelled";
        progress = 100;
      } else if (options.keepFirstPpuRunningUntilCancel && site.ppu_id === firstPpu) {
        state = "running";
        progress = 40;
      } else if (polls >= 2) {
        state = "success";
        progress = 100;
      }
      const complete = state === "success" ? batchRequest!.execution_policy.repeat_count : 0;
      const attempts = state === "success"
        ? batchRequest!.execution_policy.repeat_count * batchRequest!.operations.length
        : Math.max(1, batchRequest!.operations.length);
      return {
        ...site,
        key: `${site.facility_id}::${site.ppu_id}::SITE${site.site_id}`,
        state,
        current_round: state === "running" ? 1 : complete,
        completed_rounds: complete,
        current_operation: state === "running" ? batchRequest!.operations[0] : null,
        current_job_id: state === "running" ? `job-${site.ppu_id}-${site.site_id}` : null,
        progress_percent: progress,
        total_attempts: attempts,
        retry_count: 0,
        final_failures: 0,
        faulted_round: null,
        faulted_operation: null,
        last_failure_source: null,
        error: null,
        operation_statistics: {},
      };
    });
    const counts = siteCountMap(sites);
    let state = "running";
    if (cancelAll) state = "cancelled";
    else if (sites.every(site => site.state === "success")) state = "success";
    else if (sites.every(site => site.state === "cancelled")) state = "cancelled";
    else if (sites.some(site => site.state === "cancelled") && sites.some(site => site.state === "success")) state = "partial";
    else if (terminal) state = "success";

    const operation_statistics = Object.fromEntries(batchRequest.operations.map(operation => [operation, {
      logical_executions: state === "success" ? allSites.length * batchRequest!.execution_policy.repeat_count : allSites.length,
      attempts: state === "success" ? allSites.length * batchRequest!.execution_policy.repeat_count : allSites.length,
      retries: 0,
      successful_executions: state === "success" ? allSites.length * batchRequest!.execution_policy.repeat_count : 0,
      failed_executions: 0,
      error_executions: 0,
      cancelled_executions: sites.filter(site => site.state === "cancelled").length,
      failed_attempts: 0,
      error_attempts: 0,
      cancelled_attempts: sites.filter(site => site.state === "cancelled").length,
      attempt_failure_rate: 0,
    }]));

    return {
      batch_id: batchId,
      state,
      created_at: "2026-08-21T00:00:00Z",
      started_at: "2026-08-21T00:00:00Z",
      finished_at: ["success", "partial", "cancelled"].includes(state) ? "2026-08-21T00:00:01Z" : null,
      operations: batchRequest.operations,
      execution_policy: batchRequest.execution_policy,
      asset: null,
      read: { offset: 0, length: 256 },
      cancel_requested: cancelAll,
      stop_reason: cancelAll ? "operator_cancel" : null,
      error: null,
      faulted_site_count: 0,
      site_counts: counts,
      operation_statistics,
      sites,
    };
  }

  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({
        ok: true,
        session: {
          session_id: "0123456789abcdef0123456789abcdef",
          previous_session_cleared: false,
          programming_asset_cache_scope: "connection-session-and-ppu",
        },
      }) });
      return;
    }
    if (path === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }
    const targetMatch = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/status$/.exec(path);
    if (targetMatch && request.method() === "GET") {
      const facilityId = decodeURIComponent(targetMatch[1]);
      const ppuId = decodeURIComponent(targetMatch[2]);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(targetStatus(facilityId, ppuId)) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });

  await page.route("**/api/batches**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/batches" && request.method() === "POST") {
      batchRequest = request.postDataJSON() as BatchRequest;
      submittedBatches.push(batchRequest);
      polls = 0;
      cancelAll = false;
      cancelledPpuSet.clear();
      await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: batchSnapshot() }) });
      return;
    }
    if (path === `/api/batches/${batchId}` && request.method() === "GET") {
      polls += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: batchSnapshot() }) });
      return;
    }
    if (path === `/api/batches/${batchId}/cancel` && request.method() === "POST") {
      cancelAll = true;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: batchSnapshot() }) });
      return;
    }
    const ppuCancel = new RegExp(`^/api/batches/${batchId}/targets/([^/]+)/([^/]+)/cancel$`).exec(path);
    if (ppuCancel && request.method() === "POST") {
      const ppuId = decodeURIComponent(ppuCancel[2]);
      cancelledPpuSet.add(ppuId);
      cancelledPpus.push(ppuId);
      polls = Math.max(polls, 2);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: batchSnapshot() }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "missing batch" } }) });
  });

  return {
    submittedBatches,
    cancelledPpus,
    get polls() { return polls; },
  };
}

function fpsCheckbox(page: Page, facilityId: string, ppuId: string, siteId = 1) {
  return page.getByRole("checkbox", { name: `${facilityId} ${ppuId} SITE-${String(siteId).padStart(2, "0")}` });
}

async function buildTwoPpuSet(page: Page) {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Mock topology summary" })).toContainText("12");

  const facilityId = "mock-facility-01";
  const ppu1Id = `${facilityId}-ppu-01`;
  const ppu2Id = `${facilityId}-ppu-02`;
  await expect(fpsCheckbox(page, facilityId, ppu1Id)).toBeVisible();
  await expect(fpsCheckbox(page, facilityId, ppu2Id)).toBeVisible();
  await fpsCheckbox(page, facilityId, ppu1Id).check();
  await fpsCheckbox(page, facilityId, ppu2Id).check();
  await page.getByRole("button", { name: "確定選取", exact: true }).click();

  const ppu1 = page.locator(`[data-production-target="${facilityId}::${ppu1Id}"]`);
  const ppu2 = page.locator(`[data-production-target="${facilityId}::${ppu2Id}"]`);
  await expect(ppu1).toBeVisible();
  await expect(ppu2).toBeVisible();
  return { facilityId, ppu1, ppu2, ppu1Id, ppu2Id };
}

async function selectEraseAndExecute(page: Page) {
  await page.locator(".batchOperations label").filter({ hasText: "E" }).getByRole("checkbox").check();
  await page.locator(".executeBatchButton").click();
}

test("FPS selector exposes Select all, Cancel all and Confirm selection together", async ({ page }) => {
  await installProductionMock(page);
  await page.goto("/fleet");
  const actions = page.locator(".fpsSelectorActions");
  await expect(actions.getByRole("button", { name: "全選", exact: true })).toBeVisible();
  await expect(actions.getByRole("button", { name: "全部取消", exact: true })).toBeVisible();
  await expect(actions.getByRole("button", { name: "確定選取", exact: true })).toBeVisible();
});

test("FPS selector retains selections across Facilities and renders Facility → PPU → Site hierarchy", async ({ page }) => {
  await installProductionMock(page);
  await page.goto("/fleet");
  const firstFacility = "mock-facility-01";
  const secondFacility = "mock-facility-02";
  const firstPpu = `${firstFacility}-ppu-01`;
  const secondPpu = `${secondFacility}-ppu-02`;
  await fpsCheckbox(page, firstFacility, firstPpu).check();
  await fpsCheckbox(page, secondFacility, secondPpu, 2).check();
  await expect(fpsCheckbox(page, firstFacility, firstPpu)).toBeChecked();
  await expect(fpsCheckbox(page, secondFacility, secondPpu, 2)).toBeChecked();
  await expect(page.locator(".fpsSelectorActions")).toContainText("2 F / 2 P / 2 S");
  await page.getByRole("button", { name: "確定選取", exact: true }).click();
  await expect(page.locator(`[data-production-facility="${firstFacility}"] [data-production-ppu="${firstPpu}"] [data-production-site="1"]`)).toBeVisible();
  await expect(page.locator(`[data-production-facility="${secondFacility}"] [data-production-ppu="${secondPpu}"] [data-production-site="2"]`)).toBeVisible();
});

test("Cancel all clears only the draft FPS selection and leaves Active FPS unchanged", async ({ page }) => {
  await installProductionMock(page);
  await page.goto("/fleet");
  const facilityId = "mock-facility-01";
  const ppuId = `${facilityId}-ppu-01`;
  const site = fpsCheckbox(page, facilityId, ppuId);
  await site.check();
  await page.getByRole("button", { name: "確定選取", exact: true }).click();
  const activeSite = page.locator(`[data-production-target="${facilityId}::${ppuId}"] [data-production-site="1"]`);
  await expect(activeSite).toBeVisible();
  await page.getByRole("button", { name: "全部取消", exact: true }).click();
  await expect(site).not.toBeChecked();
  await expect(page.locator(".fpsSelectorActions")).toContainText("0 F / 0 P / 0 S");
  await expect(page.getByRole("button", { name: "確定選取", exact: true })).toBeDisabled();
  await expect(activeSite).toBeVisible();
});

test("all Site cards, LEDs and PPU footprints use one global size", async ({ page }) => {
  await installProductionMock(page);
  const { ppu1, ppu2 } = await buildTwoPpuSet(page);
  const site1 = ppu1.locator('[data-production-site="1"]');
  const site2 = ppu2.locator('[data-production-site="1"]');
  const box1 = await site1.boundingBox();
  const box2 = await site2.boundingBox();
  expect(box1?.width).toBe(box2?.width);
  expect(box1?.height).toBe(box2?.height);
  const lamp1 = await site1.locator(".prototypeSiteLamp").boundingBox();
  const lamp2 = await site2.locator(".prototypeSiteLamp").boundingBox();
  expect(lamp1?.width).toBe(lamp2?.width);
  expect(lamp1?.height).toBe(lamp2?.height);
  expect((await ppu1.boundingBox())?.width).toBe((await ppu2.boundingBox())?.width);
});

test("Site density is selected from total active FPS count, not per-PPU count", async ({ page }) => {
  await installProductionMock(page);
  await page.goto("/fleet");
  const facilityId = "mock-facility-01";
  const ppu1 = `${facilityId}-ppu-01`;
  const ppu4 = `${facilityId}-ppu-04`;
  for (const siteId of [1, 2]) await fpsCheckbox(page, facilityId, ppu1, siteId).check();
  for (let siteId = 1; siteId <= 8; siteId += 1) await fpsCheckbox(page, facilityId, ppu4, siteId).check();
  await page.getByRole("button", { name: "確定選取", exact: true }).click();
  await expect(page.getByRole("region", { name: "Active FPS : 即時執行狀態", exact: true })).toHaveClass(/density-comfortable/);
});

test("running Site shows server Batch progress and Batch cancel ends it", async ({ page }) => {
  await installProductionMock(page, { keepFirstPpuRunningUntilCancel: true });
  const { ppu1 } = await buildTwoPpuSet(page);
  await selectEraseAndExecute(page);
  const site = ppu1.locator('[data-production-site="1"]');
  await expect(site).toHaveAttribute("data-site-state", "running");
  await expect(site.locator("strong")).toHaveText("RUNNING");
  await expect(site.locator("small").first()).toContainText("40%");
  const animationName = await site.locator(".prototypeSiteLamp.running i").evaluate(element => getComputedStyle(element).animationName);
  expect(animationName).toContain("production-site-running-pulse");
  await page.locator(".cancelBatchButton").click();
  await expect(site).toHaveAttribute("data-site-state", "cancelled");
});

test("Production submits one server Batch for multiple PPUs and keeps selector expanded", async ({ page }) => {
  const runtime = await installProductionMock(page);
  const { ppu1, ppu2 } = await buildTwoPpuSet(page);
  await selectEraseAndExecute(page);
  await expect(page.locator(".productionWorkspace")).not.toHaveClass(/selector-collapsed/);
  await expect(page.getByRole("button", { name: "收起選擇器", exact: true })).toBeVisible();
  await expect.poll(() => runtime.submittedBatches.length).toBe(1);
  expect(runtime.submittedBatches[0].targets).toHaveLength(2);
  await expect(ppu1.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");
  await expect(ppu2.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");
  await expect(page.locator(".serverBatchStatistics")).toHaveAttribute("data-batch-state", "success");
});

test("Batch execution policy is submitted once and completed rounds come from server snapshot", async ({ page }) => {
  const runtime = await installProductionMock(page);
  const { ppu1 } = await buildTwoPpuSet(page);
  await page.getByLabel("Repeat Count").fill("3");
  await page.getByLabel("Site Retry Limit").fill("2");
  await page.getByLabel("Failed Site Stop Threshold").fill("2");
  await selectEraseAndExecute(page);
  await expect.poll(() => runtime.submittedBatches.length).toBe(1);
  expect(runtime.submittedBatches[0].execution_policy).toEqual({
    repeat_count: 3,
    site_retry_limit: 2,
    failed_site_stop_threshold: 2,
  });
  const site = ppu1.locator('[data-production-site="1"]');
  await expect(site).toHaveAttribute("data-completed-rounds", "3");
  await expect(site).toHaveAttribute("data-total-attempts", "3");
});

test("Cancel PPU uses Batch PPU endpoint and does not cancel the other PPU", async ({ page }) => {
  const runtime = await installProductionMock(page, { keepFirstPpuRunningUntilCancel: true });
  const { ppu1, ppu2, ppu1Id, ppu2Id } = await buildTwoPpuSet(page);
  await selectEraseAndExecute(page);
  await expect(ppu1.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "running");
  await ppu1.getByRole("button", { name: "Cancel PPU", exact: true }).click();
  await expect(ppu1.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "cancelled");
  await expect(ppu2.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");
  expect(runtime.cancelledPpus).toContain(ppu1Id);
  expect(runtime.cancelledPpus).not.toContain(ppu2Id);
  await expect(page.locator(".serverBatchStatistics")).toHaveAttribute("data-batch-state", "partial");
});
