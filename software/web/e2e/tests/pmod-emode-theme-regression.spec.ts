import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppu1Id = `${facilityId}-ppu-01`;
const ppu2Id = `${facilityId}-ppu-02`;

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 2,
    site_count: 6,
    programming_asset_scope: "connection-session-and-ppu",
    facilities: [{
      facility_id: facilityId,
      display_name: "Mock Facility 01",
      ppus: [
        { ppu_id: ppu1Id, display_name: "Mock PPU 01", model: "MOCK-PPU", site_count: 2, provider: "mock" },
        { ppu_id: ppu2Id, display_name: "Mock PPU 02", model: "MOCK-PPU", site_count: 4, provider: "mock" },
      ],
    }],
  };
}

function targetStatus(ppuId: string) {
  const siteCount = ppuId === ppu1Id ? 2 : 4;
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: ppuId === ppu1Id ? "Mock PPU 01" : "Mock PPU 02",
      site_count: siteCount,
      enabled_site_count: siteCount,
      capabilities: { max_supported_sites: siteCount, operations: ["erase", "program", "verify", "read"] },
    },
    sites: Array.from({ length: siteCount }, (_, index) => ({
      site_id: index + 1,
      enabled: true,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: "mock",
      target: "MOCK-IC",
    })),
  };
}

async function installMockProvider(page: Page) {
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
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }

    const targetMatch = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/status$/.exec(url.pathname);
    if (targetMatch && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(targetStatus(decodeURIComponent(targetMatch[2]))) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

async function background(page: Page, selector: string) {
  return page.locator(selector).first().evaluate(element => getComputedStyle(element).backgroundColor);
}

async function fileButtonStyle(page: Page, selector: string) {
  return page.locator(selector).evaluate(element => {
    const style = getComputedStyle(element);
    return {
      height: style.height,
      paddingLeft: style.paddingLeft,
      paddingRight: style.paddingRight,
      borderRadius: style.borderRadius,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      color: style.color,
      background: style.backgroundColor,
      borderColor: style.borderColor,
    };
  });
}

test("Pmod dark theme covers operator surfaces and keeps file picker before EPVR", async ({ page }) => {
  await installMockProvider(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();

  await page.getByRole("checkbox", { name: `${facilityId} ${ppu1Id} SITE-01` }).check();
  await page.getByRole("button", { name: "確定選取", exact: true }).click();
  await expect(page.locator(`[data-production-target="${facilityId}::${ppu1Id}"]`)).toBeVisible();

  const toolbarOrder = await page.locator(".productionBatchToolbar").evaluate(element => (
    Array.from(element.children).map(child => child.className)
  ));
  expect(toolbarOrder.slice(0, 3)).toEqual([
    "productionImagePicker programmingBatchFile",
    "batchOperations programmingBatchOperations",
    "productionBatchActions programmingBatchActions",
  ]);

  const toolbarBox = await page.locator(".productionBatchToolbar").boundingBox();
  const imageBox = await page.locator(".programmingBatchFile").boundingBox();
  const operationsBox = await page.locator(".programmingBatchOperations").boundingBox();
  const actionsBox = await page.locator(".programmingBatchActions").boundingBox();
  expect(toolbarBox).not.toBeNull();
  expect(imageBox).not.toBeNull();
  expect(operationsBox).not.toBeNull();
  expect(actionsBox).not.toBeNull();
  expect(imageBox!.x).toBeLessThanOrEqual(toolbarBox!.x + 12);
  expect(imageBox!.x + imageBox!.width).toBeGreaterThanOrEqual(toolbarBox!.x + toolbarBox!.width - 12);
  expect(imageBox!.y + imageBox!.height).toBeLessThanOrEqual(Math.min(operationsBox!.y, actionsBox!.y));
  expect(actionsBox!.x).toBeGreaterThanOrEqual(operationsBox!.x + operationsBox!.width);

  const theme = page.getByRole("group", { name: "Theme" });
  await theme.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await expect.poll(() => background(page, ".productionPrototypePage")).toBe("rgb(7, 17, 29)");
  for (const selector of [
    ".fpsSelector",
    ".productionBatchToolbar",
    ".productionRuntimeBoard",
    ".productionPpuPrototype",
    ".productionSitePrototype",
  ]) {
    await expect.poll(() => background(page, selector)).toBe("rgb(12, 25, 39)");
  }

  const headingColor = await page.locator(".productionPrototypeHeading h1").evaluate(element => getComputedStyle(element).color);
  expect(headingColor).toBe("rgb(233, 243, 248)");
});

test("Emode stays dense and shares the Pmod file picker and dark operator palette", async ({ page }) => {
  await installMockProvider(page);
  await page.goto("/fleet");
  const theme = page.getByRole("group", { name: "Theme" });
  const darkButton = theme.getByRole("button", { name: "Dark", exact: true });
  await darkButton.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(darkButton).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("plasma-theme"))).toBe("dark");

  const pmodButtonStyle = await fileButtonStyle(page, ".productionBrowseButton");

  await page.goto("/engineering");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.locator(".engineeringWorkspace nav button").nth(2).click();
  const ppuSelect = page.getByLabel("Engineering PPU", { exact: true });
  await expect(ppuSelect).toBeVisible();

  const selectStyle = await ppuSelect.evaluate(element => {
    const style = getComputedStyle(element);
    const optionStyle = getComputedStyle((element as HTMLSelectElement).options[0]);
    return {
      background: style.backgroundColor,
      color: style.color,
      colorScheme: style.colorScheme,
      optionBackground: optionStyle.backgroundColor,
      optionColor: optionStyle.color,
    };
  });
  expect(selectStyle.background).toBe("rgb(12, 25, 39)");
  expect(selectStyle.color).toBe("rgb(233, 243, 248)");
  expect(selectStyle.colorScheme).toContain("dark");
  expect(selectStyle.optionBackground).toBe("rgb(12, 25, 39)");
  expect(selectStyle.optionColor).toBe("rgb(233, 243, 248)");

  const emodeButtonStyle = await fileButtonStyle(page, ".engineeringBrowseButton");
  expect(emodeButtonStyle).toEqual(pmodButtonStyle);

  const browse = await page.locator(".engineeringBrowseButton").boundingBox();
  const imageText = await page.locator(".engineeringProgramming .programmingFileName").boundingBox();
  expect(browse).not.toBeNull();
  expect(imageText).not.toBeNull();
  expect(browse!.x).toBeLessThan(imageText!.x);
  expect(imageText!.x - (browse!.x + browse!.width)).toBeGreaterThanOrEqual(0);
  expect(imageText!.x - (browse!.x + browse!.width)).toBeLessThanOrEqual(16);

  const toolbar = await page.locator(".engineeringExecutionToolbar").boundingBox();
  const header = await page.locator(".engineeringProgrammingHeader").boundingBox();
  const topology = await page.locator(".engineeringProgramming .batchTopologySummary").boundingBox();
  const controls = await page.locator(".engineeringProgramming .unifiedBatchControlStack").boundingBox();
  const activeSummary = await page.locator(".engineeringProgramming .activeFpsSummary").boundingBox();
  const targetSelector = await page.locator(".engineeringTargetSelector").boundingBox();
  const sourceNote = await page.locator(".engineeringBoundaryNote").last().boundingBox();
  const sitePanel = await page.locator(".engineeringSelectorPanel").boundingBox();
  for (const box of [toolbar, header, topology, controls, activeSummary, targetSelector, sourceNote, sitePanel]) expect(box).not.toBeNull();
  expect(header!.height).toBeLessThanOrEqual(80);
  expect(toolbar!.height).toBeLessThanOrEqual(140);
  expect(topology!.height).toBeLessThanOrEqual(72);
  expect(controls!.height).toBeLessThanOrEqual(230);
  expect(activeSummary!.height).toBeLessThanOrEqual(76);
  expect(activeSummary!.y + activeSummary!.height - header!.y).toBeLessThanOrEqual(490);
  expect(targetSelector!.height).toBeLessThanOrEqual(72);
  expect(sourceNote!.height).toBeLessThanOrEqual(42);
  expect(sitePanel!.height).toBeLessThanOrEqual(118);
  expect(sitePanel!.y + sitePanel!.height - header!.y).toBeLessThanOrEqual(650);
});