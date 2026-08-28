import { expect, test, type Locator, type Page, type Route } from "@playwright/test";
import { programmingJob, programmingJobField } from "./programming-job-test-helpers";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

async function installMockProvider(page: Page) {
  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, session: {
          session_id: "0123456789abcdef0123456789abcdef",
          programming_asset_cache_scope: "connection-session-and-ppu",
          previous_session_cleared: false,
        } }),
      });
      return;
    }

    if (url.pathname === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          provider: "mock",
          facility_count: 1,
          ppu_count: 1,
          site_count: 2,
          programming_asset_scope: "connection-session-and-ppu",
          facilities: [{
            facility_id: facilityId,
            display_name: "Mock Facility 01",
            ppus: [{ ppu_id: ppuId, display_name: "Mock PPU 01", model: "MOCK-PPU", site_count: 2, provider: "mock" }],
          }],
        }),
      });
      return;
    }

    if (url.pathname === `/api/engineering/targets/${facilityId}/${ppuId}/api/status` && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
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
        }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

async function rowMetrics(row: Locator) {
  return row.evaluate(element => {
    const children = Array.from(element.children);
    const label = children[0] as HTMLElement;
    const control = children[1] as HTMLElement;
    const rowBox = element.getBoundingClientRect();
    const labelBox = label.getBoundingClientRect();
    const controlBox = control.getBoundingClientRect();
    const style = getComputedStyle(label);
    return {
      gap: controlBox.left - labelBox.right,
      controlX: controlBox.left,
      controlOffset: controlBox.left - rowBox.left,
      textAlign: style.textAlign,
      justifySelf: style.justifySelf,
    };
  });
}

function expectRightAlignedRail(metric: Awaited<ReturnType<typeof rowMetrics>>, minOffset: number, maxOffset: number) {
  expect(metric.gap).toBeGreaterThanOrEqual(6);
  expect(metric.gap).toBeLessThanOrEqual(10);
  expect(metric.controlOffset).toBeGreaterThanOrEqual(minOffset);
  expect(metric.controlOffset).toBeLessThanOrEqual(maxOffset);
  expect(metric.textAlign).toBe("right");
  expect(metric.justifySelf).toBe("end");
}

test("Engineering targeting keeps its compact rail while Programming Job keeps the shared canonical rail", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await installMockProvider(page);
  await page.goto("/engineering");
  await page.locator(".engineeringWorkspace nav button").nth(2).click();
  await expect(page.getByLabel("Engineering PPU", { exact: true })).toBeVisible();

  const facility = await rowMetrics(page.locator(".targetingCard .workflowField").nth(0));
  const ppu = await rowMetrics(page.locator(".targetingCard .workflowField").nth(1));
  const job = programmingJob(page, "engineering");
  const target = await rowMetrics(programmingJobField(job, "target"));
  const image = await rowMetrics(programmingJobField(job, "image"));
  const operations = await rowMetrics(programmingJobField(job, "operations"));
  const policy = await rowMetrics(programmingJobField(job, "policy"));

  for (const metric of [facility, ppu]) {
    expectRightAlignedRail(metric, 118, 122);
  }
  for (const metric of [target, image, operations, policy]) {
    expectRightAlignedRail(metric, 134, 138);
  }

  expect(Math.abs(target.controlX - operations.controlX)).toBeLessThanOrEqual(2);
  expect(Math.abs(image.controlX - policy.controlX)).toBeLessThanOrEqual(2);
});
