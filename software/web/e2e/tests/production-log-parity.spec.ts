import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { Z2, mockManager } from "./managed-programming-helpers";

// U10: the Console is Manager-managed only; the Mock Manager answers at the
// Browser boundary (managed-programming-helpers.ts).
async function installProductionCatalog(page: Page) {
  await mockManager(page, { ppus: [{ ...Z2, enabledSites: [1, 2], siteCount: 2 }] });
}

test("Production log uses the Engineering log panel contract", async ({ page }) => {
  await installProductionCatalog(page);
  await page.goto("/fleet");

  const log = page.getByLabel("Production batch log");
  await expect(log).toBeVisible();
  await expect(page.getByRole("button", { name: "Download .log", exact: true })).toBeEnabled();
  await expect(page.getByLabel("Production log filters")).toBeVisible();
  for (const category of ["USR", "NET", "PPU", "DAT", "BAT", "SYS"]) {
    await expect(page.getByLabel(`Production log filter ${category}`)).toBeChecked();
  }

  await expect(log).toContainText("[NET] [PROVIDER] MANAGER");
  const logHeight = await log.evaluate(element => Number.parseFloat(getComputedStyle(element).height));
  expect(logHeight).toBeGreaterThanOrEqual(260);

  await page.getByLabel("Production log filter NET").uncheck();
  await expect(log).not.toContainText("[PROVIDER] MANAGER");

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download .log", exact: true }).click();
  const download = await downloadPromise;
  const path = await download.path();
  expect(path).not.toBeNull();
  const fileText = await readFile(path!, "utf8");
  expect(fileText).toContain("[NET] [PROVIDER] MANAGER");

  await page.getByRole("button", { name: "清除 Log", exact: true }).click();
  await expect(log).toContainText("No log entries for selected filters.");
});
