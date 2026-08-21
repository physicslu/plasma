import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

type MutableJobState = "running" | "cancelled" | "success";

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

async function installExecutionApi(page: Page) {
  let jobState: MutableJobState = "running";
  let cancelRequested = false;
  let jobCounter = 0;
  let activeJobId = "";

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
    if (request.method() === "GET" && tail === "status" && !url.searchParams.has("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(targetStatus()) });
      return;
    }

    if (request.method() === "POST" && tail === "jobs") {
      jobCounter += 1;
      activeJobId = `guard-job-${jobCounter}`;
      cancelRequested = false;
      jobState = "running";
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify(jobPayload(activeJobId, "queued")),
      });
      return;
    }

    if (request.method() === "GET" && tail === "status" && url.searchParams.has("job")) {
      const jobId = url.searchParams.get("job") ?? activeJobId;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(jobPayload(jobId, jobState, cancelRequested)),
      });
      return;
    }

    const cancelMatch = /^jobs\/([^/]+)\/cancel$/.exec(tail);
    if (request.method() === "POST" && cancelMatch) {
      cancelRequested = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, job: { job_id: cancelMatch[1], cancel_requested: true } }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });

  return {
    finish(state: "cancelled" | "success") { jobState = state; },
    get cancelRequested() { return cancelRequested; },
  };
}

async function expectModeLocked(page: Page, linkName: string) {
  const link = page.getByRole("link", { name: linkName, exact: true });
  await expect(link).toHaveAttribute("aria-disabled", "true");
  await expect(page.locator(".globalExecutionGuard")).toContainText("PPU BUSY · 1 JOB");
  const before = page.url();
  await link.click({ force: true });
  await expect.poll(() => page.url()).toBe(before);
}

async function expectModeUnlocked(page: Page, linkName: string) {
  const link = page.getByRole("link", { name: linkName, exact: true });
  await expect(link).not.toHaveAttribute("aria-disabled", "true");
  await expect(page.locator(".globalExecutionGuard")).toHaveCount(0);
}

test("Pmod batch execution locks Emode through running and cancelling until terminal", async ({ page }) => {
  const api = await installExecutionApi(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();

  await page.getByRole("checkbox", { name: `${facilityId} ${ppuId} SITE-01`, exact: true }).check();
  await page.getByRole("button", { name: "確定選取", exact: true }).click();
  await expect(page.locator(`[data-production-target="${facilityId}::${ppuId}"] [data-production-site="1"]`)).toBeVisible();

  const toolbar = page.locator(".programmingBatchToolbar");
  await toolbar.locator(".programmingBatchOperations input").first().check();
  await expect(toolbar.getByRole("status", { name: "Batch readiness" })).toContainText("BATCH READY");
  await toolbar.locator(".executeBatchButton").click();

  await expectModeLocked(page, "工程模式");
  await toolbar.locator(".cancelBatchButton").click();
  await expect.poll(() => api.cancelRequested).toBe(true);
  await expectModeLocked(page, "工程模式");

  api.finish("cancelled");
  await expectModeUnlocked(page, "工程模式");
});

test("Emode single-Site PPU action locks Pmod through cancel until terminal", async ({ page }) => {
  const api = await installExecutionApi(page);
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  await page.getByRole("button", { name: "SITE 1 擦除", exact: true }).click();
  await expectModeLocked(page, "量產模式");

  await page.getByRole("button", { name: "Cancel SITE 1", exact: true }).click();
  await expect.poll(() => api.cancelRequested).toBe(true);
  await expectModeLocked(page, "量產模式");

  api.finish("cancelled");
  await expectModeUnlocked(page, "量產模式");
});
