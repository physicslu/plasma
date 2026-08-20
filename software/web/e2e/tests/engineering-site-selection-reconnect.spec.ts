import { expect, test } from "@playwright/test";

const siteCounts = [2, 4, 6, 8] as const;

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 3,
    ppu_count: 12,
    site_count: 60,
    programming_asset_scope: "connection-session-and-ppu",
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

async function fulfillEngineeringRoute(
  route: import("@playwright/test").Route,
  counters?: { sessions?: number; statuses?: number },
) {
  const request = route.request();
  const url = new URL(request.url());

  if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
    if (counters) counters.sessions = (counters.sessions ?? 0) + 1;
    const body = request.postDataJSON() as { previous_session_id?: string };
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        session: {
          session_id: String(counters?.sessions ?? 1).padStart(32, "0"),
          programming_asset_cache_scope: "connection-session-and-ppu",
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
    if (counters) counters.statuses = (counters.statuses ?? 0) + 1;
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
}

test("operator reconnect keeps explicit Site selection and polling never turns explicit zero back into all", async ({ page }) => {
  let providerOnline = true;
  const counters = { sessions: 0, statuses: 0 };

  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (!providerOnline && url.pathname === "/api/engineering/session") {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { message: "operator simulated provider outage" } }),
      });
      return;
    }

    await fulfillEngineeringRoute(route, counters);
  });

  await openProgramming(page);

  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  const connect = page.locator(".engineeringGateway button[type=submit]");
  const log = page.getByLabel("Engineering job log");

  await facility.selectOption("mock-facility-01");
  await ppu.selectOption("mock-facility-01-ppu-03");
  await expect(page.getByLabel("Engineering Site selection").getByRole("checkbox")).toHaveCount(6);

  // Mirror the operator's manual pattern: keep SITE 1 / 5 / 6 only.
  await page.getByLabel("選取 SITE 2", { exact: true }).uncheck();
  await page.getByLabel("選取 SITE 3", { exact: true }).uncheck();
  await page.getByLabel("選取 SITE 4", { exact: true }).uncheck();
  await expectCheckedSites(page, [1, 5, 6]);

  const pollsBeforeOutage = counters.statuses;
  await expect.poll(() => counters.statuses).toBeGreaterThan(pollsBeforeOutage);
  await expectCheckedSites(page, [1, 5, 6]);

  // Simulate a Provider failure while staying on the same Gateway URL.
  providerOnline = false;
  await connect.click();
  await expect(page.locator(".engineeringBoundaryNote.warning")).toContainText("operator simulated provider outage");

  providerOnline = true;
  await connect.click();
  await expect(facility).toHaveValue("mock-facility-01");
  await expect(ppu).toHaveValue("mock-facility-01-ppu-03");
  await expect(page.getByLabel("Engineering Site selection").getByRole("checkbox")).toHaveCount(6);
  await expectCheckedSites(page, [1, 5, 6]);
  await expect(log).toContainText("[SYS] [TARGET] RESTORED · mock-facility-01 / mock-facility-01-ppu-03");
  await expect(log).toContainText("[SYS] [SITE] RESTORED · SITE-01, SITE-05, SITE-06");

  // Explicitly select zero Sites. This is a real user state, not "uninitialized".
  await page.getByLabel("選取 SITE 1", { exact: true }).uncheck();
  await page.getByLabel("選取 SITE 5", { exact: true }).uncheck();
  await page.getByLabel("選取 SITE 6", { exact: true }).uncheck();
  await expectCheckedSites(page, []);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(0);

  // Let multiple status polls happen; zero must stay zero instead of becoming all selected.
  const pollsBeforeZeroHold = counters.statuses;
  await expect.poll(() => counters.statuses).toBeGreaterThanOrEqual(pollsBeforeZeroHold + 2);
  await expectCheckedSites(page, []);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(0);

  // A same-Gateway reconnect must also preserve an explicit empty Site selection.
  const sessionsBeforeReconnect = counters.sessions;
  await connect.click();
  await expect.poll(() => counters.sessions).toBeGreaterThan(sessionsBeforeReconnect);
  await expect(ppu).toHaveValue("mock-facility-01-ppu-03");
  await expectCheckedSites(page, []);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(0);
  await expect(log).toContainText("[SYS] [SITE] RESTORED · none");
});

test("operator gateway outage round-trip restores the original PPU and Site subset", async ({ page }) => {
  const badGateway = "http://127.0.0.1:65534";
  let sessionRequests = 0;

  await page.route("**/api/engineering/**", async route => {
    const url = new URL(route.request().url());
    if (url.origin === badGateway) {
      await route.abort("failed");
      return;
    }
    if (url.pathname === "/api/engineering/session") sessionRequests += 1;
    await fulfillEngineeringRoute(route, { sessions: sessionRequests });
  });

  await openProgramming(page);

  const gateway = page.getByLabel("Engineering Gateway URL");
  const originalGateway = await gateway.inputValue();
  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  const connect = page.locator(".engineeringGateway button[type=submit]");
  const log = page.getByLabel("Engineering job log");

  await facility.selectOption("mock-facility-03");
  await ppu.selectOption("mock-facility-03-ppu-04");
  await expect(page.getByLabel("Engineering Site selection").getByRole("checkbox")).toHaveCount(8);

  // Mirror the uploaded operator log: keep SITE 2 / 4 / 6 / 7 on an 8-Site PPU.
  for (const siteId of [1, 3, 5, 8]) {
    await page.getByLabel(`選取 SITE ${siteId}`, { exact: true }).uncheck();
  }
  await expectCheckedSites(page, [2, 4, 6, 7]);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(4);

  await gateway.fill(badGateway);
  await connect.click();
  await expect(page.locator(".engineeringBoundaryNote.warning")).toContainText("Failed to fetch");

  await gateway.fill(originalGateway);
  await connect.click();
  await expect(facility).toHaveValue("mock-facility-03");
  await expect(ppu).toHaveValue("mock-facility-03-ppu-04");
  await expect(page.getByLabel("Engineering Site selection").getByRole("checkbox")).toHaveCount(8);
  await expectCheckedSites(page, [2, 4, 6, 7]);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(4);
  await expect(log).toContainText("[SYS] [TARGET] RESTORED · mock-facility-03 / mock-facility-03-ppu-04");
  await expect(log).toContainText("[SYS] [SITE] RESTORED · SITE-02, SITE-04, SITE-06, SITE-07");
});
