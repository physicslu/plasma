import { expect, test, type Locator, type Page, type Route } from "@playwright/test";
import { factoryConsoleHeading } from "./production-console-helpers";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

async function installMockProvider(page: Page) {
  await page.route("**/api/settings/gateway", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        gateway_settings: {
          revision: 1,
          ppu_request_timeout_ms: 10_000,
          ppu_retry_count: 3,
          ppu_response_budget_ms: 47_000,
        },
      }),
    });
  });

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

async function headerSignature(locator: Locator) {
  return locator.evaluate(element => {
    const style = getComputedStyle(element);
    return {
      minHeight: style.minHeight,
      paddingTop: style.paddingTop,
      paddingRight: style.paddingRight,
      paddingBottom: style.paddingBottom,
      paddingLeft: style.paddingLeft,
      borderBottomWidth: style.borderBottomWidth,
      borderTopLeftRadius: style.borderTopLeftRadius,
      backgroundImage: style.backgroundImage,
      fontFamily: style.fontFamily,
    };
  });
}

async function titleSignature(locator: Locator) {
  return locator.evaluate(element => {
    const style = getComputedStyle(element);
    return {
      fontFamily: style.fontFamily,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      letterSpacing: style.letterSpacing,
      lineHeight: style.lineHeight,
    };
  });
}

async function toggleSignature(locator: Locator) {
  return locator.evaluate(element => {
    const style = getComputedStyle(element);
    return {
      minWidth: style.minWidth,
      minHeight: style.minHeight,
      paddingLeft: style.paddingLeft,
      paddingRight: style.paddingRight,
      borderRadius: style.borderRadius,
      borderWidth: style.borderWidth,
      fontFamily: style.fontFamily,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      lineHeight: style.lineHeight,
    };
  });
}

async function directTextGeometry(locator: Locator, text: string) {
  return locator.evaluate((element, expectedText) => {
    const textNode = Array.from(element.childNodes).find(node =>
      node.nodeType === Node.TEXT_NODE && node.textContent?.includes(expectedText),
    );
    if (!textNode) throw new Error(`Missing direct text node containing ${expectedText}`);
    const range = document.createRange();
    range.selectNodeContents(textNode);
    const textRect = range.getBoundingClientRect();
    const headerRect = element.getBoundingClientRect();
    return {
      left: textRect.left - headerRect.left,
      width: textRect.width,
      headerWidth: headerRect.width,
    };
  }, text);
}

async function expectSameSignatures(locators: Locator[], signature: (locator: Locator) => Promise<Record<string, string>>) {
  for (const locator of locators) await expect(locator).toBeVisible();
  const baseline = await signature(locators[0]);
  for (const locator of locators.slice(1)) expect(await signature(locator)).toEqual(baseline);
  return baseline;
}

test("PMode first-level Panel headers and collapse controls use one computed presentation", async ({ page }) => {
  await installMockProvider(page);
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();

  const headers = [
    page.locator(".batchSummary > .operatorPanelHeader"),
    page.locator(".productionSiteSelection > .operatorPanelHeader"),
    page.locator(".programmingJobPanel > .operatorPanelHeader"),
    page.locator(".factoryLiveStatus > .operatorPanelHeader"),
    page.locator(".productionOperatorLog > .operatorPanelHeader"),
  ];
  const titles = headers.map(header => header.locator(".operatorPanelTitle > strong"));

  const header = await expectSameSignatures(headers, headerSignature);
  const title = await expectSameSignatures(titles, titleSignature);
  expect(header.minHeight).toBe("30px");
  expect(title.fontSize).toBe("11px");
  expect(title.fontWeight).toBe("900");

  const toggle = await expectSameSignatures([
    page.locator(".selectionVisibilityButton"),
    page.locator(".programmingJobPanel .operatorPanelToggle"),
  ], toggleSignature);
  expect(toggle.minHeight).toBe("24px");
  expect(toggle.fontSize).toBe("10px");
});

test("PMode and EMode first-level Panel Header Title and Toggle computed styles are identical", async ({ page }) => {
  await installMockProvider(page);
  await page.setViewportSize({ width: 1600, height: 1000 });

  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  const productionHeader = await headerSignature(page.locator(".productionSiteSelection > .operatorPanelHeader"));
  const productionTitle = await titleSignature(page.locator(".productionSiteSelection .operatorPanelTitle > strong"));
  const productionToggle = await toggleSignature(page.locator(".selectionVisibilityButton"));

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  const headers = [
    page.locator(".batchSummary > .operatorPanelHeader"),
    page.locator(".targetingCard > header"),
    page.locator(".programmingJobPanel > .operatorPanelHeader"),
    page.locator(".liveSiteStatus > header"),
    page.locator(".engineeringOperatorLog > .operatorPanelHeader"),
  ];
  for (const header of headers) {
    await expect(header).toBeVisible();
    expect(await headerSignature(header)).toEqual(productionHeader);
  }

  const titles = [
    page.locator(".batchSummary .operatorPanelTitle > strong"),
    page.locator(".targetingCard > header"),
    page.locator(".programmingJobPanel .operatorPanelTitle > strong"),
    page.locator(".liveSiteStatus > header > span"),
    page.locator(".engineeringOperatorLog .operatorPanelTitle > strong"),
  ];
  for (const title of titles) {
    await expect(title).toBeVisible();
    expect(await titleSignature(title)).toEqual(productionTitle);
  }

  for (const toggle of [
    page.locator(".engineeringPanelToggle"),
    page.locator(".programmingJobPanel .operatorPanelToggle"),
  ]) {
    await expect(toggle).toBeVisible();
    expect(await toggleSignature(toggle)).toEqual(productionToggle);
  }

  const setupHeader = page.locator(".targetingCard > header");
  const setupTitle = await directTextGeometry(setupHeader, "SYSTEM SETUP & TARGETING");
  expect(setupTitle.left).toBeLessThan(64);
  expect(setupTitle.left).toBeLessThan(setupTitle.headerWidth / 4);

  const setupHeaderBox = await setupHeader.boundingBox();
  const setupToggleBox = await page.locator(".targetingCard .engineeringPanelToggle").boundingBox();
  expect(setupHeaderBox).not.toBeNull();
  expect(setupToggleBox).not.toBeNull();
  expect(Math.abs((setupHeaderBox!.x + setupHeaderBox!.width) - (setupToggleBox!.x + setupToggleBox!.width))).toBeLessThan(16);
});
