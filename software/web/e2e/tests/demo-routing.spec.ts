import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const productLinks = [
  ["入口", "/demo"],
  ["量產模式", "/fleet"],
  ["工程模式", "/engineering"],
] as const;

async function expectProductNavigation(page: Page, activeLabel: string) {
  const nav = page.getByRole("navigation", { name: "產品模式" });
  await expect(nav).toBeVisible();

  for (const [label, href] of productLinks) {
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

test("demo entry exposes only canonical Product Modes in top-level navigation", async ({ page }) => {
  await page.goto("/demo");
  await expectProductNavigation(page, "入口");

  await expect(page.getByRole("heading", { name: "選擇產品模式" })).toBeVisible();
  const production = page.locator('a.demoCard[href="/fleet"]');
  const engineering = page.locator('a.demoCard[href="/engineering"]');
  await expect(production).toHaveAttribute("href", "/fleet");
  await expect(engineering).toHaveAttribute("href", "/engineering");
  await expect(page.getByRole("navigation", { name: "產品模式" }).getByRole("link", { name: /Fleet/ })).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "產品模式" }).getByRole("link", { name: /單機 PPU/ })).toHaveCount(0);

  await production.click();
  await expect(page).toHaveURL(/\/fleet$/);
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();
  await expectProductNavigation(page, "量產模式");

  // Standard browser CI intentionally does not start the Python Mock PPU
  // Provider. The route must still render its explicit Mock-only execution
  // boundary rather than falling back to the former Manager/Fleet write model.
  await expect(page.getByText(/此頁使用 Python Mock PPU Provider 驗證多 PPU 執行/)).toBeVisible();
  await expect(page.getByText(/Plasma Manager 仍維持唯讀/)).toBeVisible();
  await expect(page.getByText("Fleet BFF HTTP 503")).toHaveCount(0);

  await page.getByRole("navigation", { name: "產品模式" }).getByRole("link", { name: "工程模式", exact: true }).click();
  await expect(page).toHaveURL(/\/engineering$/);
  await expect(page.getByRole("heading", { name: "Engineering Mode" })).toBeVisible();
  await expectProductNavigation(page, "工程模式");

  await page.getByRole("navigation", { name: "產品模式" }).getByRole("link", { name: "入口", exact: true }).click();
  await expect(page).toHaveURL(/\/demo$/);
  await expect(page.getByRole("heading", { name: "選擇產品模式" })).toBeVisible();
  await expectProductNavigation(page, "入口");
});

test("language switching becomes interactive after hydration and then updates immediately", async ({ page }) => {
  await page.goto("/fleet");
  await expect(page.getByRole("navigation", { name: "產品模式" })).toBeVisible();

  const english = page.getByRole("button", { name: "EN", exact: true });
  await expect(english, "locale control must not accept a click before hydration is interactive").toBeEnabled();
  await english.click();
  await expect(page.getByRole("navigation", { name: "Product mode" }), "locale change should not wait on polling/storage propagation after the control is enabled").toBeVisible({ timeout: 300 });
  await expect(page.getByRole("link", { name: "Production Mode", exact: true })).toBeVisible({ timeout: 300 });
  await expect(page.locator("html")).toHaveAttribute("lang", "en-US", { timeout: 300 });

  const traditionalChinese = page.getByRole("button", { name: "繁中", exact: true });
  await expect(traditionalChinese).toBeEnabled();
  await traditionalChinese.click();
  await expect(page.getByRole("navigation", { name: "產品模式" })).toBeVisible({ timeout: 300 });
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-TW", { timeout: 300 });
});


test("demo landing content follows locale switching", async ({ page }) => {
  await page.goto("/demo");
  await expect(page.getByRole("heading", { name: "選擇產品模式" })).toBeVisible();
  await expect(page.getByText("架構邊界", { exact: true })).toBeVisible();
  await expect(page.getByText("開啟量產模式 →", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en-US", { timeout: 300 });
  await expect(page.getByRole("heading", { name: "Choose Product Mode" })).toBeVisible({ timeout: 300 });
  await expect(page.getByText("Architecture boundary", { exact: true })).toBeVisible({ timeout: 300 });
  await expect(page.getByText("Open Production Mode →", { exact: true })).toBeVisible({ timeout: 300 });
  await expect(page.getByText("Open Engineering Mode →", { exact: true })).toBeVisible({ timeout: 300 });

  await page.getByRole("button", { name: "繁中", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-TW", { timeout: 300 });
  await expect(page.getByRole("heading", { name: "選擇產品模式" })).toBeVisible({ timeout: 300 });
});