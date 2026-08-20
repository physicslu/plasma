import { expect, test, type Page, type Route } from "@playwright/test";

const apiBase = "https://plasma.open4th.com";

function canonicalStatus() {
  return {
    ok: true,
    ppu: {
      ppu_id: "observability-ppu-01",
      facility_id: "observability-facility-01",
      model: "MOCK-PPU",
      display_name: "Observability PPU 01",
      site_count: 8,
      enabled_site_count: 2,
      capabilities: {
        max_supported_sites: 8,
        operations: ["erase", "program", "verify", "read"],
      },
    },
    sites: Array.from({ length: 8 }, (_, index) => ({
      site_id: index + 1,
      enabled: index < 2,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: index < 2 ? "Mock" : null,
      target: index < 2 ? "STM32F103C8T6" : null,
    })),
  };
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installStatusMock(page: Page) {
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "GET" && url.pathname === "/api/status" && !url.searchParams.has("job")) {
      await fulfillJson(route, canonicalStatus());
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled mock route" } }) });
  });
}

test("restored default Gateway URL does not emit a second connected event", async ({ page }) => {
  await page.addInitScript(({ storedApiBase }) => {
    window.localStorage.setItem("plasma-api-base", storedApiBase);
    window.localStorage.setItem("plasma-api-base-version", "2");
  }, { storedApiBase: apiBase });
  await installStatusMock(page);

  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");

  const liveLog = page.getByLabel("Live job log");
  await expect(liveLog).toContainText(`Plasma Web REST Gateway connected · ${apiBase}`);

  await page.waitForTimeout(1_750);

  const connectedLines = liveLog.locator("span").filter({ hasText: "Plasma Web REST Gateway connected" });
  await expect(connectedLines).toHaveCount(1);
  expect(await page.evaluate(() => window.localStorage.getItem("plasma-api-base"))).toBeNull();
});

test("operator-requested cancellation stays INFO even when backend includes an error detail", async ({ page }) => {
  let cancelled = false;
  const jobId = "observability-cancel-job";

  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (request.method() === "GET" && url.pathname === "/api/status" && !url.searchParams.has("job")) {
      await fulfillJson(route, canonicalStatus());
      return;
    }

    if (request.method() === "POST" && url.pathname === "/api/jobs") {
      const body = request.postDataJSON() as { site_id: number };
      expect(body.site_id).toBe(1);
      await fulfillJson(route, {
        ok: true,
        job: {
          job_id: jobId,
          site_id: 1,
          operation: "erase",
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

    if (request.method() === "POST" && url.pathname === `/api/jobs/${jobId}/cancel`) {
      cancelled = true;
      await fulfillJson(route, { ok: true });
      return;
    }

    if (request.method() === "GET" && url.pathname === "/api/status" && url.searchParams.get("job") === jobId) {
      await fulfillJson(route, {
        ok: true,
        job: {
          job_id: jobId,
          site_id: 1,
          operation: "erase",
          state: cancelled ? "cancelled" : "running",
          cancel_requested: cancelled,
          stage: "erase",
          stage_state: cancelled ? "cancelled" : "running",
          stage_progress_percent: cancelled ? 50 : 25,
          progress_percent: cancelled ? 50 : 25,
          bytes_done: null,
          bytes_total: null,
          result: cancelled
            ? { state: "cancelled", error: { message: "job was cancelled" } }
            : undefined,
        },
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled mock route" } }) });
  });

  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  await page.getByLabel("SITE 1 擦除").click();
  await expect(page.getByLabel("取消 SITE 1 工作")).toBeEnabled();
  await page.getByLabel("取消 SITE 1 工作").click();

  const cancelledLine = page.getByLabel("Live job log").locator("span").filter({ hasText: `${jobId} · CANCELLED` });
  await expect(cancelledLine).toHaveCount(1);
  await expect(cancelledLine).toHaveAttribute("data-level", "info");
  await expect(cancelledLine).not.toContainText("[ERROR]");
  await expect(cancelledLine).not.toContainText("job was cancelled");
});