import { expect, test } from "@playwright/test";

test("Documents exposes PMode and EMode static operator guides through the shared EMode-style tree", async ({ page }) => {
  await page.goto("/documents");

  await expect(page.locator('[data-route-marker="Documents"]')).toBeVisible();
  await expect(page.getByRole("heading", { name: /PMode (操作總覽|Overview)/ })).toBeVisible();

  const nav = page.getByRole("navigation", { name: /文件導覽|Documents navigation/ });
  await expect(nav.getByRole("button", { name: "PMode", exact: true })).toHaveAttribute("aria-expanded", "true");
  await expect(nav.getByRole("button", { name: "EMode", exact: true })).toHaveAttribute("aria-expanded", "true");

  await nav.getByRole("button", { name: "Gateway Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Gateway (設定說明|Settings)/ })).toBeVisible();
  await expect(page.getByText("4 × 10 sec + 1 + 2 + 4 sec = 47 sec", { exact: true })).toBeVisible();

  await nav.getByRole("button", { name: "Mock Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Mock (設定說明|Settings)/ })).toBeVisible();
  await expect(page.getByText(/Mock PASS ≠/)).toBeVisible();
});

test("Documents sidebar collapses with the same desktop behavior as EMode", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/documents");

  const workspace = page.locator(".documentsPage");
  await page.getByRole("button", { name: "Collapse Documents menu" }).click();
  await expect(workspace).toHaveClass(/sidebarCollapsed/);
  await expect(page.locator(".documentsPage .engineeringNavChildren").first()).toBeHidden();
  await page.getByRole("button", { name: "Expand Documents menu" }).click();
  await expect(workspace).not.toHaveClass(/sidebarCollapsed/);
});

test("Documents navigation remains usable on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 720, height: 900 });
  await page.goto("/documents");

  const nav = page.getByRole("navigation", { name: /文件導覽|Documents navigation/ });
  await nav.getByRole("button", { name: "Batch & Status", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Batch (指標與狀態|Metrics and Status)/ })).toBeVisible();
});
