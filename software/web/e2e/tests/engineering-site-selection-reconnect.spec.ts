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

async function openProgramming(page: import("@playwright/test").Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
}

async function expectCheckedSites(page: import("@playwright/test").Page, expected: number[]) {
  const checkboxes = page.getByLabel("Engineering Site selection").getByRole("checkbox");
  const count = await checkboxes.count();
  for (let index = 0; index < count; index += 1) {
    const siteId = index + 1;
    if (expected.includes(siteId)) await expect(checkboxes.nth(index)).toBeChecked();
    else await expect(checkboxes.nth(index)).not.toBeChecked();
  }
}

test("operator reconnect keeps explicit Site selection and polling never turns explicit zero back into all", async ({ page }) => {
  let providerOnline = true;
  let sessionRequests = 0;
  let statusRequests = 0;

  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      if (!providerOnline) {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ error: { message: "operator simulated provider outage" } }),
        });
        return;
      }
      sessionRequests += 1;
      const body = request.postDataJSON() as { previous_session_id?: string };
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: String(sessionRequests).padStart(32, "0"),
            firmware_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: Boolean(body.previous_session_id),
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
      statusRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(statusFor(parts[3], parts[4])),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "unhandled Engineering route" } }),
    });
  });

  await openProgramming(page);

  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  const connect = page.locator(".engineeringGateway button[type=submit]");

  await facility.selectOption("mock-facility-01");
  await ppu.selectOption("mock-facility-01-ppu-03");
  await expect(page.getByLabel("Engineering Site selection").getByRole("checkbox")).toHaveCount(6);

  // Mirror the operator's manual pattern: keep SITE 1 / 5 / 6 only.
  await page.getByLabel("選取 SITE 2", { exact: true }).uncheck();
  await page.getByLabel("選取 SITE 3", { exact: true }).uncheck();
  await page.getByLabel("選取 SITE 4", { exact: true }).uncheck();
  await expectCheckedSites(page, [1, 5, 6]);

  const pollsBeforeOutage = statusRequests;
  await expect.poll(() => statusRequests).toBeGreaterThan(pollsBeforeOutage);
  await expectCheckedSites(page, [1, 5, 6]);

  // Simulate the same temporary outage/reconnect sequence used in manual acceptance.
  providerOnline = false;
  await connect.click();
  await expect(page.locator(".engineeringBoundaryNote.warning")).toContainText("operator simulated provider outage");

  providerOnline = true;
  await connect.click();
  await expect(facility).toHaveValue("mock-facility-01");
  await expect(ppu).toHaveValue("mock-facility-01-ppu-03");
  await expect(page.getByLabel("Engineering Site selection").getByRole("checkbox")).toHaveCount(6);
  await expectCheckedSites(page, [1, 5, 6]);

  // Explicitly select zero Sites. This is a real user state, not "uninitialized".
  await page.getByLabel("選取 SITE 1", { exact: true }).uncheck();
  await page.getByLabel("選取 SITE 5", { exact: true }).uncheck();
  await page.getByLabel("選取 SITE 6", { exact: true }).uncheck();
  await expectCheckedSites(page, []);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(0);

  // Let multiple status polls happen; zero must stay zero instead of becoming all selected.
  const pollsBeforeZeroHold = statusRequests;
  await expect.poll(() => statusRequests).toBeGreaterThanOrEqual(pollsBeforeZeroHold + 2);
  await expectCheckedSites(page, []);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(0);

  // A same-Gateway reconnect must also preserve an explicit empty Site selection.
  const sessionsBeforeReconnect = sessionRequests;
  await connect.click();
  await expect.poll(() => sessionRequests).toBeGreaterThan(sessionsBeforeReconnect);
  await expect(ppu).toHaveValue("mock-facility-01-ppu-03");
  await expectCheckedSites(page, []);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(0);
});
