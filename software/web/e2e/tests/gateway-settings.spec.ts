import { expect, test } from "@playwright/test";

test("EMode Settings > Gateway edits shared server-owned timeout and retry settings", async ({ page }) => {
  let settings = { revision: 1, ppu_request_timeout_ms: 10_000, ppu_retry_count: 3 };
  let submitted: Record<string, number> | null = null;

  await page.route("**/api/settings/gateway", async route => {
    if (route.request().method() === "POST") {
      submitted = route.request().postDataJSON() as Record<string, number>;
      settings = { ...submitted, revision: settings.revision + 1 } as typeof settings;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, rest_contract_version: "3", gateway_settings: settings }),
    });
  });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Gateway", exact: true })).toBeVisible();
  await expect(page.getByLabel("PPU Request Timeout seconds")).toHaveValue("10");
  await expect(page.getByLabel("PPU Retry Count")).toHaveValue("3");
  await expect(page.getByText("REV 1", { exact: true })).toBeVisible();

  await page.getByLabel("PPU Request Timeout seconds").fill("20");
  await page.getByLabel("PPU Retry Count").fill("5");
  await page.getByRole("button", { name: "Apply Settings", exact: true }).click();

  await expect.poll(() => submitted).toEqual({ ppu_request_timeout_ms: 20_000, ppu_retry_count: 5 });
  await expect(page.getByText("REV 2", { exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Gateway 設定已儲存");
});
