import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { mockFleet, mockManager, type MockPpu } from "./managed-programming-helpers";

// U10: Manager-managed only. The Engineering session reconnect is gone; the
// topology is re-read from the Manager Registry / Fleet. The operator contract
// is kept: the selected PPU survives a Manager outage and falls back to the
// first PPU only when it disappeared from the Registry, and the Engineering
// Job Log is newest-first with Download .log exporting the same order.

async function openProgramming(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.getByTestId("managed-backend")).toContainText("ONLINE");
}

test("Manager outage preserves the selected PPU and falls back to the first PPU only when it disappeared", async ({ page }) => {
  const ppus: MockPpu[] = mockFleet();
  const options: Parameters<typeof mockManager>[1] = { ppus };
  await mockManager(page, options);

  await openProgramming(page);
  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  const log = page.getByLabel("Engineering job log");

  await facility.selectOption("mock-facility-02");
  await ppu.selectOption("mock-facility-02-ppu-03");
  await expect(facility).toHaveValue("mock-facility-02");
  await expect(ppu).toHaveValue("mock-facility-02-ppu-03");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(6);

  options.registryStatus = 503;
  await expect(page.getByTestId("managed-backend")).toContainText("OFFLINE", { timeout: 10_000 });
  const availability = page.locator(".engineeringBoundaryNote.warning");
  await expect(availability.locator("b")).toContainText("MANAGER OFFLINE");
  await expect(log).toContainText("[NET] [MANAGER] Registry unavailable");

  options.registryStatus = undefined;
  await expect(page.getByTestId("managed-backend")).toContainText("ONLINE", { timeout: 10_000 });
  await expect(facility).toHaveValue("mock-facility-02");
  await expect(ppu).toHaveValue("mock-facility-02-ppu-03");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(6);

  // The selected PPU leaves the Registry: the first PPU becomes the target.
  ppus.splice(ppus.findIndex(item => item.alias === "mock-facility-02-ppu-03"), 1);
  await expect(facility).toHaveValue("mock-facility-01", { timeout: 10_000 });
  await expect(ppu).toHaveValue("mock-facility-01-ppu-01");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
});

test("Engineering Job Log is newest-first and Download .log exports the same order", async ({ page }) => {
  await mockManager(page, { ppus: mockFleet() });

  await openProgramming(page);
  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  const log = page.getByLabel("Engineering job log");

  await facility.selectOption("mock-facility-02");
  await ppu.selectOption("mock-facility-02-ppu-02");

  const entries = log.locator("span");
  const targets = log.locator('span[data-category="USR"]').filter({ hasText: "[TARGET] SELECT" });
  await expect(targets.nth(0)).toContainText("[TARGET] SELECT · PPU mock-facility-02-ppu-02");
  await expect(targets.nth(1)).toContainText("[TARGET] SELECT · PPU mock-facility-02-ppu-01");
  await expect(entries.last()).toContainText("[NET] [MANAGER] Registry");

  const visibleLines = await entries.allTextContents();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download .log", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^plasma-engineering-\d{8}-\d{6}\.log$/);

  const path = await download.path();
  expect(path).not.toBeNull();
  const fileText = await readFile(path!, "utf8");
  expect(fileText).toBe(`${visibleLines.join("\n")}\n`);

  await page.getByRole("button", { name: "清除", exact: true }).click();
  await expect(entries).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Download .log", exact: true })).toBeDisabled();
});
