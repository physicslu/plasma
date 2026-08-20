import { expect, test, type Page, type Route } from "@playwright/test";

type MockMode = "normal" | "cancel-race-success" | "individual-cancel-partial";

type StartRequest = { site_id: number; operation: string };

type MockController = {
  startRequests: StartRequest[];
  cancelRequests: string[];
};

const enabledSites = [1, 2];

function ppuStatus() {
  return {
    ok: true,
    ppu: {
      ppu_id: "mock-ppu-01",
      facility_id: "mock-facility-01",
      model: "MOCK-PPU",
      display_name: "Mock PPU 01",
      site_count: 8,
      enabled_site_count: 2,
      capabilities: {
        max_supported_sites: 8,
        operations: ["erase", "program", "verify", "read"],
      },
    },
    sites: Array.from({ length: 8 }, (_, index) => ({
      site_id: index + 1,
      enabled: enabledSites.includes(index + 1),
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: enabledSites.includes(index + 1) ? "Mock" : null,
      target: enabledSites.includes(index + 1) ? "STM32F103C8T6" : null,
    })),
  };
}

function jobSnapshot(
  jobId: string,
  siteId: number,
  operation: string,
  state: "queued" | "running" | "success" | "cancelled",
  cancelRequested = false,
) {
  return {
    ok: true,
    job: {
      job_id: jobId,
      site_id: siteId,
      operation,
      state,
      cancel_requested: cancelRequested,
      stage: operation,
      stage_state: state === "success" ? "done" : state,
      stage_progress_percent: state === "success" ? 100 : 25,
      progress_percent: state === "success" ? 100 : 25,
      bytes_done: null,
      bytes_total: null,
      result: state === "success" || state === "cancelled"
        ? { state, output_files: [], error: null }
        : undefined,
    },
  };
}

async function fulfillJson(route: Route, status: number, body: unknown) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installMock(page: Page, options: { mode?: MockMode; waitForStarts?: number } = {}): Promise<MockController> {
  const mode = options.mode ?? "normal";
  const waitForStarts = options.waitForStarts ?? 0;
  const startRequests: StartRequest[] = [];
  const cancelRequests: string[] = [];
  const jobs = new Map<string, { siteId: number; operation: string; cancelled: boolean; polls: number }>();
  let nextJob = 0;

  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (request.method() === "GET" && url.pathname === "/api/status" && !url.searchParams.has("job")) {
      await fulfillJson(route, 200, ppuStatus());
      return;
    }

    if (request.method() === "POST" && url.pathname === "/api/jobs") {
      const body = request.postDataJSON() as StartRequest;
      startRequests.push(body);
      nextJob += 1;
      const jobId = `mock-job-${nextJob}`;
      jobs.set(jobId, { siteId: body.site_id, operation: body.operation, cancelled: false, polls: 0 });
      await fulfillJson(route, 202, jobSnapshot(jobId, body.site_id, body.operation, "queued"));
      return;
    }

    if (request.method() === "POST" && url.pathname.startsWith("/api/jobs/") && url.pathname.endsWith("/cancel")) {
      const jobId = url.pathname.split("/")[3];
      cancelRequests.push(jobId);
      const job = jobs.get(jobId);
      if (job) job.cancelled = true;
      await fulfillJson(route, 200, { ok: true, job: { job_id: jobId, cancel_requested: true } });
      return;
    }

    if (request.method() === "GET" && url.pathname === "/api/status" && url.searchParams.has("job")) {
      const jobId = url.searchParams.get("job")!;
      const job = jobs.get(jobId)!;
      job.polls += 1;

      if (mode === "cancel-race-success" && job.cancelled) {
        await fulfillJson(route, 200, jobSnapshot(jobId, job.siteId, job.operation, "success", true));
        return;
      }

      if (mode === "individual-cancel-partial") {
        if (job.cancelled) {
          await fulfillJson(route, 200, jobSnapshot(jobId, job.siteId, job.operation, "cancelled", true));
          return;
        }
        if (job.siteId === 2 && startRequests.length >= waitForStarts) {
          await fulfillJson(route, 200, jobSnapshot(jobId, job.siteId, job.operation, "success"));
          return;
        }
        await fulfillJson(route, 200, jobSnapshot(jobId, job.siteId, job.operation, "running"));
        return;
      }

      if (job.cancelled) {
        await fulfillJson(route, 200, jobSnapshot(jobId, job.siteId, job.operation, "cancelled", true));
        return;
      }
      await fulfillJson(route, 200, jobSnapshot(jobId, job.siteId, job.operation, job.polls > 1 ? "success" : "running"));
      return;
    }

    await fulfillJson(route, 404, { error: { message: `unhandled ${url.pathname}` } });
  });

  return { startRequests, cancelRequests };
}

async function openConsole(page: Page, options: { mode?: MockMode; waitForStarts?: number } = {}) {
  const mock = await installMock(page, options);
  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  return mock;
}

function batchSummary(page: Page) {
  return page.getByLabel("選取 Site 狀態摘要");
}

function liveLog(page: Page) {
  return page.getByLabel("Live job log");
}

test("starts with SITE 1/SITE 2 visible and no batch operation selected", async ({ page }) => {
  await openConsole(page);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  for (const operation of ["擦除", "燒錄", "驗證", "讀取"]) {
    await expect(page.getByLabel(`批次操作：${operation}`)).not.toBeChecked();
  }
});

test("selects batch operations and completes them through the browser", async ({ page }) => {
  const mock = await openConsole(page);
  await page.getByLabel("批次操作：擦除").check();
  await page.getByLabel("批次操作：讀取").check();
  await page.getByRole("button", { name: "批次執行：擦除、讀取" }).click();
  await expect.poll(() => mock.startRequests.length).toBe(4);
  await expect(liveLog(page)).toContainText("[BATCH] COMPLETE");
});

test("starts selected sites concurrently instead of serializing site pipelines", async ({ page }) => {
  const mock = await openConsole(page);
  await page.getByLabel("批次操作：擦除").check();
  await page.getByLabel("批次操作：讀取").check();
  await page.getByRole("button", { name: "批次執行：擦除、讀取" }).click();
  await expect.poll(() => mock.startRequests.length).toBeGreaterThanOrEqual(2);
  expect(mock.startRequests.slice(0, 2).map(item => item.site_id).sort()).toEqual([1, 2]);
});

test("batch cancel stops active jobs and prevents later operations", async ({ page }) => {
  const mock = await openConsole(page);
  await page.getByLabel("批次操作：擦除").check();
  await page.getByLabel("批次操作：讀取").check();
  await page.getByRole("button", { name: "批次執行：擦除、讀取" }).click();
  await expect.poll(() => mock.startRequests.length).toBe(2);
  await page.getByLabel("取消批次工作").click();
  await expect.poll(() => mock.cancelRequests.length).toBe(2);
  expect(mock.startRequests.every(request => request.operation === "erase")).toBe(true);
  await expect(liveLog(page)).toContainText("[BATCH] CANCELLED");
});

test("reports PARTIAL when one Site is cancelled independently", async ({ page }) => {
  const mock = await openConsole(page, { mode: "individual-cancel-partial", waitForStarts: 2 });

  await page.getByLabel("批次操作：擦除").check();
  await page.getByRole("button", { name: "批次執行：擦除" }).click();

  await expect.poll(() => mock.startRequests.length).toBe(2);
  const cancelSite1 = page.getByLabel("取消 SITE 1 工作");
  await expect(cancelSite1).toBeEnabled();
  await cancelSite1.click();

  await expect.poll(() => mock.cancelRequests.length).toBe(1);
  await expect(batchSummary(page)).toContainText("成功 1");
  await expect(batchSummary(page)).toContainText("取消 1");
  await expect(liveLog(page)).toContainText("[BATCH] PARTIAL · success: SITE 2 · cancelled: SITE 1");
});

test("cancel request wins batch classification when the last job races to success", async ({ page }) => {
  const mock = await openConsole(page, { mode: "cancel-race-success" });

  await page.getByLabel("批次操作：擦除").check();
  await page.getByLabel("批次操作：讀取").check();
  await page.getByRole("button", { name: "批次執行：擦除、讀取" }).click();

  await expect.poll(() => mock.startRequests.length).toBe(2);
  await page.getByLabel("取消批次工作").click();
  await expect.poll(() => mock.cancelRequests.length).toBe(2);

  await expect(page.locator(".channelTable .state").filter({ hasText: "批次已取消" })).toHaveCount(2);
  await expect(batchSummary(page)).toContainText("取消 2");
  await expect(liveLog(page)).toContainText("[BATCH] CANCELLED");
  expect(mock.startRequests.every(request => request.operation === "erase")).toBe(true);

  await page.locator(".channelDetails").filter({ hasText: "SITE 1" }).click();
  await expect(page.getByText("Job State", { exact: true }).locator("..").locator("dd")).toHaveText("SUCCESS");
  await expect(page.getByText("Batch State", { exact: true }).locator("..").locator("dd")).toHaveText("已取消");
  await expect(page.getByText("Protocol", { exact: true }).locator("..").locator("dd")).toHaveText("REST → Plasma v3.3 TCP");
});
