import { expect, test } from "@playwright/test";

test("demo entry separates Single PPU and Manager/Fleet views", async ({ page }) => {
  await page.goto("/demo");

  const singlePpu = page.getByRole("link", { name: /Open Single PPU Demo/ });
  const fleet = page.getByRole("link", { name: /Open Fleet Demo/ });
  await expect(singlePpu).toHaveAttribute("href", "/ppu");
  await expect(fleet).toHaveAttribute("href", "/fleet");

  await singlePpu.click();
  await expect(page).toHaveURL(/\/ppu$/);
  await expect(page.getByRole("heading", { name: "Programming Site 工作總覽" })).toBeVisible();

  await page.goto("/demo");
  await fleet.click();
  await expect(page).toHaveURL(/\/fleet$/);
  await expect(page.getByRole("heading", { name: "Facility / PPU Fleet Overview" })).toBeVisible();
  await expect(page.getByText("Fleet UI is disabled on this host.")).toBeVisible();
});
