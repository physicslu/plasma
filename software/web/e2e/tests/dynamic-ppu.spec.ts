import { expect, test } from "@playwright/test";

test("renders PPU identity and a four-site topology from canonical status", async ({ page }) => {
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
        ppu: {
          ppu_id: "z2-e2e-04",
          facility_id: "e2e-lab",
          model: "PYNQ-Z2",
          display_name: "Plasma Four Site Fixture",
          site_count: 4,
          enabled_site_count: 3,
          capabilities: {
            max_supported_sites: 8,
            operations: ["erase", "program", "verify", "read"],
          },
        },
        sites: Array.from({ length: 4 }, (_, siteId) => ({
          site_id: siteId,
          enabled: siteId < 3,
          state: siteId < 3 ? "idle" : "disabled",
          current_job_id: null,
          queued_jobs: 0,
          interface: siteId < 3 ? "mock" : null,
          target: siteId < 3 ? "STM32F103C8T6" : null,
        })),
      }),
    });
  });

  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");
  await expect(page.locator(".gatewayHealth")).toContainText("3/4 Enabled");

  const identity = page.getByLabel("PPU identity");
  await expect(identity).toContainText("Facility");
  await expect(identity).toContainText("e2e-lab");
  await expect(identity).toContainText("PPU");
  await expect(identity).toContainText("z2-e2e-04");
  await expect(identity).toContainText("PYNQ-Z2");

  await expect(page.getByLabel("顯示 SITE 0")).toBeChecked();
  await expect(page.getByLabel("顯示 SITE 1")).toBeChecked();
  await expect(page.getByLabel("顯示 SITE 2")).toBeChecked();
  await expect(page.getByLabel("顯示 SITE 3")).not.toBeChecked();
  await expect(page.getByLabel("顯示 SITE 4")).toHaveCount(0);

  const topologySummary = page.getByLabel("Site 配置摘要");
  await expect(topologySummary).toContainText("顯示 3 / 4");
  await expect(topologySummary).toContainText("停用 1");
  await expect(page.getByLabel("顯示 SITE 3").locator("..")).toContainText("停用");

  await expect(page.locator(".channelDetails")).toHaveCount(3);
  await expect(page.locator(".channelDetails").first()).toContainText("SITE 0");
});
