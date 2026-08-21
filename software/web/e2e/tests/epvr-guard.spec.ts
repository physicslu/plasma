import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

function catalog() {
  return {
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
  };
}

function targetStatus() {
  return {
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
}

async function installEngineeringApi(page: Page) {
  let jobRequests = 0;

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

    const targetMatch = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/(.*)$/.exec(url.pathname);
    if (!targetMatch) {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
      return;
    }

    const tail = targetMatch[3];
    if (request.method() === "GET" && tail === "status" && !url.searchParams.has("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(targetStatus()) });
      return;
    }

    if (request.method() === "POST" && tail === "jobs") {
      jobRequests += 1;
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: { message: "empty-EPVR guard failed: unexpected job submission" } }),
      });
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
  await chooser.setFiles({
    name: expectedFileName,
    mimeType: "application/octet-stream",
    buffer: Buffer.from([0x50, 0x4c, 0x41, 0x53, 0x4d, 0x41]),
  });
}

test("Pmod Browse is explicit and empty EPVR shows a warning without submitting jobs", async ({ page }) => {
  const api = await installEngineeringApi(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();

  await page.getByRole("checkbox", { name: `${facilityId} ${ppuId} SITE-01`, exact: true }).check();
  await page.getByRole("button", { name: "確定選取", exact: true }).click();
  await expect(page.locator(`[data-production-target="${facilityId}::${ppuId}"] [data-production-site="1"]`)).toBeVisible();

  const browse = page.getByRole("button", { name: "選擇檔案", exact: true });
  await expect(browse).toBeVisible();
  await chooseFileFromButton(page, "選擇檔案", "pmod-test.bin");
  await expect(page.locator(".productionImagePicker")).toContainText("pmod-test.bin");

  await page.locator(".executeBatchButton").click();
  await expect(page.getByRole("alert")).toContainText(
    "未選擇任何操作。請至少選擇 Erase、Program、Verify 或 Read 其中一項。",
  );
  expect(api.jobRequests).toBe(0);
});

test("Emode Browse is explicit and empty EPVR shows a warning without submitting jobs", async ({ page }) => {
  const api = await installEngineeringApi(page);
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  const browse = page.getByRole("button", { name: "瀏覽檔案", exact: true });
  await expect(browse).toBeVisible();
  await chooseFileFromButton(page, "瀏覽檔案", "emode-test.bin");
  await expect(page.locator(".compactFile")).toContainText("emode-test.bin");

  const execute = page.locator(".executeBatch");
  await expect(execute).toBeEnabled();
  await execute.click();
  await expect(page.getByRole("alert")).toContainText(
    "未選擇任何操作。請至少選擇 Erase、Program、Verify 或 Read 其中一項。",
  );
  expect(api.jobRequests).toBe(0);
});
