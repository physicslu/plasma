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

function jobSnapshot(jobId: string, siteId: number, operation: string, state: string, progress: number) {
  return {
    job_id: jobId,
    site_id: siteId,
    operation,
    state,
    cancel_requested: state === "cancelled",
    stage: operation,
    stage_state: state,
    stage_progress_percent: progress,
    progress_percent: progress,
    bytes_done: null,
    bytes_total: null,
    result: state === "success" || state === "cancelled" || state === "failed"
      ? { state, output_files: [], error: state === "failed" ? { message: "mock failure" } : null }
      : undefined,
  };
}

type MockRuntimeOptions = {
  holdStartsUntilTwoPpus?: boolean;
  keepFirstPpuRunningUntilCancel?: boolean;
};

async function installProductionMock(page: Page, options: MockRuntimeOptions = {}) {
  const jobs = new Map<string, { ppuId: string; siteId: number; operation: string; polls: number; cancelled: boolean }>();
  const seenStartPpus = new Set<string>();
  const cancelledPpus: string[] = [];
  let sequence = 0;
  let releaseStarts: (() => void) | null = null;
  const startsReleased = new Promise<void>(resolve => { releaseStarts = resolve; });

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

    const targetMatch = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/(.*)$/.exec(path);
    if (!targetMatch) {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
      return;
    }
    const facilityId = decodeURIComponent(targetMatch[1]);
    const ppuId = decodeURIComponent(targetMatch[2]);
    const tail = targetMatch[3];

    if (tail === "status" && request.method() === "GET" && !url.searchParams.get("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(targetStatus(facilityId, ppuId)) });
      return;
    }

    if (tail === "jobs" && request.method() === "POST") {
      const body = request.postDataJSON() as { site_id: number; operation: string };
      const jobId = `job-${++sequence}`;
      jobs.set(jobId, { ppuId, siteId: body.site_id, operation: body.operation, polls: 0, cancelled: false });
      seenStartPpus.add(ppuId);
      if (options.holdStartsUntilTwoPpus) {
        if (seenStartPpus.size >= 2) releaseStarts?.();
        await startsReleased;
      }
      await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ ok: true, job: jobSnapshot(jobId, body.site_id, body.operation, "queued", 0) }) });
      return;
    }

    const cancelMatch = /^jobs\/([^/]+)\/cancel$/.exec(tail);
    if (cancelMatch && request.method() === "POST") {
      const job = jobs.get(cancelMatch[1]);
      if (job) {
        job.cancelled = true;
        cancelledPpus.push(job.ppuId);
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
      return;
    }

    if (tail === "status" && request.method() === "GET" && url.searchParams.get("job")) {
      const jobId = url.searchParams.get("job") as string;
      const job = jobs.get(jobId);
      if (!job) {
        await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "missing job" } }) });
        return;
      }
      job.polls += 1;
      let state = "running";
      let progress = 50;
      if (job.cancelled) {
        state = "cancelled";
        progress = 100;
      } else if (options.keepFirstPpuRunningUntilCancel && job.ppuId.endsWith("ppu-01")) {
        state = "running";
        progress = 40;
      } else if (job.polls >= 2) {
        state = "success";
        progress = 100;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, job: jobSnapshot(jobId, job.siteId, job.operation, state, progress) }) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });

  return { jobs, seenStartPpus, cancelledPpus };
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
  return { ppu1, ppu2, ppu1Id, ppu2Id };
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
  await expect(page.locator(".fpsSelectionSummary")).toBeHidden();

  await page.getByRole("button", { name: "確定選取", exact: true }).click();
  const facilityOne = page.locator(`[data-production-facility="${firstFacility}"]`);
  const facilityTwo = page.locator(`[data-production-facility="${secondFacility}"]`);
  await expect(facilityOne).toBeVisible();
  await expect(facilityTwo).toBeVisible();
  await expect(facilityOne.locator(`[data-production-ppu="${firstPpu}"] [data-production-site="1"]`)).toBeVisible();
  await expect(facilityTwo.locator(`[data-production-ppu="${secondPpu}"] [data-production-site="2"]`)).toBeVisible();
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
  await expect(page.locator(".fpsSelectionSummary")).toBeHidden();
  await expect(page.getByRole("button", { name: "確定選取", exact: true })).toBeDisabled();
  await expect(activeSite).toBeVisible();
});

test("all Site cards, LEDs and four-Site PPU footprints use one global size", async ({ page }) => {
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

  const ppuBox1 = await ppu1.boundingBox();
  const ppuBox2 = await ppu2.boundingBox();
  expect(ppuBox1?.width).toBe(ppuBox2?.width);
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

test("running Site shows a blinking LED, operation text and progress", async ({ page }) => {
  await installProductionMock(page, { keepFirstPpuRunningUntilCancel: true });
  const { ppu1 } = await buildTwoPpuSet(page);
  await page.locator(".batchOperations label").filter({ hasText: "E" }).getByRole("checkbox").check();
  await page.locator(".executeBatchButton").click();

  const site = ppu1.locator('[data-production-site="1"]');
  await expect(site).toHaveAttribute("data-site-state", "running");
  await expect(site.locator("strong")).toHaveText("RUNNING");
  await expect(site.locator("small")).toContainText("40%");
  await expect(site.locator("small")).toContainText("E");
  const animationName = await site.locator(".prototypeSiteLamp.running i").evaluate(element => getComputedStyle(element).animationName);
  expect(animationName).toContain("production-site-running-pulse");

  await page.locator(".cancelBatchButton").click();
  await expect(site).toHaveAttribute("data-site-state", "cancelled");
});

test("selected PPUs dispatch concurrently and selector remains expanded when execution starts", async ({ page }) => {
  const runtime = await installProductionMock(page, { holdStartsUntilTwoPpus: true });
  const { ppu1, ppu2 } = await buildTwoPpuSet(page);
  await page.locator(".batchOperations label").filter({ hasText: "E" }).getByRole("checkbox").check();
  await page.locator(".executeBatchButton").click();

  await expect(page.locator(".productionWorkspace")).not.toHaveClass(/selector-collapsed/);
  await expect(page.getByRole("button", { name: "收起選擇器", exact: true })).toBeVisible();
  await expect.poll(() => runtime.seenStartPpus.size).toBe(2);
  await expect(ppu1.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");
  await expect(ppu2.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");
  await expect(page.locator(".batchState")).toContainText("COMPLETE");
  await expect(page.locator(".productionPrototypeLog")).toContainText("[BAT] COMPLETE");
});

test("Cancel PPU affects only that PPU while another PPU continues to PASS", async ({ page }) => {
  const runtime = await installProductionMock(page, { keepFirstPpuRunningUntilCancel: true });
  const { ppu1, ppu2, ppu1Id, ppu2Id } = await buildTwoPpuSet(page);
  await page.locator(".batchOperations label").filter({ hasText: "E" }).getByRole("checkbox").check();
  await page.locator(".executeBatchButton").click();
  await expect(ppu1.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "running");
  await expect(ppu2.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");

  await ppu1.getByRole("button", { name: "Cancel PPU", exact: true }).click();
  await expect(ppu1.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "cancelled");
  await expect(ppu2.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");
  await expect(page.locator(".batchState")).toContainText("PARTIAL");
  expect(runtime.cancelledPpus).toContain(ppu1Id);
  expect(runtime.cancelledPpus).not.toContain(ppu2Id);
});
