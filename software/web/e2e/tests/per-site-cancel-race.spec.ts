import { expect, test, type Page, type Route } from "@playwright/test";

type Operation = "erase" | "program" | "verify" | "read";

type MockJob = {
  jobId: string;
  siteId: number;
  operation: Operation;
};

function sites() {
  return Array.from({ length: 8 }, (_, index) => {
    const siteId = index + 1;
    return {
      site_id: siteId,
      enabled: siteId <= 2,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: siteId <= 2 ? "Mock" : null,
      target: siteId <= 2 ? "STM32F103C8T6" : null,
    };
  });
}

async function json(route: Route, body: unknown) {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
}

async function installPerSiteCancelRaceMock(page: Page) {
  const jobs = new Map<string, MockJob>();
  const starts: Array<{ siteId: number; operation: Operation }> = [];
  const cancelledJobs = new Set<string>();
  let nextId = 1;

  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (request.method() === "GET" && url.pathname === "/api/status" && !url.searchParams.has("job")) {
      await json(route, { ok: true, sites: sites() });
      return;
    }

    if (request.method() === "POST" && url.pathname === "/api/jobs") {
      const body = request.postDataJSON() as { site_id: number; operation: Operation };
      const jobId = `site-race-job-${nextId++}`;
      jobs.set(jobId, { jobId, siteId: body.site_id, operation: body.operation });
      starts.push({ siteId: body.site_id, operation: body.operation });
      await json(route, {
        ok: true,
        job: {
          job_id: jobId,
          site_id: body.site_id,
          operation: body.operation,
          state: "queued",
          cancel_requested: false,
          stage: null,
          stage_state: null,
          stage_progress_percent: 0,
          progress_percent: 0,
          bytes_done: null,
          bytes_total: null,
        },
      });
      return;
    }

    if (request.method() === "POST") {
      const cancelMatch = url.pathname.match(/^\/api\/jobs\/([^/]+)\/cancel$/);
      if (cancelMatch) {
        cancelledJobs.add(cancelMatch[1]);
        await json(route, { ok: true });
        return;
      }
    }

    if (request.method() === "GET" && url.pathname === "/api/status" && url.searchParams.has("job")) {
      const jobId = url.searchParams.get("job") ?? "";
      const job = jobs.get(jobId);
      if (!job) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ error: { message: "job not found" } }),
        });
        return;
      }

      const racingSiteOneErase = job.siteId === 1 && job.operation === "erase";
      const stillRunning = racingSiteOneErase && !cancelledJobs.has(jobId);
      await json(route, {
        ok: true,
        job: {
          job_id: job.jobId,
          site_id: job.siteId,
          operation: job.operation,
          state: stillRunning ? "running" : "success",
          cancel_requested: cancelledJobs.has(jobId),
          stage: job.operation,
          stage_state: stillRunning ? "running" : "success",
          stage_progress_percent: stillRunning ? 80 : 100,
          progress_percent: stillRunning ? 80 : 100,
          bytes_done: null,
          bytes_total: null,
          ...(stillRunning ? {} : { result: { state: "success", error: null } }),
        },
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "unhandled route" } }),
    });
  });

  return { starts, cancelledJobs };
}

test("per-Site cancel blocks the next operation when the current job races to SUCCESS", async ({ page }) => {
  const mock = await installPerSiteCancelRaceMock(page);
  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");

  await page.getByLabel("選擇 Programming Image Asset 檔案").setInputFiles({
    name: "site-race.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.from([0x50, 0x4c, 0x41, 0x53, 0x4d, 0x41]),
  });
  await page.getByLabel("批次操作：擦除").check();
  await page.getByLabel("批次操作：燒錄").check();
  await page.getByRole("button", { name: "批次執行：擦除、燒錄" }).click();

  const siteOneCancel = page.getByRole("button", { name: "取消 SITE 1 工作" });
  await expect(siteOneCancel).toBeEnabled();
  await siteOneCancel.click();

  const liveLog = page.getByLabel("Live job log");
  await expect(liveLog).toContainText("[SITE 1] Batch stopped · CANCEL REQUESTED · last job SUCCESS");
  await expect(liveLog).toContainText("[BATCH] PARTIAL");
  await expect(liveLog).toContainText("success: SITE 2 · cancelled: SITE 1");

  await expect.poll(() => mock.cancelledJobs.size).toBe(1);
  await expect.poll(() => mock.starts.some(start => start.siteId === 2 && start.operation === "program")).toBe(true);
  expect(mock.starts).not.toContainEqual({ siteId: 1, operation: "program" });
});
