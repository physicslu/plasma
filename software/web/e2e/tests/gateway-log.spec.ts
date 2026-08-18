import { expect, test, type Page, type Route } from "@playwright/test";

const defaultGateway = "https://plasma.open4th.com";
const wrongGateway = "https://wrong-gateway.example.invalid";

function channels() {
  return Array.from({ length: 8 }, (_, channelId) => ({
    channel_id: channelId,
    enabled: channelId < 2,
    state: "idle",
    current_job_id: null,
    queued_jobs: 0,
    interface: channelId < 2 ? "Mock" : null,
    target: channelId < 2 ? "STM32F103C8T6" : null,
  }));
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function openOnlineConsole(page: Page) {
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.origin === wrongGateway) {
      await route.abort("failed");
      return;
    }

    if (
      url.origin === defaultGateway
      && request.method() === "GET"
      && url.pathname === "/api/status"
      && !url.searchParams.has("job")
    ) {
      await fulfillJson(route, { ok: true, channels: channels() });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "unhandled mock route" } }),
    });
  });

  await page.goto("/");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");
  await expect(page.getByLabel("Live job log")).toContainText(
    `Plasma Web REST Gateway connected · ${defaultGateway}`,
  );
}

test("offline Gateway log always includes the attempted endpoint", async ({ page }) => {
  await openOnlineConsole(page);

  const gatewayInput = page.getByLabel("Plasma Web REST Gateway URL");
  await gatewayInput.fill(wrongGateway);
  await page.getByRole("button", { name: "連線" }).click();

  const offlineLine = page.getByLabel("Live job log").locator("span")
    .filter({ hasText: "Plasma Web REST Gateway offline" })
    .filter({ hasText: wrongGateway });
  await expect(offlineLine).toHaveCount(1);
  await expect(offlineLine).toContainText(wrongGateway);
  await expect(offlineLine).toHaveAttribute("data-level", "error");
});

test("rejected Gateway log includes the invalid endpoint text", async ({ page }) => {
  await openOnlineConsole(page);

  const invalidGateway = "ftp://wrong-gateway.local";
  const gatewayInput = page.getByLabel("Plasma Web REST Gateway URL");
  await gatewayInput.fill(invalidGateway);
  await page.getByRole("button", { name: "連線" }).click();

  const rejectedLine = page.getByLabel("Live job log").locator("span")
    .filter({ hasText: "Plasma Web REST Gateway rejected" })
    .filter({ hasText: invalidGateway });
  await expect(rejectedLine).toHaveCount(1);
  await expect(rejectedLine).toContainText(invalidGateway);
  await expect(rejectedLine).toHaveAttribute("data-level", "error");
});
