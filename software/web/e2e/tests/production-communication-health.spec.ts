import { expect, test, type Page } from "@playwright/test";
import { legacyRequests, mockFleet, mockManager, type MockPpu } from "./managed-programming-helpers";
import { chooseTestTarget, commitProductionSites } from "./production-console-helpers";

// U10: PMode is Manager-managed only. "Gateway" health is the Manager BFF's
// reachability and "PPU" health is the Manager Fleet observation of each
// Production Set PPU; the Engineering provider and its session are gone. The
// operator contract is kept: Gateway and PPU health are reported separately,
// a PPU fault never reads as a Gateway fault, and START stays disabled while
// any of them is not ready.

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

function communicationHealth(page: Page) {
  return page.getByLabel("Factory communication health");
}

test("healthy selected PPU reports Gateway ONLINE and PPU READY separately", async ({ page }) => {
  await mockManager(page, { ppus: mockFleet(1, [2]) });
  await page.goto("/fleet");
  await expect(communicationHealth(page)).toContainText("Gateway ONLINE · PPU —");

  await commitProductionSites(page, facilityId, ppuId, [1, 2]);
  await expect(communicationHealth(page)).toContainText("Gateway ONLINE · PPU 1/1 READY");
});

test("a PPU the Manager cannot observe keeps Gateway ONLINE and marks PPU DEGRADED", async ({ page }) => {
  const ppus: MockPpu[] = mockFleet(1, [2]);
  await mockManager(page, { ppus });
  await page.goto("/fleet");
  // The Manager loses its transport to the PPU after the Facility tree loaded.
  ppus[0].transport = "unreachable";
  await commitProductionSites(page, facilityId, ppuId, [1, 2]);

  await expect(communicationHealth(page)).toContainText("Gateway ONLINE · PPU 0/1 READY · DEGRADED");
  await expect(page.getByRole("button", { name: /START PROGRAMMING/ })).toBeDisabled();
});

test("Manager transport failure marks Gateway UNREACHABLE and PPU UNKNOWN", async ({ page }) => {
  const counters = await mockManager(page, { ppus: mockFleet(1, [2]) });
  await page.route(/\/api\/manager\/registry$/, route => route.abort("failed"));
  await page.route(/\/api\/fleet$/, route => route.abort("failed"));
  await page.goto("/fleet");

  await expect(communicationHealth(page)).toContainText("Gateway UNREACHABLE · PPU UNKNOWN");
  // Without a Manager topology there is no Production Programming Job to start.
  await expect(page.getByRole("status").filter({ hasText: /無法連線|unreachable/i })).toBeVisible();
  await expect(page.locator('[data-programming-job-action="start"]')).toHaveCount(0);
  expect(legacyRequests(counters)).toEqual([]);
});

test("Programming Routes unavailable keeps Gateway ONLINE and the PPU READY, reports Programming unavailable, and never reaches a PPU Gateway", async ({ page }) => {
  const counters = await mockManager(page, { ppus: mockFleet(1, [2]), routesStatus: 503 });
  await page.goto("/fleet");
  await commitProductionSites(page, facilityId, ppuId, [1, 2]);
  await chooseTestTarget(page);

  await expect(communicationHealth(page)).toContainText("Gateway ONLINE · PPU 1/1 READY");
  await expect(page.getByTestId("managed-readiness")).toContainText("ROUTES UNAVAILABLE");
  await expect(page.getByRole("button", { name: /START PROGRAMMING/ })).toBeDisabled();
  expect(legacyRequests(counters)).toEqual([]);
  expect(counters.batches).toHaveLength(0);
});
