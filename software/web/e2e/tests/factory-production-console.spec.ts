import { expect, test } from "@playwright/test";

const fleetPayload = {
  ok: true,
  contract_version: "1",
  observed_at: "2026-08-19T13:00:00Z",
  degraded: false,
  summary: {
    configured_ppus: 2,
    reachable_ppus: 2,
    ready_ppus: 2,
    current_ppus: 2,
    stale_ppus: 0,
    unknown_ppus: 0,
    reported_sites: 6,
    enabled_sites: 5,
    identity_conflicts: 0,
  },
  manager: {
    cache_age_s: 0.2,
    poll_interval_s: 2,
    refresh_healthy: true,
    observation_store: { mode: "memory", healthy: true, writable: true },
  },
  ppus: [
    {
      alias: "PPU-A",
      identity: { ppu_id: "PPU-A", facility_id: "FACTORY-1", model: "Mock-8", display_name: "PPU-A" },
      transport_state: "reachable",
      execution_state: "ready",
      observation: { state: "current", last_success_at: "2026-08-19T13:00:00Z", stale_age_s: 0 },
      topology: {
        source: "current",
        site_count: 4,
        enabled_site_count: 3,
        sites: [
          { site_id: 1, enabled: true, state: "ready", interface: "mock", target: "IC-A" },
          { site_id: 2, enabled: true, state: "success", interface: "mock", target: "IC-A" },
          { site_id: 3, enabled: true, state: "verify_failed", interface: "mock", target: "IC-A" },
          { site_id: 4, enabled: false, state: "disabled", interface: "mock", target: null },
        ],
      },
      current_capacity: { site_count: 4, enabled_site_count: 3 },
      identity_conflict: false,
      degraded: false,
    },
    {
      alias: "PPU-B",
      identity: { ppu_id: "PPU-B", facility_id: "FACTORY-1", model: "Mock-2", display_name: "PPU-B" },
      transport_state: "reachable",
      execution_state: "ready",
      observation: { state: "current", last_success_at: "2026-08-19T13:00:00Z", stale_age_s: 0 },
      topology: {
        source: "current",
        site_count: 2,
        enabled_site_count: 2,
        sites: [
          { site_id: 1, enabled: true, state: "program", interface: "mock", target: "IC-B" },
          { site_id: 2, enabled: true, state: "ready", interface: "mock", target: "IC-B" },
        ],
      },
      current_capacity: { site_count: 2, enabled_site_count: 2 },
      identity_conflict: false,
      degraded: false,
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/fleet", async route => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fleetPayload) });
  });
});

test("Production Mode shows heterogeneous PPUs, E/P/V/R and per-PPU selection", async ({ page }) => {
  await page.goto("/fleet");

  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();
  await expect(page.getByText("工廠量產監控 · 所有 PPU × Site 同畫面")).toBeVisible();

  for (const code of ["E", "P", "V", "R"]) {
    await expect(page.locator(".operationChecks label").filter({ hasText: code })).toBeVisible();
  }

  const ppuA = page.locator('[data-ppu="PPU-A"]');
  await expect(ppuA.locator("[data-site-id]")).toHaveCount(4);
  await ppuA.getByRole("button", { name: "全選" }).click();
  await expect(ppuA.getByRole("checkbox", { name: /PPU-A SITE/ })).toHaveCount(4);
  await expect(ppuA.locator('input[type="checkbox"]:checked')).toHaveCount(3);
  await expect(ppuA.getByRole("checkbox", { name: "PPU-A SITE 4" })).toBeDisabled();

  await ppuA.getByRole("button", { name: "全部取消" }).click();
  await expect(page.getByText(/已選 Sites: 0/)).toBeVisible();

  await expect(ppuA.locator('[data-site-id="2"]')).toHaveAttribute("data-status", "pass");
  await expect(ppuA.locator('[data-site-id="3"]')).toHaveAttribute("data-status", "fail");
  await expect(ppuA.locator('[data-site-id="4"]')).toHaveAttribute("data-status", "disabled");
  await expect(page.locator('[data-ppu="PPU-B"] [data-site-id="1"]')).toHaveAttribute("data-status", "running");

  await ppuA.locator('[data-site-id="3"]').click();
  const detail = page.getByRole("complementary", { name: "Site Detail" });
  await expect(detail.getByRole("heading", { name: "SITE 3" })).toBeVisible();
  await expect(detail.getByText("FAIL", { exact: true })).toBeVisible();
  await expect(detail.getByText("LATCHED", { exact: true })).toBeVisible();

  await expect(page.getByRole("region", { name: "Factory Log Console" })).toBeVisible();
  await expect(page.getByText(/Manager\/Fleet observation event/)).toBeVisible();

  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Work mode" }).getByRole("link", { name: "Production Mode" })).toBeVisible();
  await expect(ppuA.getByRole("button", { name: "Select All" })).toBeVisible();
  await expect(page.locator(".operationChecks label").filter({ hasText: "Program" })).toBeVisible();
});
