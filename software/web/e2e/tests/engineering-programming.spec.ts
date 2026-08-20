import { expect, test } from "@playwright/test";

test("Engineering Programming exposes the 3x4 simulated Facility and heterogeneous PPU topology", async ({ page }) => {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await page.getByRole("button", { name: "Simulation Catalog", exact: true }).click();

  const facility = page.getByLabel("Engineering Facility");
  const ppu = page.getByLabel("Engineering PPU");
  await expect(facility.locator("option")).toHaveCount(3);
  await expect(ppu.locator("option")).toHaveCount(4);

  await ppu.selectOption("2");
  await expect(page.getByLabel("Selected simulated PPU")).toContainText("Facility 01 / PPU 03");
  await expect(page.getByLabel("Selected simulated PPU")).toContainText("6 Sites");
  await expect(page.locator(".simulatedSiteCard")).toHaveCount(6);
  await expect(page.getByText("SITE 1", { exact: true })).toBeVisible();
  await expect(page.getByText("SITE 6", { exact: true })).toBeVisible();
  await expect(page.getByText("SITE 0", { exact: true })).toHaveCount(0);
  await expect(page.getByText("SITE 7", { exact: true })).toHaveCount(0);

  await facility.selectOption("facility-03");
  await expect(ppu).toHaveValue("0");
  await expect(page.locator(".simulatedSiteCard")).toHaveCount(2);

  await ppu.selectOption("3");
  await expect(page.getByLabel("Selected simulated PPU")).toContainText("Facility 03 / PPU 04");
  await expect(page.locator(".simulatedSiteCard")).toHaveCount(8);
  await expect(page.getByLabel("SITE 1 Erase simulated")).toBeDisabled();
  await expect(page.getByLabel("SITE 1 Program simulated")).toBeDisabled();
  await expect(page.getByLabel("SITE 1 Verify simulated")).toBeDisabled();
  await expect(page.getByLabel("SITE 1 Read simulated")).toBeDisabled();
  await expect(page.getByText("NO HARDWARE EXECUTION")).toBeVisible();
});

test("Engineering Programming restores the connected local single-PPU E/P/V/R console", async ({ page }) => {
  await page.route("**/api/status**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== "GET" || url.searchParams.has("job")) {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled mock route" } }) });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        ppu: {
          ppu_id: "engineering-local-e2e",
          facility_id: "engineering-lab",
          model: "PYNQ-Z2",
          display_name: "Engineering Local Fixture",
          site_count: 4,
          enabled_site_count: 4,
          capabilities: { max_supported_sites: 8, operations: ["erase", "program", "verify", "read"] },
        },
        sites: Array.from({ length: 4 }, (_, index) => ({
          site_id: index + 1,
          enabled: true,
          state: "idle",
          current_job_id: null,
          queued_jobs: 0,
          interface: "mock",
          target: "STM32F103C8T6",
        })),
      }),
    });
  });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  await expect(page.getByText("LOCAL EXECUTION")).toBeVisible();
  await expect(page.getByRole("button", { name: "Connected Local PPU", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".gatewayHealth")).toContainText("Online");
  await expect(page.getByLabel("PPU identity")).toContainText("engineering-lab");
  await expect(page.getByLabel("PPU identity")).toContainText("engineering-local-e2e");
  await expect(page.locator(".channelDetails")).toHaveCount(4);

  await expect(page.getByLabel("SITE 1 擦除")).toBeVisible();
  await expect(page.getByLabel("SITE 1 燒錄")).toBeVisible();
  await expect(page.getByLabel("SITE 1 驗證")).toBeVisible();
  await expect(page.getByLabel("SITE 1 讀取")).toBeVisible();
  await expect(page.getByLabel("顯示 SITE 0")).toHaveCount(0);
});
