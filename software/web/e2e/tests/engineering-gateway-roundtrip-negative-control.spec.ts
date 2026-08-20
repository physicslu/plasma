import { expect, test } from "@playwright/test";

const siteCounts = [2, 4, 6, 8] as const;

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 3,
    ppu_count: 12,
    site_count: 60,
    firmware_scope: "connection-session-and-ppu",
    facilities: Array.from({ length: 3 }, (_, facilityIndex) => {
      const facilityNumber = facilityIndex + 1;
      const facilityId = `mock-facility-${String(facilityNumber).padStart(2, "0")}`;
      return {
        facility_id: facilityId,
        display_name: `Server Facility ${String(facilityNumber).padStart(2, "0")}`,
        ppus: siteCounts.map((siteCount, ppuIndex) => ({
          ppu_id: `${facilityId}-ppu-${String(ppuIndex + 1).padStart(2, "0")}`,
          display_name: `Server PPU ${String(ppuIndex + 1).padStart(2, "0")}`,
          model: "MOCK-PPU",
          site_count: siteCount,
          provider: "mock",
        })),
      };
    }),
  };
}

function statusFor(facilityId: string, ppuId: string) {
  const ppuNumber = Number(ppuId.slice(-2));
  const siteCount = siteCounts[ppuNumber - 1];
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: `Server PPU ${String(ppuNumber).padStart(2, "0")}`,
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

async function fulfillEngineeringRoute(route: import("@playwright/test").Route) {
  const request = route.request();
  const url = new URL(request.url());

  if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        session: {
          session_id: "00000000000000000000000000000001",
          firmware_cache_scope: "connection-session-and-ppu",
          previous_session_cleared: true,
        },
      }),
    });
    return;
  }

  if (url.pathname === "/api/engineering/targets") {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
    return;
  }

  const parts = url.pathname.split("/").filter(Boolean);
  if (request.method() === "GET" && parts.slice(5).join("/") === "api/status" && !url.searchParams.has("job")) {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(statusFor(parts[3], parts[4])),
    });
    return;
  }

  await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled" } }) });
}

test("negative control: old code loses PPU and Site subset after bad-Gateway round trip", async ({ page }) => {
  const badGateway = "http://127.0.0.1:65534";

  await page.route("**/api/engineering/**", async route => {
    const url = new URL(route.request().url());
    if (url.origin === badGateway) {
      await route.abort("failed");
      return;
    }
    await fulfillEngineeringRoute(route);
  });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();

  const gateway = page.getByLabel("Engineering Gateway URL");
  const originalGateway = await gateway.inputValue();
  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  const connect = page.locator(".engineeringGateway button[type=submit]");

  await facility.selectOption("mock-facility-03");
  await ppu.selectOption("mock-facility-03-ppu-04");
  await expect(page.getByLabel("Engineering Site selection").getByRole("checkbox")).toHaveCount(8);

  for (const siteId of [1, 3, 5, 8]) {
    await page.getByLabel(`選取 SITE ${siteId}`, { exact: true }).uncheck();
  }

  await gateway.fill(badGateway);
  await connect.click();
  await expect(page.locator(".engineeringBoundaryNote.warning")).toContainText("Failed to fetch");

  await gateway.fill(originalGateway);
  await connect.click();

  // New OAT contract. This MUST fail against old product code.
  await expect(facility).toHaveValue("mock-facility-03");
  await expect(ppu).toHaveValue("mock-facility-03-ppu-04");

  for (const selectedSiteId of [2, 4, 6, 7]) {
    await expect(page.getByLabel(`選取 SITE ${selectedSiteId}`, { exact: true })).toBeChecked();
  }
  for (const unselectedSiteId of [1, 3, 5, 8]) {
    await expect(page.getByLabel(`選取 SITE ${unselectedSiteId}`, { exact: true })).not.toBeChecked();
  }
});
