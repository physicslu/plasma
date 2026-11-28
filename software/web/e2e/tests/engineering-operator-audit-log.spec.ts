import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { FIRMWARE, legacyRequests, mockManager, type MockPpu } from "./managed-programming-helpers";
import {
  programmingJob,
  programmingJobAction,
  programmingJobOperation,
} from "./programming-job-test-helpers";

// U10: Manager-managed only. Mock Manager / Mock PPUs at the Browser boundary;
// the Engineering session, its provenance log lines and the PPU-local Batch
// engine are gone. The operator audit contract is unchanged: every operator
// action is reconstructable from the Engineering Job Log, filters only hide
// entries on screen, and Download .log keeps the full evidence.

const facilityId = "lab";
const ppu1: MockPpu = { alias: "bench-a", ppuId: "bench-a-01", facilityId, enabledSites: [1, 2], siteCount: 2 };
const ppu2: MockPpu = { alias: "bench-b", ppuId: "bench-b-01", facilityId, enabledSites: [1, 2], siteCount: 2 };

async function openProgramming(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByTestId("managed-backend")).toContainText("ONLINE");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
}

test("Engineering audit log reconstructs operator actions and filters without truncating downloaded evidence", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [ppu1, ppu2] });

  await openProgramming(page);
  const log = page.getByLabel("Engineering job log");
  const job = programmingJob(page, "engineering");
  await expect(log).toContainText("[NET] [MANAGER] Registry · 1 Facilities · 2 PPUs · 4 Sites");

  await page.getByLabel("Engineering PPU", { exact: true }).selectOption(ppu2.alias);
  await expect(log).toContainText(`[USR] [TARGET] SELECT · PPU ${ppu2.alias}`);

  await job.getByPlaceholder("Search ICPN / IC identifier...").fill("STM32F103");
  await job.getByRole("option", { name: /STM32F103C8T6/ }).click();
  await expect(log).toContainText("[USR] [TARGET IC] SELECT · STMicroelectronics / STM32F103C8T6");

  await page.getByLabel("Select SITE 1 for programming").check();
  await page.getByLabel("Select SITE 2 for programming").check();
  await page.getByLabel("Select SITE 2 for programming").uncheck();
  await expect(log).toContainText("[USR] [SITE] SELECTION · SITE-01, SITE-02");
  await expect(log.locator("span").first()).toContainText("[USR] [SITE] SELECTION · SITE-01");

  await page.getByLabel("Engineering Programming Image file").setInputFiles({
    name: "operator-audit.bin",
    mimeType: "application/octet-stream",
    buffer: FIRMWARE,
  });
  await expect(log).toContainText("[USR] [IMG] SELECT IMAGE · operator-audit.bin · 4096 B");

  await programmingJobOperation(job, "verify").uncheck();
  await expect(log).toContainText("[USR] [OPS] ERASE → PROGRAM");
  await programmingJobAction(job, "start").click();

  await expect(log).toContainText("[RESULT] PASS", { timeout: 20_000 });
  expect(counters.batches).toHaveLength(1);
  expect(legacyRequests(counters)).toEqual([]);
  await expect(log).toContainText(`[USR] [START] ERASE → PROGRAM · PPU ${ppu2.alias} (${ppu2.ppuId}) · SITE-01 (1 Site) · STM32F103C8T6 · IMAGE operator-audit.bin`);
  await expect(log).toContainText("[DAT] [LOCK] IMAGE · operator-audit.bin · 4096 B · SHA256");
  await expect(log).toContainText("[BAT] [BATCH]");
  await expect(log).toContainText("[PPU] [RUN] PASS");

  await expect(page.getByText("DAT", { exact: true })).toBeVisible();
  const logHeight = await log.evaluate(element => Number.parseFloat(getComputedStyle(element).height));
  expect(logHeight).toBeGreaterThanOrEqual(260);

  await page.getByLabel("Engineering log filter NET").uncheck();
  await page.getByLabel("Engineering log filter PPU").uncheck();
  await page.getByLabel("Engineering log filter DAT").uncheck();
  await page.getByLabel("Engineering log filter BAT").uncheck();
  await page.getByLabel("Engineering log filter SYS").uncheck();

  const visibleEntries = log.locator("span");
  await expect(visibleEntries.first()).toHaveAttribute("data-category", "USR");
  expect(await visibleEntries.count()).toBeGreaterThan(0);
  for (const category of await visibleEntries.evaluateAll(elements => elements.map(element => element.getAttribute("data-category")))) {
    expect(category).toBe("USR");
  }
  await expect(log).not.toContainText("[PPU] [RUN] PASS");
  await expect(log).not.toContainText("[NET] [MANAGER]");

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download .log", exact: true }).click();
  const download = await downloadPromise;
  const path = await download.path();
  expect(path).not.toBeNull();
  const fileText = await readFile(path!, "utf8");
  expect(fileText).toContain("[USR] [IMG] SELECT IMAGE · operator-audit.bin · 4096 B");
  expect(fileText).toContain(`[USR] [START] ERASE → PROGRAM · PPU ${ppu2.alias}`);
  expect(fileText).toContain("[BAT] [BATCH]");
  expect(fileText).toContain("[PPU] [RUN] PASS");
  expect(fileText).toContain("[NET] [MANAGER] Registry");
});
