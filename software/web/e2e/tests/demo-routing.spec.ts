import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const globalLinks = [
  ["入口", "/demo"],
  ["單機 PPU", "/ppu"],
  ["多機 Fleet", "/fleet"],
] as const;

async function expectGlobalNavigation(page: Page, activeLabel: string) {
  const nav = page.getByRole("navigation", { name: "Plasma global navigation" });
  await expect(nav).toBeVisible();

  for (const [label, href] of globalLinks) {
    const link = nav.getByRole("link", { name: label, exact: true });
    await expect(link).toHaveAttribute("href", href);
    if (label === activeLabel) {
      await expect(link).toHaveAttribute("aria-current", "page");
    } else {
      await expect(link).not.toHaveAttribute("aria-current", "page");
    }
  }

  return nav;
}

test("demo, Single PPU, Fleet, and product modes share top-level navigation", async ({ page }) => {
  await page.goto("/demo");
  await expectGlobalNavigation(page, "入口");

  const singlePpu = page.getByRole("link", { name: /Open Single PPU Demo/ });
  const fleet = page.getByRole("link", { name: /Open Fleet Demo/ });
  await expect(singlePpu).toHaveAttribute("href", "/ppu");
  await expect(fleet).toHaveAttribute("href", "/fleet");

  const modeNav = page.getByRole("navigation", { name: "工作模式" });
  await expect(modeNav.getByRole("link", { name: "量產模式" })).toHaveAttribute("href", "/fleet");
  await expect(modeNav.getByRole("link", { name: "工程模式" })).toHaveAttribute("href", "/engineering");

  await singlePpu.click();
  await expect(page).toHaveURL(/\/ppu$/);
  await expect(page.getByRole("heading", { name: "Programming Site 工作總覽" })).toBeVisible();
  const ppuNav = await expectGlobalNavigation(page, "單機 PPU");

  await ppuNav.getByRole("link", { name: "多機 Fleet", exact: true }).click();
  await expect(page).toHaveURL(/\/fleet$/);
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();
  const fleetNav = await expectGlobalNavigation(page, "多機 Fleet");

  // Browser CI intentionally does not start Plasma Manager. The Fleet flag is
  // enabled on the Vite host process, so the Worker route must see that binding
  // and advance to the Manager connection attempt. If the host -> Worker bridge
  // regresses, this becomes the old "Fleet UI is disabled" state instead.
  await expect(page.getByText("Fleet snapshot unavailable")).toBeVisible();
  await expect(page.getByText("Fleet BFF HTTP 503")).toBeVisible();
  await expect(page.getByText("Fleet UI is disabled on this host.")).toHaveCount(0);

  await page.getByRole("navigation", { name: "工作模式" }).getByRole("link", { name: "工程模式" }).click();
  await expect(page).toHaveURL(/\/engineering$/);
  await expect(page.getByRole("heading", { name: "Engineering Mode" })).toBeVisible();

  await page.getByRole("navigation", { name: "Plasma global navigation" }).getByRole("link", { name: "入口", exact: true }).click();
  await expect(page).toHaveURL(/\/demo$/);
  await expect(page.getByRole("heading", { name: "Choose a Demo" })).toBeVisible();
  await expectGlobalNavigation(page, "入口");
});
