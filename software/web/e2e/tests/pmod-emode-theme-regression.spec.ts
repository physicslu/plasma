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
        body: JSON.stringify({ ok: true, session: {
          session_id: "0123456789abcdef0123456789abcdef",
          programming_asset_cache_scope: "connection-session-and-ppu",
          previous_session_cleared: false,
        } }),
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
  for (const selector of [".fpsSelector", ".productionBatchToolbar", ".productionRuntimeBoard", ".productionPpuPrototype", ".productionSitePrototype"]) {
    await expect.poll(() => background(page, selector)).toBe("rgb(12, 25, 39)");
  }
  const headingColor = await page.locator(".productionPrototypeHeading h1").evaluate(element => getComputedStyle(element).color);
  expect(headingColor).toBe("rgb(233, 243, 248)");
});

test("Emode v2 stays dense with centered Batch status and target-owned READ", async ({ page }) => {
  await installMockProvider(page);
  await page.goto("/fleet");
  const theme = page.getByRole("group", { name: "Theme" });
  const darkButton = theme.getByRole("button", { name: "Dark", exact: true });
  await darkButton.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(darkButton).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("plasma-theme"))).toBe("dark");

  await page.goto("/engineering");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator(".engineeringSidebar")).toBeVisible();
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

  const browseStyle = await page.locator(".engineeringBrowseButton").evaluate(element => {
    const style = getComputedStyle(element);
    return {
      height: Number.parseFloat(style.height),
      radius: style.borderRadius,
      color: style.color,
      background: style.backgroundColor,
    };
  });
  expect(browseStyle.height).toBeGreaterThanOrEqual(30);
  expect(browseStyle.radius).toBe("7px");
  expect(browseStyle.color).toBe("rgb(233, 243, 248)");
  expect(browseStyle.background).not.toBe("rgba(0, 0, 0, 0)");

  const browse = await page.locator(".engineeringBrowseButton").boundingBox();
  const imageText = await page.locator(".engineeringProgramming .programmingFileName").boundingBox();
  expect(browse).not.toBeNull();
  expect(imageText).not.toBeNull();
  expect(imageText!.x).toBeLessThan(browse!.x);
  expect(Math.abs(browse!.x - (imageText!.x + imageText!.width))).toBeLessThanOrEqual(2);

  const repeat = await page.getByLabel("Repeat Count").boundingBox();
  const retry = await page.getByLabel("Site Retry Limit").boundingBox();
  const stopPolicy = await page.getByLabel("Engineering Stop Policy").boundingBox();
  const operations = await page.locator(".programmingBatchOperations").boundingBox();
  const policy = await page.locator(".engineeringPolicyRow").boundingBox();
  const readiness = await page.locator(".batchReadiness").boundingBox();
  const jobBody = await page.locator(".programmingJobBody").boundingBox();
  const actions = await page.locator(".programmingActions").boundingBox();
  const startButton = await page.locator(".programmingActions .startProgramming").boundingBox();
  const abortButton = await page.locator(".programmingActions .abortProgramming").boundingBox();
  for (const box of [repeat, retry, stopPolicy, operations, policy, readiness, jobBody, actions, startButton, abortButton]) expect(box).not.toBeNull();

  const policyControlY = [repeat!.y, retry!.y, stopPolicy!.y];
  expect(Math.max(...policyControlY) - Math.min(...policyControlY)).toBeLessThanOrEqual(2);
  expect(Math.abs(operations!.y - policy!.y)).toBeLessThanOrEqual(6);
  const actionCenterY = actions!.y + actions!.height / 2;
  const readinessCenterY = readiness!.y + readiness!.height / 2;
  expect(Math.abs(actionCenterY - readinessCenterY)).toBeLessThanOrEqual(3);
  expect(actions!.width).toBeGreaterThanOrEqual(jobBody!.width - 40);
  expect(Math.abs(startButton!.width - abortButton!.width)).toBeLessThanOrEqual(2);
  expect(Math.abs(startButton!.x - actions!.x)).toBeLessThanOrEqual(2);
  expect(Math.abs((abortButton!.x + abortButton!.width) - (actions!.x + actions!.width))).toBeLessThanOrEqual(2);
  expect(startButton!.x + startButton!.width).toBeLessThan(readiness!.x);
  expect(readiness!.x + readiness!.width).toBeLessThan(abortButton!.x);

  await page.getByLabel("Engineering batch read").check();
  await expect(page.locator(".engineeringReadRow")).toBeHidden();
  await expect(page.getByLabel("Engineering READ offset")).toBeHidden();
  await expect(page.getByLabel("Engineering READ length")).toBeHidden();

  const passKpi = await page.locator('[data-kpi="pass"]').evaluate(element => {
    const style = getComputedStyle(element);
    return { background: style.backgroundColor, edge: style.borderLeftColor };
  });
  const failKpi = await page.locator('[data-kpi="fail"]').evaluate(element => {
    const style = getComputedStyle(element);
    return { background: style.backgroundColor, edge: style.borderLeftColor };
  });
  expect(passKpi.edge).toBe("rgb(21, 128, 61)");
  expect(failKpi.edge).toBe("rgb(220, 38, 38)");
  expect(passKpi.background).not.toBe(failKpi.background);

  const header = await page.locator(".engineeringProgrammingV2Header").boundingBox();
  const kpis = await page.locator(".productionProgrammingKpis").boundingBox();
  const workflow = await page.locator(".productionProgrammingWorkflow").boundingBox();
  const setup = await page.locator(".targetingCard").boundingBox();
  const job = await page.locator(".programmingJobCard").boundingBox();
  const liveStatus = await page.locator(".liveSiteStatus").boundingBox();
  for (const box of [header, kpis, workflow, setup, job, liveStatus]) expect(box).not.toBeNull();
  expect(header!.height).toBeLessThanOrEqual(90);
  expect(kpis!.height).toBeLessThanOrEqual(180);
  expect(job!.height).toBeLessThanOrEqual(420);
  expect(setup!.y + setup!.height).toBeLessThanOrEqual(job!.y);
  expect(job!.y + job!.height).toBeLessThanOrEqual(liveStatus!.y);
  await expect(page.locator(".recentEvents")).toBeHidden();
});