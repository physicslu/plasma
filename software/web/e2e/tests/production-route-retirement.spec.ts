import { expect, test } from "@playwright/test";

test("retired Production Single PPU route returns the operator to Factory Console", async ({ page }) => {
  await page.goto("/fleet/programming");

  await expect(page).toHaveURL(/\/fleet$/);
  await expect(page.getByRole("heading", { name: "PMODE · FACTORY CONSOLE" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Production workspaces" })).toHaveCount(0);
  await expect(page.getByText("Single PPU Programming", { exact: true })).toHaveCount(0);
});
