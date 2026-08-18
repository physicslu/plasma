import { expect, test, type Page } from "@playwright/test";

type Operation = "erase" | "program" | "verify" | "read";
type JobState = "queued" | "running" | "success" | "failed" | "cancelled" | "timeout" | "aborted";
type VisualMode = "running" | "cancelled" | "failed";

type MockJob = {
  jobId: string;
  siteId: number;
  operation: Operation;
  cancelRequested: boolean;
};

function jobPayload(job: MockJob, state: JobState) {
  const running = state === "running";
  const success = state === "success";
  const failed = state === "failed";
  return {
    job_id: job.jobId,
    site_id: job.siteId,
    channel_id: job.siteId,
    operation: job.operation,
    state,
    cancel_requested: job.cancelRequested,
    stage: running || success ? job.operation : null,
    stage_state: running ? "running" : success ? "success" : failed ? "failed" : null,
    stage_progress_percent: success ? 100 : running ? 50 : 0,
    progress_percent: success ? 100 : running ? 50 : 0,
    bytes_done: null,
    bytes_total: null,
    result: success || failed
      ? {
          state,
          output_files: [],
          error: failed ? { message: "Visual regression mock failure" } : null,
        }
      : undefined,
  };
}

async function installMockApi(page: Page, mode: VisualMode = "running") {
  const jobs = new Map<string, MockJob>();
  const startRequests: Array<{ siteId: number; operation: Operation; jobId: string }> = [];
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
            ppu: {
              ppu_id: "z2-visual-01",
              facility_id: "visual-lab",
              model: "PYNQ-Z2",
              display_name: "Plasma Visual Fixture",
              site_count: 8,
              enabled_site_count: 2,
              capabilities: {
                max_supported_sites: 8,
                operations: ["erase", "program", "verify", "read"],
              },
            },
            sites: Array.from({ length: 8 }, (_, siteId) => ({
              site_id: siteId,
              enabled: siteId < 2,
              state: siteId < 2 ? "idle" : "disabled",
              current_job_id: null,
              queued_jobs: 0,
              interface: siteId < 2 ? "mock" : null,
              target: siteId < 2 ? "STM32F103C8T6" : null,
            })),
          }),
        });
        return;
      }

      const job = jobs.get(jobId);
      if (!job) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ error: { message: "job not found" } }),
        });
        return;
      }

      let state: JobState = "running";
      if (mode === "failed") state = "failed";
      else if (job.cancelRequested || mode === "cancelled") state = "cancelled";

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, job: jobPayload(job, state) }),
      });
      return;
    }

    if (request.method() === "POST" && path === "/api/jobs") {
      const body = request.postDataJSON() as { site_id: number; channel_id: number; operation: Operation };
      if (body.site_id !== body.channel_id) {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ error: { message: "site/channel compatibility fields disagree" } }),
        });
        return;
      }
      const jobId = `visual-job-${nextJobId++}`;
      const job: MockJob = {
        jobId,
        siteId: body.site_id,
        operation: body.operation,
        cancelRequested: false,
      };
      jobs.set(jobId, job);
      startRequests.push({ siteId: job.siteId, operation: job.operation, jobId });
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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "unhandled mock route" } }),
    });
  });

  return { startRequests, cancelRequests };
}

async function openConsole(page: Page, mode: VisualMode = "running") {
  const mock = await installMockApi(page, mode);
  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");
  await expect(page.getByLabel("PPU identity")).toContainText("z2-visual-01");
  await expect(page.getByRole("button", { name: "淺色" })).toHaveAttribute("aria-pressed", "true");
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  await page.addStyleTag({
    content: "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}",
  });
  return mock;
}

async function compactScreenshot(page: Page): Promise<Buffer> {
  await page.addStyleTag({
    content: ".logCard pre{visibility:hidden!important}",
  });
  const fullSize = await page.screenshot({
    fullPage: true,
    animations: "disabled",
    caret: "hide",
    scale: "css",
  });
  const compactBase64 = await page.evaluate(async sourceBase64 => {
    const image = new Image();
    image.src = `data:image/png;base64,${sourceBase64}`;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(image.naturalWidth / 4));
    canvas.height = Math.max(1, Math.round(image.naturalHeight / 4));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas 2D context unavailable");
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/webp", 0.78).split(",", 2)[1];
  }, fullSize.toString("base64"));
  return Buffer.from(compactBase64, "base64");
}

async function expectVisual(page: Page, name: string) {
  await expect(await compactScreenshot(page)).toMatchSnapshot(name, {
    threshold: 0.2,
    maxDiffPixelRatio: 0.002,
  });
}

const batchSummary = (page: Page) => page.getByLabel("選取 Site 狀態摘要");

test.describe("maximized desktop visual regression", () => {
  test("idle console", async ({ page }) => {
    await openConsole(page);
    await expect(batchSummary(page)).toContainText("待命 2");
    await expectVisual(page, "desktop-max-idle.webp");
  });

  test("batch running", async ({ page }) => {
    const mock = await openConsole(page, "running");
    await page.getByLabel("批次操作：擦除").check();
    await page.getByRole("button", { name: "批次執行：擦除" }).click();
    await expect.poll(() => mock.startRequests.length).toBe(2);
    await expect(batchSummary(page)).toContainText("工作中 2");
    await expectVisual(page, "desktop-max-batch-running.webp");
  });

  test("batch cancelled", async ({ page }) => {
    const mock = await openConsole(page, "running");
    await page.getByLabel("批次操作：擦除").check();
    await page.getByLabel("批次操作：讀取").check();
    await page.getByRole("button", { name: "批次執行：擦除、讀取" }).click();
    await expect.poll(() => mock.startRequests.length).toBe(2);
    await page.getByLabel("取消批次工作").click();
    await expect.poll(() => mock.cancelRequests.length).toBe(2);
    await expect(batchSummary(page)).toContainText("取消 2");
    await expectVisual(page, "desktop-max-batch-cancelled.webp");
  });

  test("batch failed", async ({ page }) => {
    const mock = await openConsole(page, "failed");
    await page.getByLabel("批次操作：擦除").check();
    await page.getByRole("button", { name: "批次執行：擦除" }).click();
    await expect.poll(() => mock.startRequests.length).toBe(2);
    await expect(batchSummary(page)).toContainText("失敗 2");
    await expectVisual(page, "desktop-max-batch-failed.webp");
  });
});
