import { expect, test } from "@playwright/test";

const rawManagedProviderError = "Managed PPU returned a non-JSON response for a JSON API route";

test("EMode keeps raw managed-provider detail out of the operator availability notice", async ({ page }) => {
  await page.route("**/api/settings/gateway", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        gateway_settings: {
          revision: 1,
          ppu_request_timeout_ms: 5_000,
          ppu_retry_count: 0,
          ppu_response_budget_ms: 5_000,
        },
      }),
    });
  });

  await page.route("**/api/engineering/session", async route => {
    await route.fulfill({
      status: 502,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        error: { message: rawManagedProviderError },
      }),
    });
  });

  await page.route("**/api/health/live", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, gateway: "plasma-web" }),
    });
  });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  const availability = page.locator(".engineeringBoundaryNote.warning");
  await expect(availability).toBeVisible();
  await expect(availability.locator("b")).toContainText(/燒錄功能目前不可用|Programming unavailable/i);
  await expect(availability.locator(":scope > span")).toBeHidden();
  await expect(page.locator(".engineeringGateway")).toHaveClass(/online/);

  // The diagnostic detail is still retained by the Engineering Job Log.
  await expect(page.locator(".engineeringOperatorLog")).toContainText(rawManagedProviderError);
});
