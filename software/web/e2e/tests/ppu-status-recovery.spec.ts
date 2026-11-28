import { expect, test, type Page } from "@playwright/test";
import { FIRMWARE, mockFleet, mockManager, type MockPpu } from "./managed-programming-helpers";
import { programmingJobAction } from "./programming-job-test-helpers";
import {
  chooseTestTarget,
  commitProductionSites,
  factoryConsoleHeading,
  programmingJob,
} from "./production-console-helpers";

// U10: PMode is Manager-managed only; the Production Set PPU status is the
// Manager Fleet observation of that Alias. The operator contract is kept: a
// transient PPU status failure is shown on LIVE SITE STATUS and recovers on its
// own, without the operator reselecting the Facility / PPU / Site set, and
// START is re-enabled once the PPU is observable again.

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

async function openFactory(page: Page, ppus: MockPpu[]) {
  const counters = await mockManager(page, { ppus });
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  return counters;
}

const fleetReads = (requests: string[]) => requests.filter(entry => entry === "GET /api/fleet").length;

// A commissioned PPU the Fleet cannot observe is a transient status fault:
// the status recovery re-reads the Manager Fleet with backoff until it is
// observable again, so no stale OFFLINE state is kept.
test("transient PPU status failure auto-recovers without reselecting FPS", async ({ page }) => {
  const ppus = mockFleet(1, [2]);
  const counters = await openFactory(page, ppus);
  // The Manager temporarily cannot reach the PPU while the set is committed.
  ppus[0].transport = "unreachable";
  await commitProductionSites(page, facilityId, ppuId, [1, 2]);

  const live = page.getByRole("region", { name: "LIVE SITE STATUS" });
  await expect(live.getByText(/OFFLINE|UNREACHABLE/i).first()).toBeVisible();
  const readsDuringOutage = fleetReads(counters.requests);
  ppus[0].transport = "reachable";
  await expect.poll(() => fleetReads(counters.requests), { timeout: 8_000 }).toBeGreaterThan(readsDuringOutage);
  await expect(live.locator(".factorySiteLedCard")).toHaveCount(2);
  await expect(page.getByLabel("Factory communication health")).toContainText("PPU 1/1 READY", { timeout: 10_000 });
  await expect(page.getByText(new RegExp(`STATUS RESTORED · ${ppuId}`))).toBeVisible();
});

test("PMode keeps START disabled during a PPU status outage and re-enables it after recovery without reselecting FPS", async ({ page }) => {
  const ppus = mockFleet(1, [2]);
  await openFactory(page, ppus);
  ppus[0].transport = "unreachable";
  await commitProductionSites(page, facilityId, ppuId, [1, 2]);
  await chooseTestTarget(page);
  await programmingJob(page).getByLabel("Production Programming Image file").setInputFiles({
    name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE,
  });

  const start = programmingJobAction(programmingJob(page), "start");
  const live = page.getByRole("region", { name: "LIVE SITE STATUS" });
  await expect(start).toBeDisabled();
  await expect(page.getByLabel("Factory communication health")).toContainText("DEGRADED");
  ppus[0].transport = "reachable";
  await expect(page.getByLabel("Factory communication health")).toContainText("PPU 1/1 READY", { timeout: 15_000 });
  await expect(live.locator(".factorySiteLedCard")).toHaveCount(2);
  await expect(start).toBeEnabled();
});
