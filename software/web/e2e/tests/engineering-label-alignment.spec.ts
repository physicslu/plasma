import { expect, test, type Page, type Route } from "@playwright/test";

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

async function rowMetrics(page: Page, selector: string, index: number) {
  return page.locator(selector).nth(index).evaluate(row => {
    const children = Array.from(row.children);
    const label = children[0] as HTMLElement;
    const control = children[1] as HTMLElement;
    const labelBox = label.getBoundingClientRect();
    const controlBox = control.getBoundingClientRect();
    const style = getComputedStyle(label);
    return {
      gap: controlBox.left - labelBox.right,
      controlX: controlBox.left,
      textAlign: style.textAlign,
      justifySelf: style.justifySelf,
    };
  });
}

test("Engineering labels sit close to controls on a shared desktop baseline", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await installMockProvider(page);
  await page.goto("/engineering");
  await page.locator(".engineeringWorkspace nav button").nth(2).click();
  await expect(page.getByLabel("Engineering PPU", { exact: true })).toBeVisible();

  const facility = await rowMetrics(page, ".targetingCard .workflowField", 0);
  const ppu = await rowMetrics(page, ".targetingCard .workflowField", 1);
  const target = await rowMetrics(page, ".programmingJobBody > .jobRow", 0);
  const image = await rowMetrics(page, ".programmingJobBody > .jobRow", 1);
  const operations = await rowMetrics(page, ".programmingJobBody > .jobRow", 2);
  const policy = await rowMetrics(page, ".programmingJobBody > .jobRow", 3);

  for (const metric of [facility, ppu, target, image, operations, policy]) {
    expect(metric.gap).toBeGreaterThanOrEqual(6);
    expect(metric.gap).toBeLessThanOrEqual(10);
    expect(metric.textAlign).toBe("right");
    expect(metric.justifySelf).toBe("end");
  }

  expect(Math.abs(target.controlX - operations.controlX)).toBeLessThanOrEqual(2);
  expect(Math.abs(image.controlX - policy.controlX)).toBeLessThanOrEqual(2);
});
