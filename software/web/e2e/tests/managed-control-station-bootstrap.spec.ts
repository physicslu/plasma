import { expect, test } from "@playwright/test";

const staleDirectGateway = "https://swpc.tail820e64.ts.net:8443";

async function seedLegacyStandaloneRouting(page: import("@playwright/test").Page) {
  await page.addInitScript(({ directGateway }) => {
    window.localStorage.setItem("plasma-api-mode", "standalone");
    window.localStorage.setItem("plasma-api-base", directGateway);
  }, { directGateway: staleDirectGateway });
}

async function expectManagedBrowserRouting(page: import("@playwright/test").Page) {
  await expect.poll(async () => page.evaluate(() => window.localStorage.getItem("plasma-api-mode")))
    .toBe("managed");
  await expect.poll(async () => page.evaluate(() => window.localStorage.getItem("plasma-api-base")))
    .toMatch(/\/api\/manager\/ppu$/);
  await expect.poll(async () => page.evaluate(() => window.localStorage.getItem("plasma-api-base")))
    .not.toBe(staleDirectGateway);
}

test("Managed Control Station overrides stale standalone Browser routing", async ({ page }) => {
  await seedLegacyStandaloneRouting(page);
  await page.route("**/api/manager/ppu", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, managed: true, configured: true, ppu_alias: "swpc" }),
    });
  });

  await page.goto("/");
  await expectManagedBrowserRouting(page);
});

test("Managed Control Station remains fail-closed when the BFF routing config is incomplete", async ({ page }) => {
  await seedLegacyStandaloneRouting(page);
  await page.route("**/api/manager/ppu", async route => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        managed: true,
        configured: false,
        error: { code: "manager_bff_misconfigured", message: "Managed PPU routing is not configured" },
      }),
    });
  });

  await page.goto("/");
  await expectManagedBrowserRouting(page);
});
