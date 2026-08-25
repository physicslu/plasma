import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

async function installEngineeringApi(page: Page) {
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
            ppus: [{
              ppu_id: ppuId,
              display_name: "Mock PPU 01",
              model: "MOCK-PPU",
              site_count: 2,
              provider: "mock",
            }],
          }],
        }),
      });
      return;
    }

    const targetMatch = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/status$/.exec(url.pathname);
    if (targetMatch && request.method() === "GET") {
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

test("Engineering labels are readable without reviving duplicate card headers", async ({ page }) => {
  await installEngineeringApi(page);
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  for (const selector of [".targetingCard > header", ".programmingJobCard > header"]) {
    const header = page.locator(selector);
    await expect(header).toBeVisible();
    expect(await header.evaluate(element => getComputedStyle(element).fontSize)).toBe("0px");
  }

  const setupPseudo = await page.locator(".targetingCard > header").evaluate(element => ({
    content: getComputedStyle(element, "::before").content,
    fontSize: getComputedStyle(element, "::before").fontSize,
  }));
  expect(setupPseudo.content).toContain("SYSTEM SETUP");
  expect(setupPseudo.fontSize).toBe("12px");

  const jobPseudo = await page.locator(".programmingJobCard > header").evaluate(element => ({
    content: getComputedStyle(element, "::before").content,
    fontSize: getComputedStyle(element, "::before").fontSize,
  }));
  expect(jobPseudo.content).toContain("PROGRAMMING JOB");
  expect(jobPseudo.fontSize).toBe("12px");

  const setupLabels = page.locator(".targetingCard .workflowField > span");
  await expect(setupLabels).toHaveCount(2);
  for (let index = 0; index < 2; index += 1) {
    expect(await setupLabels.nth(index).evaluate(element => getComputedStyle(element).fontSize)).toBe("12px");
  }

  const jobLabels = page.locator(".programmingJobBody .jobRow > strong");
  await expect(jobLabels).toHaveCount(4);
  for (let index = 0; index < 4; index += 1) {
    expect(await jobLabels.nth(index).evaluate(element => getComputedStyle(element).fontSize)).toBe("12px");
  }

  const siteNames = page.locator(".channelTable tbody td:nth-child(2) b");
  await expect(siteNames).toHaveCount(2);
  await expect(siteNames.nth(0)).toHaveText("SITE-01");
  await expect(siteNames.nth(1)).toHaveText("SITE-02");
  for (let index = 0; index < 2; index += 1) {
    expect(await siteNames.nth(index).evaluate(element => getComputedStyle(element).fontSize)).toBe("13px");
  }
});
