import { expect, test, type Page } from "@playwright/test";
import { mockFleet, mockManager, type Counters } from "./managed-programming-helpers";
import { chooseTestTarget } from "./production-console-helpers";

// U10: Manager-managed only. The Engineering session reconnect and the
// Browser-chosen Gateway URL are gone; the topology is re-read from the
// Manager Registry / Fleet every few seconds. The operator contract is kept:
// a Manager outage round-trip and steady polling never change the selected
// Facility / PPU or the explicit Site subset, and an explicit empty Site
// selection never turns back into "all".

const fleetPolls = (counters: Counters) => counters.requests.filter(entry => entry === "GET /api/fleet").length;

async function openProgramming(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByTestId("managed-backend")).toContainText("ONLINE");
  // Sites are offered once the Target IC has a Programming Route.
  await chooseTestTarget(page, "engineering");
}

async function expectCheckedSites(page: Page, siteCount: number, checked: number[]) {
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(siteCount);
  for (let siteId = 1; siteId <= siteCount; siteId += 1) {
    const box = page.getByLabel(`Select SITE ${siteId} for programming`, { exact: true });
    if (checked.includes(siteId)) await expect(box).toBeChecked();
    else await expect(box).not.toBeChecked();
  }
}

async function managerOutageRoundTrip(page: Page, options: { registryStatus?: number }) {
  options.registryStatus = 503;
  await expect(page.getByTestId("managed-backend")).toContainText("OFFLINE", { timeout: 10_000 });
  await expect(page.getByTestId("managed-readiness")).toContainText("MANAGER OFFLINE");
  options.registryStatus = undefined;
  await expect(page.getByTestId("managed-backend")).toContainText("ONLINE", { timeout: 10_000 });
}

test("Manager outage round-trip keeps the explicit Site selection and polling never turns explicit zero back into all", async ({ page }) => {
  const options: Parameters<typeof mockManager>[1] = { ppus: mockFleet() };
  const counters = await mockManager(page, options);
  await openProgramming(page);

  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  const log = page.getByLabel("Engineering job log");

  await facility.selectOption("mock-facility-01");
  await ppu.selectOption("mock-facility-01-ppu-03");
  await expectCheckedSites(page, 6, []);

  // Mirror the operator's manual pattern: keep SITE 1 / 5 / 6 only.
  for (const siteId of [1, 5, 6]) await page.getByLabel(`Select SITE ${siteId} for programming`, { exact: true }).check();
  await expectCheckedSites(page, 6, [1, 5, 6]);

  const pollsBeforeOutage = fleetPolls(counters);
  await expect.poll(() => fleetPolls(counters), { timeout: 10_000 }).toBeGreaterThan(pollsBeforeOutage);
  await expectCheckedSites(page, 6, [1, 5, 6]);

  await managerOutageRoundTrip(page, options);
  await expect(log).toContainText("[NET] [MANAGER] Registry unavailable");
  await expect(facility).toHaveValue("mock-facility-01");
  await expect(ppu).toHaveValue("mock-facility-01-ppu-03");
  await expectCheckedSites(page, 6, [1, 5, 6]);

  // Explicitly select zero Sites. The live status table must remain complete.
  for (const siteId of [1, 5, 6]) await page.getByLabel(`Select SITE ${siteId} for programming`, { exact: true }).uncheck();
  await expectCheckedSites(page, 6, []);
  await expect(log.locator("span").first()).toContainText("[USR] [SITE] SELECTION · none");

  // Let multiple polls happen; zero must stay zero instead of becoming all selected.
  const pollsBeforeZeroHold = fleetPolls(counters);
  await expect.poll(() => fleetPolls(counters), { timeout: 15_000 }).toBeGreaterThanOrEqual(pollsBeforeZeroHold + 2);
  await expectCheckedSites(page, 6, []);
  await expect(page.getByRole("button", { name: /START PROGRAMMING/ })).toBeDisabled();
});

test("Manager outage round-trip restores the original PPU and Site subset on an 8-Site PPU", async ({ page }) => {
  const options: Parameters<typeof mockManager>[1] = { ppus: mockFleet() };
  await mockManager(page, options);
  await openProgramming(page);

  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });

  await facility.selectOption("mock-facility-03");
  await ppu.selectOption("mock-facility-03-ppu-04");
  await expectCheckedSites(page, 8, []);

  // Mirror the uploaded operator log: keep SITE 2 / 4 / 6 / 7 on an 8-Site PPU.
  for (const siteId of [2, 4, 6, 7]) await page.getByLabel(`Select SITE ${siteId} for programming`, { exact: true }).check();
  await expectCheckedSites(page, 8, [2, 4, 6, 7]);

  await managerOutageRoundTrip(page, options);
  await expect(facility).toHaveValue("mock-facility-03");
  await expect(ppu).toHaveValue("mock-facility-03-ppu-04");
  await expectCheckedSites(page, 8, [2, 4, 6, 7]);
});
