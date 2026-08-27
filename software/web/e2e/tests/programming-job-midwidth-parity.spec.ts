import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

const catalog = {
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
};

const status = {
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
};

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
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog) });
      return;
    }
    if (/\/api\/engineering\/targets\/[^/]+\/[^/]+\/api\/status$/.test(url.pathname) && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(status) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

async function presentation(page: Page, selector: string) {
  return page.locator(selector).first().evaluate(element => {
    const style = getComputedStyle(element);
    return {
      height: style.height,
      minHeight: style.minHeight,
      padding: style.padding,
      border: style.border,
      radius: style.borderRadius,
      background: style.backgroundImage === "none" ? style.backgroundColor : style.backgroundImage,
      color: style.color,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      display: style.display,
    };
  });
}

test("PMode and EMode keep one Programming Job control presentation through the 761-980px container range", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 900 });
  await page.addInitScript(() => sessionStorage.clear());
  await installMockProvider(page);

  await page.goto("/fleet");
  await expect(page.locator(".factoryOperationChecks label").first()).toBeVisible();

  const pOperation = await presentation(page, ".factoryOperationChecks label");
  const pCheckbox = await presentation(page, ".factoryOperationChecks input");
  const pStart = await presentation(page, ".factoryStartButton");
  const pAbort = await presentation(page, ".factoryAbortButton");
  const pStatus = await presentation(page, ".factoryBatchStatus");

  await page.goto("/engineering");
  await page.locator(".engineeringWorkspace nav button").nth(2).click();
  await expect(page.locator(".programmingBatchOperations .operationChecks label").first()).toBeVisible();

  const container = await page.locator(".engineeringProgrammingV2").boundingBox();
  expect(container).not.toBeNull();
  expect(container!.width).toBeGreaterThan(760);
  expect(container!.width).toBeLessThanOrEqual(980);

  expect(await presentation(page, ".programmingBatchOperations .operationChecks label")).toEqual(pOperation);
  expect(await presentation(page, ".programmingBatchOperations .operationChecks input")).toEqual(pCheckbox);
  expect(await presentation(page, ".programmingActions .startProgramming")).toEqual(pStart);
  expect(await presentation(page, ".programmingActions .abortProgramming")).toEqual(pAbort);

  /* Status tone may differ because each mode can be in a different semantic
     state. Geometry and typography are the cross-mode invariant. */
  const eStatus = await presentation(page, ".batchReadiness");
  expect(eStatus.height).toBe(pStatus.height);
  expect(eStatus.minHeight).toBe(pStatus.minHeight);
  expect(eStatus.padding).toBe(pStatus.padding);
  expect(eStatus.radius).toBe(pStatus.radius);
  expect(eStatus.fontSize).toBe(pStatus.fontSize);
  expect(eStatus.fontWeight).toBe(pStatus.fontWeight);
  expect(eStatus.display).toBe(pStatus.display);

  const actions = await page.locator(".programmingActions").boundingBox();
  const start = await page.locator(".programmingActions .startProgramming").boundingBox();
  const readiness = await page.locator(".batchReadiness").boundingBox();
  const abort = await page.locator(".programmingActions .abortProgramming").boundingBox();
  for (const box of [actions, start, readiness, abort]) expect(box).not.toBeNull();

  expect(Math.abs(start!.width - abort!.width)).toBeLessThanOrEqual(2);
  expect(Math.abs(readiness!.width - 160)).toBeLessThanOrEqual(2);
  expect(start!.x + start!.width).toBeLessThan(readiness!.x);
  expect(readiness!.x + readiness!.width).toBeLessThan(abort!.x);

  const centerY = (box: NonNullable<typeof start>) => box.y + box.height / 2;
  expect(Math.abs(centerY(start!) - centerY(readiness!))).toBeLessThanOrEqual(2);
  expect(Math.abs(centerY(abort!) - centerY(readiness!))).toBeLessThanOrEqual(2);
  expect(Math.abs(start!.x - actions!.x)).toBeLessThanOrEqual(2);
  expect(Math.abs((abort!.x + abort!.width) - (actions!.x + actions!.width))).toBeLessThanOrEqual(2);
});
