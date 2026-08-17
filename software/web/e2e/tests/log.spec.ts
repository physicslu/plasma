import { expect, test } from "@playwright/test";

test("renders invalid Gateway input as a highlighted English error log", async ({ page }) => {
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "GET" && url.pathname === "/api/status" && !url.searchParams.has("job")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          channels: Array.from({ length: 8 }, (_, channelId) => ({
            channel_id: channelId,
            enabled: channelId < 2,
            state: "idle",
            current_job_id: null,
            queued_jobs: 0,
            interface: channelId < 2 ? "Mock" : null,
            target: channelId < 2 ? "STM32F103C8T6" : null,
          })),
        }),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "not found" } }) });
  });

  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");

  await page.getByLabel("Plasma Web REST Gateway URL").fill("not a url");
  await page.getByRole("button", { name: "連線" }).click();

  const errorLine = page.getByLabel("Live job log").locator('[data-level="error"]');
  await expect(errorLine).toHaveCount(1);
  await expect(errorLine).toContainText("[ERROR]");
  await expect(errorLine).toContainText("[NET]");
  await expect(errorLine).toHaveCSS("font-weight", "700");
  await expect(errorLine).toHaveCSS("border-left-style", "solid");
});
