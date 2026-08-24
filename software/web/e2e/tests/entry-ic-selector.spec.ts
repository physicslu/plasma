import { expect, test } from "@playwright/test";

test("entry portal exposes IC lookup as card 03 and global navigation does not duplicate it", async ({ page }) => {
  await page.goto("/demo");

  const productNav = page.getByRole("navigation", { name: "產品模式" });
  await expect(productNav).toBeVisible();
  await expect(productNav.getByRole("link", { name: "IC Selector", exact: true })).toHaveCount(0);
  await expect(page.locator(".globalUtilityNav")).toHaveCount(0);

  const icLookup = page.locator('a.demoCard.utility[href="/devices"]');
  await expect(icLookup).toBeVisible();
  await expect(icLookup.getByText("03", { exact: true })).toBeVisible();
  await expect(icLookup.getByRole("heading", { name: "IC Selector" })).toBeVisible();
  await expect(icLookup.getByText("查詢 IC 料號 →", { exact: true })).toBeVisible();

  await icLookup.click();
  await expect(page).toHaveURL(/\/devices$/);
  await expect(page.getByRole("heading", { name: "IC Selector" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "產品模式" }).getByRole("link", { name: "IC Selector", exact: true })).toHaveCount(0);

  const theme = page.getByRole("group", { name: "Theme" });
  await expect(theme).toBeVisible();
  await expect(theme.getByRole("button", { name: "Light" })).toBeVisible();
  await expect(theme.getByRole("button", { name: "Dark" })).toBeVisible();
  await theme.getByRole("button", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});
