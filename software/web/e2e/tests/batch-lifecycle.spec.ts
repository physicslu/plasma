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

async function installMock(page: Page) {
  const jobs = new Map<string, MockJob>();
  const starts: Array<{ siteId: number; operation: Operation }> = [];
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
      const jobId = `barrier-job-${nextId++}`;
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

    if (request.method() === "GET" && url.pathname === "/api/status" && url.searchParams.has("job")) {
      const jobId = url.searchParams.get("job") ?? "";
      const job = jobs.get(jobId);
      if (!job) {
        await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "job not found" } }) });
        return;
      }
      await json(route, {
        ok: true,
        job: {
          job_id: job.jobId,
          site_id: job.siteId,
          operation: job.operation,
          state: "success",
          cancel_requested: false,
          stage: job.operation,
          stage_state: "success",
          stage_progress_percent: 100,
          progress_percent: 100,
          bytes_done: null,
          bytes_total: null,
          result: { state: "success", error: null },
        },
      });
      return;
    }

    if (request.method() === "POST" && /\/api\/jobs\/[^/]+\/cancel$/.test(url.pathname)) {
      await json(route, { ok: true });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled route" } }) });
  });

  return { starts };
}

test("cancel barrier blocks PROGRAM before transport dispatch", async ({ page }) => {
  const mock = await installMock(page);
  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");

  await page.getByLabel("選擇 Programming Image Asset 檔案").setInputFiles({
    name: "barrier.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.from([0x50, 0x4c, 0x41, 0x53, 0x4d, 0x41]),
  });
  await page.getByLabel("批次操作：擦除").check();
  await page.getByLabel("批次操作：燒錄").check();

  await page.evaluate(() => {
    const liveLog = document.querySelector('pre[aria-label="Live job log"]');
    if (!liveLog) throw new Error("Live job log not found");
    const observer = new MutationObserver(() => {
      if (!liveLog.textContent?.includes("Batch PROGRAM")) return;
      const cancel = document.querySelector('button[aria-label="取消批次工作"]') as HTMLButtonElement | null;
      if (!cancel || cancel.disabled) return;
      observer.disconnect();
      cancel.click();
    });
    observer.observe(liveLog, { childList: true, subtree: true, characterData: true });
  });

  await page.getByRole("button", { name: "批次執行：擦除、燒錄" }).click();

  const liveLog = page.getByLabel("Live job log");
  await expect(liveLog).toContainText("[BATCH] CANCELLED");
  await expect(liveLog).toContainText("before PROGRAM dispatch");
  await expect(liveLog).toContainText("[BATCH] CANCEL requested · submitting:");
  await expect(liveLog).toContainText("active jobs:");

  await expect.poll(() => mock.starts.length).toBe(2);
  expect(mock.starts).toEqual([
    { siteId: 1, operation: "erase" },
    { siteId: 2, operation: "erase" },
  ]);
});
