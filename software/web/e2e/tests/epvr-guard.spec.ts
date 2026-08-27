import { expect, test, type Page, type Route } from "@playwright/test";
import {
  chooseTestTarget,
  commitProductionSites,
  factoryConsoleHeading,
  installTestDeviceCatalog,
  productionOperation,
  programmingJob,
} from "./production-console-helpers";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

function catalog(provider = "mock") {
  return {
    ok: true,
    provider,
    facility_count: 1,
    ppu_count: 1,
    site_count: 2,
    programming_asset_scope: "connection-session-and-ppu",
    facilities: [{
      facility_id: facilityId,
      display_name: provider === "mock" ? "Mock Facility 01" : "Real Facility 01",
      ppus: [{
        ppu_id: ppuId,
        display_name: provider === "mock" ? "Mock PPU 01" : "Real PPU 01",
        model: provider === "mock" ? "MOCK-PPU" : "REAL-PPU",
        site_count: 2,
        provider,
      }],
    }],
  };
}

function targetStatus(provider = "mock") {
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: provider === "mock" ? "MOCK-PPU" : "REAL-PPU",
      display_name: provider === "mock" ? "Mock PPU 01" : "Real PPU 01",
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
      interface: provider === "mock" ? "mock" : "real",
      target: provider === "mock" ? "MOCK-IC" : "REAL-IC",
    })),
  };
}

async function installEngineeringApi(page: Page, provider = "mock") {
  let jobRequests = 0;
  await installTestDeviceCatalog(page);
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
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ ok: true, session: { session_id: "0123456789abcdef0123456789abcdef", programming_asset_cache_scope: "connection-session-and-ppu", previous_session_cleared: false } }) });
      return;
    }
    if (url.pathname === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog(provider)) });
      return;
    }
    const targetMatch = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/(.*)$/.exec(url.pathname);
    if (!targetMatch) {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
      return;
    }
    const tail = targetMatch[3];
    if (request.method() === "GET" && tail === "status" && !url.searchParams.has("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(targetStatus(provider)) });
      return;
    }
    if (request.method() === "POST" && tail === "jobs") {
      jobRequests += 1;
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: { message: "readiness guard failed: unexpected job submission" } }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
  return { get jobRequests() { return jobRequests; } };
}

async function chooseFileFromButton(page: Page, buttonName: string, expectedFileName: string) {
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: buttonName, exact: true }).click();
  const chooser = await chooserPromise;
  await chooser.setFiles({ name: expectedFileName, mimeType: "application/octet-stream", buffer: Buffer.from([0x50, 0x4c, 0x41, 0x53, 0x4d, 0x41]) });
}

async function expectEngineeringV2Geometry(page: Page) {
  const toolbar = page.locator(".engineeringProgrammingV2 .programmingBatchToolbar");
  const image = toolbar.locator(".imageField");
  const operations = toolbar.locator(".programmingBatchOperations");
  const actions = toolbar.locator(".programmingActions");
  const imageBox = await image.boundingBox();
  const operationBox = await operations.boundingBox();
  const actionBox = await actions.boundingBox();
  expect(imageBox).not.toBeNull();
  expect(operationBox).not.toBeNull();
  expect(actionBox).not.toBeNull();
  expect(imageBox!.y + imageBox!.height).toBeLessThanOrEqual(operationBox!.y);
  expect(operationBox!.y + operationBox!.height).toBeLessThanOrEqual(actionBox!.y);
  await expect(toolbar.locator(".programmingFileName")).toHaveCSS("font-size", "11px");
}

test("Pmod Mock readiness uses Synthetic Image when no file is selected", async ({ page }) => {
  const api = await installEngineeringApi(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await commitProductionSites(page, facilityId, ppuId, [1]);
  await chooseTestTarget(page);
  const job = programmingJob(page);
  const readiness = job.locator(".factoryBatchStatus b");
  const execute = job.locator(".factoryStartButton");
  const fileName = job.locator(".factoryImageControl span");
  await expect(readiness).toHaveText("NO OP");
  await expect(execute).toBeDisabled();
  expect(api.jobRequests).toBe(0);
  await productionOperation(page, "P").check();
  await expect(fileName).toHaveText("Mock Synthetic Image");
  await expect(readiness).toHaveText("BATCH READY");
  await expect(execute).toBeEnabled();
  await page.getByLabel("Production Programming Image file").setInputFiles({
    name: "pmod-test.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.from([0x50, 0x4c, 0x41, 0x53, 0x4d, 0x41]),
  });
  await expect(fileName).toHaveText("pmod-test.bin");
  await expect(readiness).toHaveText("BATCH READY");
  await expect(execute).toBeEnabled();
  expect(api.jobRequests).toBe(0);
});

test("Emode Mock uses Synthetic Image and target-owned Main Flash READ", async ({ page }) => {
  const api = await installEngineeringApi(page);
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  const toolbar = page.locator(".programmingBatchToolbar");
  const readiness = toolbar.getByRole("status", { name: "Batch readiness" });
  const execute = toolbar.locator(".executeBatch");
  const fileName = toolbar.locator(".programmingFileName");
  await expect(readiness).toContainText("NO OP");
  await expect(execute).toBeDisabled();
  const operations = toolbar.locator(".programmingBatchOperations input");
  await operations.nth(3).check();
  await expect(readiness).toContainText("BATCH READY");
  await expect(execute).toBeEnabled();
  await expect(page.locator(".engineeringReadRow")).toBeHidden();
  await expect(page.getByLabel("Engineering READ offset")).toBeHidden();
  await expect(page.getByLabel("Engineering READ length")).toBeHidden();
  await operations.nth(3).uncheck();
  await operations.nth(1).check();
  await expect(fileName).toHaveText("Mock Synthetic Image");
  await expect(fileName).toHaveAttribute("data-image-source", "mock_synthetic");
  await expect(readiness).toContainText("BATCH READY");
  await expect(execute).toBeEnabled();
  await chooseFileFromButton(page, "Browse...", "emode-test.bin");
  await expect(fileName).toHaveText("emode-test.bin");
  await expect(fileName).toHaveAttribute("data-image-source", "user");
  await expect(readiness).toContainText("BATCH READY");
  await expect(execute).toBeEnabled();
  await expectEngineeringV2Geometry(page);
  expect(api.jobRequests).toBe(0);
});

test("non-Mock providers remain fail-closed without a Programming Image", async ({ page }) => {
  const api = await installEngineeringApi(page, "real");
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  const emodeToolbar = page.locator(".programmingBatchToolbar");
  await emodeToolbar.locator(".programmingBatchOperations input").nth(1).check();
  await expect(emodeToolbar.locator(".programmingFileName")).toHaveAttribute("data-image-source", "none");
  await expect(emodeToolbar.getByRole("status", { name: "Batch readiness" })).toContainText("IMAGE REQUIRED");
  await expect(emodeToolbar.locator(".executeBatch")).toBeDisabled();
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await commitProductionSites(page, facilityId, ppuId, [1]);
  await chooseTestTarget(page);
  const pmodJob = programmingJob(page);
  const program = productionOperation(page, "P");
  if (!(await program.isChecked())) await program.check();
  await expect(pmodJob.locator(".factoryImageControl span")).toHaveText("Select programming image (.bin)…");
  await expect(pmodJob.locator(".factoryBatchStatus b")).toHaveText("IMAGE REQUIRED");
  await expect(pmodJob.locator(".factoryStartButton")).toBeDisabled();
  expect(api.jobRequests).toBe(0);
});
