import { expect, test } from "@playwright/test";

async function installEmptyEngineeringCatalog(page: import("@playwright/test").Page) {
  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: "0123456789abcdef0123456789abcdef",
            programming_asset_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: false,
          },
        }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          provider: "mock",
          facility_count: 0,
          ppu_count: 0,
          site_count: 0,
          programming_asset_scope: "connection-session-and-ppu",
          facilities: [],
        }),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

test("Pmod image controls precede EPVR and Pmod Emode share persistent Light Dark preference", async ({ page }) => {
  await installEmptyEngineeringCatalog(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();

  const imageBox = await page.locator(".productionImagePicker").boundingBox();
  const operationsBox = await page.locator(".batchOperations").boundingBox();
  expect(imageBox).not.toBeNull();
  expect(operationsBox).not.toBeNull();
  expect(imageBox!.y + imageBox!.height).toBeLessThanOrEqual(operationsBox!.y);
  expect(imageBox!.x).toBeLessThanOrEqual(operationsBox!.x);

  const theme = page.getByRole("group", { name: "Theme" });
  await expect(theme.getByRole("button", { name: "Light", exact: true })).toHaveAttribute("aria-pressed", "true");
  await theme.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(theme.getByRole("button", { name: "Dark", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("plasma-theme"))).toBe("dark");
  await expect.poll(() => page.locator(".productionPrototypePage").evaluate(element => getComputedStyle(element).backgroundColor)).toBe("rgb(7, 17, 29)");

  await page.goto("/engineering");
  await expect(page.getByRole("heading", { name: /Engineering/i })).toBeVisible();
  const engineeringTheme = page.getByRole("group", { name: "Theme" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(engineeringTheme.getByRole("button", { name: "Dark", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => page.locator(".engineeringPage").evaluate(element => getComputedStyle(element).backgroundColor)).toBe("rgb(7, 17, 29)");

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("group", { name: "Theme" }).getByRole("button", { name: "Dark", exact: true })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("group", { name: "Theme" }).getByRole("button", { name: "Light", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("plasma-theme"))).toBe("light");
});
