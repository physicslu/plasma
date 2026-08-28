import { expect, test } from "@playwright/test";

test("portal exposes Documents as function 04 without changing Product Mode navigation", async ({ page }) => {
  await page.goto("/demo");

  const documents = page.locator('a.demoCard[href="/documents"]');
  await expect(documents).toBeVisible();
  await expect(documents.locator(".demoCardHead span")).toHaveText("04");
  await expect(documents.getByRole("heading", { name: /文件|Documents/ })).toBeVisible();

  const productModeNav = page.getByRole("navigation", { name: /產品模式|Product mode/ });
  await expect(productModeNav.locator('a[href="/documents"]')).toHaveCount(0);

  await documents.click();
  await expect(page).toHaveURL(/\/documents$/);
  await expect(page.locator('[data-route-marker="Documents"]')).toBeVisible();
});
