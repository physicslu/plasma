import { expect, test } from "@playwright/test";

test("renders Programmer identity and a four-channel topology from status", async ({ page }) => {
  await page.route("**/api/status**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== "GET" || url.searchParams.has("job")) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: { message: "unhandled mock route" } }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        programmer: {
          programmer_id: "z2-e2e-04",
          site_id: "e2e-lab",
          model: "PYNQ-Z2",
          display_name: "Plasma Four Channel Fixture",
          channel_count: 4,
          enabled_channel_count: 3,
          capabilities: {
            max_supported_channels: 8,
            operations: ["erase", "program", "verify", "read"],
          },
        },
        channels: Array.from({ length: 4 }, (_, channelId) => ({
          channel_id: channelId,
          enabled: channelId < 3,
          state: channelId < 3 ? "idle" : "disabled",
          current_job_id: null,
          queued_jobs: 0,
          interface: channelId < 3 ? "mock" : null,
          target: channelId < 3 ? "STM32F103C8T6" : null,
        })),
      }),
    });
  });

  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");
  await expect(page.locator(".gatewayHealth")).toContainText("3/4 Enabled");

  const identity = page.getByLabel("Programmer identity");
  await expect(identity).toContainText("e2e-lab");
  await expect(identity).toContainText("z2-e2e-04");
  await expect(identity).toContainText("PYNQ-Z2");

  await expect(page.getByLabel("顯示 CH0")).toBeChecked();
  await expect(page.getByLabel("顯示 CH1")).toBeChecked();
  await expect(page.getByLabel("顯示 CH2")).toBeChecked();
  await expect(page.getByLabel("顯示 CH3")).not.toBeChecked();
  await expect(page.getByLabel("顯示 CH4")).toHaveCount(0);

  const topologySummary = page.getByLabel("通道配置摘要");
  await expect(topologySummary).toContainText("顯示 3 / 4");
  await expect(topologySummary).toContainText("停用 1");
  await expect(page.getByLabel("顯示 CH3").locator("..")).toContainText("停用");

  await expect(page.locator(".channelDetails")).toHaveCount(3);
});
