import { expect, test } from "@playwright/test";
import { FIRMWARE, mockFleet, mockManager } from "./managed-programming-helpers";
import {
  programmingJob as sharedProgrammingJob,
  programmingJobField,
  programmingJobOperation,
} from "./programming-job-test-helpers";
import {
  chooseTestTarget,
  commitProductionSites,
  factoryConsoleHeading,
  productionOperation,
  programmingJob,
} from "./production-console-helpers";

// U10: Manager-managed only. Switching PMode ↔ EMode keeps the operator's
// workspace configuration while the runtime (topology, Site state) is re-read
// from the Manager Registry / Fleet on every visit.

const facilityId = "mock-facility-01";
const ppu1Id = `${facilityId}-ppu-01`;
const ppu2Id = `${facilityId}-ppu-02`;
const fleetReads = (requests: string[]) => requests.filter(entry => entry === "GET /api/fleet").length;

test("Production Set, Site Selection collapse and the EMode section survive a mode switch while runtime is re-read", async ({ page }) => {
  const counters = await mockManager(page, { ppus: mockFleet(1, [2, 4]) });

  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await commitProductionSites(page, facilityId, ppu1Id, [1]);
  await expect(page.locator(`[data-production-ppu="${ppu1Id}"]`)).toBeVisible();
  await page.getByRole("button", { name: /收起|Hide/ }).click();
  await expect(page.getByRole("region", { name: "SYSTEM SETUP & TARGETING" }).locator(".operatorPanelBody")).toBeHidden();

  await page.getByRole("link", { name: "工程模式", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Engineering Mode" })).toBeVisible();
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByLabel("Engineering PPU", { exact: true })).toBeVisible();
  const readsBeforeReturn = fleetReads(counters.requests);

  await page.getByRole("link", { name: "量產模式", exact: true }).click();
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await expect(page.locator(`[data-production-ppu="${ppu1Id}"]`)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(`[data-production-ppu="${ppu1Id}"] [data-production-site]`)).toHaveCount(1);
  await expect(page.getByRole("region", { name: "SYSTEM SETUP & TARGETING" }).locator(".operatorPanelBody")).toBeHidden();
  await expect.poll(() => fleetReads(counters.requests)).toBeGreaterThan(readsBeforeReturn);

  await page.getByRole("link", { name: "工程模式", exact: true }).click();
  await expect(page.getByRole("button", { name: "Programming", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
});

// KNOWN REGRESSION (U10 managed workspaces, reported, not fixed here): the
// Programming Job configuration (Target IC, Programming Image, Operations) of
// both modes and the EMode PPU / Site selection are component-local state and
// are reset by a mode switch; before U10 the shared workspace session kept
// them. This test states the previous contract and is expected to fail until
// the app restores it (or the owner retires the contract); then drop `test.fail`.
test("Programming Job configuration and the EMode PPU / Site selection survive a mode switch", async ({ page }) => {
  test.fail(true, "managed workspaces reset Programming Job configuration and EMode PPU/Site selection on a mode switch");
  await mockManager(page, { ppus: mockFleet(1, [2, 4]) });

  await page.goto("/fleet");
  await commitProductionSites(page, facilityId, ppu1Id, [1]);
  await chooseTestTarget(page);
  await page.getByLabel("Production Programming Image file").setInputFiles({
    name: "shared-mode-state.bin", mimeType: "application/octet-stream", buffer: FIRMWARE,
  });
  await productionOperation(page, "E").uncheck();

  await page.getByRole("link", { name: "工程模式", exact: true }).click();
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  let engineeringJob = sharedProgrammingJob(page, "engineering");
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  await ppu.selectOption(ppu2Id);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(4);
  await chooseTestTarget(page, "engineering");
  await page.getByLabel("Select SITE 1 for programming").check();
  await programmingJobOperation(engineeringJob, "verify").uncheck();

  await page.getByRole("link", { name: "量產模式", exact: true }).click();
  await expect(page.locator(`[data-production-ppu="${ppu1Id}"]`)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByLabel("Target IC")).toHaveValue("STM32F103C8T6");
  await expect(programmingJobField(programmingJob(page), "image").locator("[data-image-source]")).toHaveText("shared-mode-state.bin");
  await expect(productionOperation(page, "E")).not.toBeChecked();
  await expect(productionOperation(page, "P")).toBeChecked();

  await page.getByRole("link", { name: "工程模式", exact: true }).click();
  engineeringJob = sharedProgrammingJob(page, "engineering");
  await expect(ppu).toHaveValue(ppu2Id);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(4);
  await expect(page.getByLabel("Select SITE 1 for programming")).toBeChecked();
  await expect(programmingJobOperation(engineeringJob, "verify")).not.toBeChecked();
});
