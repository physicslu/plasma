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
  return {
    ok: true,
    provider: "mock",
    facility_count: 3,
    ppu_count: 12,
    site_count: 60,
    facilities,
  };
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
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: "0123456789abcdef0123456789abcdef",
            previous_session_cleared: false,
            programming_asset_cache_scope: "connection-session-and-ppu",
          },
        }),
      });
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
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, job: jobSnapshot(jobId, body.site_id, body.operation, "queued", 0) }),
      });
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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, job: jobSnapshot(jobId, job.siteId, job.operation, state, progress) }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });

  return { jobs, seenStartPpus, cancelledPpus };
}

async function buildTwoPpuSet(page: Page) {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Mock topology summary" })).toContainText("12");
  await expect(page.getByRole("region", { name: "Mock topology summary" })).toContainText("60");

  await page.getByRole("checkbox", { name: "Select mock-facility-01-ppu-01" }).check();
  await page.getByRole("checkbox", { name: "Select mock-facility-01-ppu-02" }).check();
  await page.getByRole("button", { name: "SET", exact: true }).click();

  const ppu1 = page.locator('[data-production-ppu="mock-facility-01-ppu-01"]');
  const ppu2 = page.locator('[data-production-ppu="mock-facility-01-ppu-02"]');
  await expect(ppu1).toBeVisible();
  await expect(ppu2).toBeVisible();
  await expect(page.locator('[data-production-ppu="mock-facility-01-ppu-03"]')).toHaveCount(0);

  await ppu1.getByRole("button", { name: "Clear Sites", exact: true }).click();
  await ppu2.getByRole("button", { name: "Clear Sites", exact: true }).click();
  await ppu1.getByRole("checkbox", { name: "mock-facility-01-ppu-01 SITE-01" }).check();
  await ppu2.getByRole("checkbox", { name: "mock-facility-01-ppu-02 SITE-01" }).check();
  return { ppu1, ppu2 };
}

test("Production Set selects one Facility and dispatches different PPUs concurrently", async ({ page }) => {
  const runtime = await installProductionMock(page, { holdStartsUntilTwoPpus: true });
  const { ppu1, ppu2 } = await buildTwoPpuSet(page);

  await page.locator(".batchOperations label").filter({ hasText: "E" }).getByRole("checkbox").check();
  await page.getByRole("button", { name: "EXECUTE BATCH", exact: true }).click();

  await expect.poll(() => runtime.seenStartPpus.size).toBe(2);
  await expect(ppu1.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");
  await expect(ppu2.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");
  await expect(page.locator(".batchState")).toContainText("COMPLETE");
  await expect(page.getByRole("region", { name: "Production Prototype Log" })).toContainText("[BAT] COMPLETE");
});

test("Cancel PPU affects only that PPU while another PPU continues to PASS", async ({ page }) => {
  const runtime = await installProductionMock(page, { keepFirstPpuRunningUntilCancel: true });
  const { ppu1, ppu2 } = await buildTwoPpuSet(page);

  await page.locator(".batchOperations label").filter({ hasText: "E" }).getByRole("checkbox").check();
  await page.getByRole("button", { name: "EXECUTE BATCH", exact: true }).click();
  await expect(ppu1.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "running");
  await expect(ppu2.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");

  await ppu1.getByRole("button", { name: "Cancel PPU", exact: true }).click();
  await expect(ppu1.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "cancelled");
  await expect(ppu2.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "success");
  await expect(page.locator(".batchState")).toContainText("PARTIAL");
  expect(runtime.cancelledPpus).toContain("mock-facility-01-ppu-01");
  expect(runtime.cancelledPpus).not.toContain("mock-facility-01-ppu-02");
});

test("Facility selector changes the available four-PPU set and locale remains interactive", async ({ page }) => {
  await installProductionMock(page);
  await page.goto("/fleet");
  const facility = page.getByLabel("Facility", { exact: true });
  await facility.selectOption("mock-facility-03");
  await expect(page.getByRole("checkbox", { name: "Select mock-facility-03-ppu-04" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Select mock-facility-01-ppu-01" })).toHaveCount(0);

  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(page.getByText("PPU Selection", { exact: true })).toBeVisible();
  await expect(page.getByText("After SET, only PPUs in this Production Set are shown below.")).toHaveCount(0);
});
