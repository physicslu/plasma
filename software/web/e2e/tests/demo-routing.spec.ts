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

  // Browser CI intentionally does not start Plasma Manager. The Fleet flag is
  // enabled on the Vite host process, so the Worker route must see that binding
  // and advance to the Manager connection attempt. If the host -> Worker bridge
  // regresses, this becomes the old "Fleet UI is disabled" state instead.
  await expect(page.getByText("Fleet snapshot unavailable")).toBeVisible();
  await expect(page.getByText("Fleet BFF HTTP 503")).toBeVisible();
  await expect(page.getByText("Fleet UI is disabled on this host.")).toHaveCount(0);
});
