import { expect, test } from "@playwright/test";

async function settingsVisualContract(page: import("@playwright/test").Page) {
  return await page.evaluate(() => {
    function style(selector: string) {
      const element = document.querySelector(selector);
      if (!(element instanceof HTMLElement)) throw new Error(`Missing ${selector}`);
      const computed = window.getComputedStyle(element);
      return {
        borderRadius: computed.borderRadius,
        padding: computed.padding,
        backgroundColor: computed.backgroundColor,
        fontSize: computed.fontSize,
        fontWeight: computed.fontWeight,
      };
    }
    return {
      card: style(".settingsCard"),
      guide: style(".settingsGuide"),
      primaryAction: style('.settingsActions button[data-variant="primary"]'),
      field: style(".settingsField input, .settingsField select"),
    };
  });
}

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

  const guide = page.getByRole("region", { name: "Gateway Settings Guide" });
  await expect(guide).toBeVisible();
  await expect(guide).toContainText("Gateway 設定說明");
  await expect(guide).toContainText("測試方法");
  await expect(guide).toContainText("Mock 的 E/P/V/R Error Rate");

  const canvasBox = await page.locator(".engineeringCanvas.settingsActive").boundingBox();
  const panelBox = await page.locator(".engineeringGatewaySettings").boundingBox();
  expect(canvasBox).not.toBeNull();
  expect(panelBox).not.toBeNull();
  expect((panelBox?.y ?? 0) - (canvasBox?.y ?? 0)).toBeLessThanOrEqual(24);

  await page.getByLabel("PPU Request Timeout seconds").fill("20");
  await page.getByLabel("PPU Retry Count").fill("5");
  await page.getByRole("button", { name: "Apply Settings", exact: true }).click();

  await expect.poll(() => submitted).toEqual({ ppu_request_timeout_ms: 20_000, ppu_retry_count: 5 });
  await expect(page.getByText("REV 2", { exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Gateway 設定已儲存");
});

test("Gateway and Mock share the same Settings visual contract", async ({ page }) => {
  const gatewaySettings = { revision: 2, ppu_request_timeout_ms: 10_000, ppu_retry_count: 3 };
  const mockSettings = {
    profile_id: "default",
    revision: 2,
    enabled: true,
    default_image_size_bytes: 1024 * 1024,
    seed: { mode: "auto", fixed_seed: null },
    operations: {
      erase: { error_rate_per_mille: 1, base_time_ms: 1000, throughput_bytes_per_second: 2048 * 1024, jitter_ms: 200 },
      program: { error_rate_per_mille: 50, base_time_ms: 500, throughput_bytes_per_second: 512 * 1024, jitter_ms: 200 },
      verify: { error_rate_per_mille: 20, base_time_ms: 300, throughput_bytes_per_second: 1024 * 1024, jitter_ms: 100 },
      read: { error_rate_per_mille: 5, base_time_ms: 200, throughput_bytes_per_second: 1024 * 1024, jitter_ms: 100 },
    },
  };

  await page.route("**/api/settings/gateway", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ ok: true, rest_contract_version: "3", gateway_settings: gatewaySettings }),
  }));
  await page.route("**/api/mock/runtime", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ ok: true, mock_runtime: mockSettings }),
  }));

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("region", { name: "Gateway Settings Guide" })).toBeVisible();
  const gatewayVisual = await settingsVisualContract(page);
  const gatewayCanvas = await page.locator(".engineeringCanvas.settingsActive").boundingBox();
  const gatewayPage = await page.locator(".settingsPage").boundingBox();

  await page.getByRole("button", { name: "Mock", exact: true }).click();
  await expect(page.getByRole("region", { name: "Mock Settings Guide" })).toBeVisible();
  const mockVisual = await settingsVisualContract(page);
  const mockCanvas = await page.locator(".engineeringCanvas.settingsActive").boundingBox();
  const mockPage = await page.locator(".settingsPage").boundingBox();

  expect(mockVisual).toEqual(gatewayVisual);
  expect(gatewayCanvas).not.toBeNull();
  expect(gatewayPage).not.toBeNull();
  expect(mockCanvas).not.toBeNull();
  expect(mockPage).not.toBeNull();
  expect((gatewayPage?.y ?? 0) - (gatewayCanvas?.y ?? 0)).toBeLessThanOrEqual(24);
  expect((mockPage?.y ?? 0) - (mockCanvas?.y ?? 0)).toBeLessThanOrEqual(24);
});
