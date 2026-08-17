import { expect, test, type Page } from "@playwright/test";

type Operation = "erase" | "program" | "verify" | "read";
type JobState = "queued" | "running" | "success" | "failed" | "cancelled" | "timeout" | "aborted";
type MockMode = "auto-success" | "wait-for-cancel" | "cancel-race-success";

type MockJob = {
  jobId: string;
  channelId: number;
  operation: Operation;
  cancelRequested: boolean;
};

type MockOptions = {
  mode?: MockMode;
  waitForStarts?: number;
};

function jobPayload(job: MockJob, state: JobState) {
  const running = state === "running";
  const complete = state === "success";
  return {
    job_id: job.jobId,
    channel_id: job.channelId,
    operation: job.operation,
    state,
    cancel_requested: job.cancelRequested,
    stage: running ? job.operation : complete ? job.operation : null,
    stage_state: running ? "running" : complete ? "success" : null,
    stage_progress_percent: complete ? 100 : running ? 50 : 0,
    progress_percent: complete ? 100 : running ? 50 : 0,
    bytes_done: null,
    bytes_total: null,
    result: complete
      ? {
          state,
          ...(job.operation === "read" ? { output_files: [`read_CH${job.channelId}.bin`] } : {}),
          error: null,
        }
      : undefined,
  };
}

async function installMockApi(page: Page, options: MockOptions = {}) {
  const mode = options.mode ?? "auto-success";
  const waitForStarts = options.waitForStarts ?? 1;
  const jobs = new Map<string, MockJob>();
  const startRequests: Array<{ channelId: number; operation: Operation; jobId: string }> = [];
  const cancelRequests: string[] = [];
  let nextJobId = 1;

  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (request.method() === "GET" && path === "/api/status") {
      const jobId = url.searchParams.get("job");
      if (!jobId) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            ok: true,
            channels: Array.from({ length: 8 }, (_, channelId) => ({
              channel_id: channelId,
              enabled: channelId < 2,
              state: "idle",
              current_job_id: null,
              queued_jobs: 0,
              interface: channelId < 2 ? "Mock" : null,
              target: channelId < 2 ? "STM32F103C8T6" : null,
            })),
          }),
        });
        return;
      }

      const job = jobs.get(jobId);
      if (!job) {
        await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "job not found" } }) });
        return;
      }

      let state: JobState = "running";
      if (job.cancelRequested) {
        state = mode === "cancel-race-success" ? "success" : "cancelled";
      } else if (mode === "auto-success" && startRequests.length >= waitForStarts) {
        state = "success";
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, job: jobPayload(job, state) }),
      });
      return;
    }

    if (request.method() === "POST" && path === "/api/jobs") {
      const body = request.postDataJSON() as { channel_id: number; operation: Operation };
      const jobId = `e2e-job-${nextJobId++}`;
      const job: MockJob = {
        jobId,
        channelId: body.channel_id,
        operation: body.operation,
        cancelRequested: false,
      };
      jobs.set(jobId, job);
      startRequests.push({ channelId: job.channelId, operation: job.operation, jobId });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, job: jobPayload(job, "queued") }),
      });
      return;
    }

    const cancelMatch = path.match(/^\/api\/jobs\/([^/]+)\/cancel$/);
    if (request.method() === "POST" && cancelMatch) {
      const jobId = decodeURIComponent(cancelMatch[1]);
      const job = jobs.get(jobId);
      if (job) job.cancelRequested = true;
      cancelRequests.push(jobId);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled mock route" } }) });
  });

  return { jobs, startRequests, cancelRequests };
}

async function openConsole(page: Page, options: MockOptions = {}) {
  const mock = await installMockApi(page, options);
  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");
  return mock;
}

const batchSummary = (page: Page) => page.getByLabel("選取通道狀態摘要");

test("starts with CH0/CH1 visible and no batch operation selected", async ({ page }) => {
  await openConsole(page);

  await expect(page.getByLabel("顯示 CH0")).toBeChecked();
  await expect(page.getByLabel("顯示 CH1")).toBeChecked();
  await expect(page.getByLabel("顯示 CH2")).not.toBeChecked();
  await expect(page.getByLabel("顯示 CH2").locator("..")).toContainText("停用");
  await expect(page.getByLabel("通道配置摘要")).toContainText("停用 6");

  for (const operation of ["擦除", "燒錄", "驗證", "讀取"]) {
    await expect(page.getByLabel(`批次操作：${operation}`)).not.toBeChecked();
  }
  await expect(page.getByLabel("批次執行：尚未選擇操作")).toBeDisabled();
});

test("selects batch operations and completes them through the browser", async ({ page }) => {
  const mock = await openConsole(page);

  await page.getByLabel("選擇 Firmware 檔案").setInputFiles({
    name: "e2e.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.from([0x50, 0x4c, 0x41, 0x53, 0x4d, 0x41]),
  });
  await page.getByLabel("批次操作：擦除").check();
  await page.getByLabel("批次操作：燒錄").check();

  const execute = page.getByRole("button", { name: "批次執行：擦除、燒錄" });
  await expect(execute).toBeEnabled();
  await execute.click();

  await expect(batchSummary(page)).toContainText("成功 2");
  await expect.poll(() => mock.startRequests.length).toBe(4);
  expect(mock.startRequests.map(request => request.operation)).toEqual(["erase", "erase", "program", "program"]);
});

test("starts selected channels concurrently instead of serializing channel pipelines", async ({ page }) => {
  const mock = await openConsole(page, { mode: "auto-success", waitForStarts: 2 });

  await page.getByLabel("批次操作：擦除").check();
  await page.getByRole("button", { name: "批次執行：擦除" }).click();

  await expect.poll(() => mock.startRequests.length).toBe(2);
  expect(new Set(mock.startRequests.map(request => request.channelId))).toEqual(new Set([0, 1]));
  await expect(batchSummary(page)).toContainText("成功 2");
});

test("batch cancel stops active jobs and prevents later operations", async ({ page }) => {
  const mock = await openConsole(page, { mode: "wait-for-cancel" });

  await page.getByLabel("批次操作：擦除").check();
  await page.getByLabel("批次操作：讀取").check();
  await page.getByRole("button", { name: "批次執行：擦除、讀取" }).click();

  await expect.poll(() => mock.startRequests.length).toBe(2);
  await page.getByLabel("取消批次工作").click();

  await expect.poll(() => mock.cancelRequests.length).toBe(2);
  await expect(batchSummary(page)).toContainText("取消 2");
  expect(mock.startRequests.every(request => request.operation === "erase")).toBe(true);
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
  expect(mock.startRequests.every(request => request.operation === "erase")).toBe(true);

  await page.locator(".channelDetails").filter({ hasText: "CH0" }).click();
  await expect(page.getByText("Job State", { exact: true }).locator("..").locator("dd")).toHaveText("SUCCESS");
  await expect(page.getByText("Batch State", { exact: true }).locator("..").locator("dd")).toHaveText("已取消");
});
