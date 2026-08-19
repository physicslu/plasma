import { expect, test } from "@playwright/test";

function latestJob(job_id: string, operation: string, state: string, progress_percent = 100) {
  return {
    job_id,
    operation,
    state,
    stage: operation,
    stage_state: state,
    progress_percent,
    created_at: "2026-08-19T13:00:00Z",
    started_at: "2026-08-19T13:00:01Z",
    updated_at: "2026-08-19T13:00:02Z",
    cancel_requested: false,
  };
}

const fleetPayload = {
  ok: true,
  contract_version: "1",
  observed_at: "2026-08-19T13:00:00Z",
  degraded: false,
  summary: {
    configured_ppus: 2, reachable_ppus: 2, ready_ppus: 2, current_ppus: 2,
    stale_ppus: 0, unknown_ppus: 0, reported_sites: 6, enabled_sites: 5, identity_conflicts: 0,
  },
  manager: {
    cache_age_s: 0.2, poll_interval_s: 2, refresh_healthy: true,
    observation_store: { mode: "memory", healthy: true, writable: true },
  },
  ppus: [
    {
      alias: "PPU-A",
      identity: { ppu_id: "PPU-A", facility_id: "FACTORY-1", model: "Mock-8", display_name: "PPU-A" },
      transport_state: "reachable", execution_state: "ready",
      observation: { state: "current", last_success_at: "2026-08-19T13:00:00Z", stale_age_s: 0 },
      topology: {
        source: "current", site_count: 4, enabled_site_count: 3,
        sites: [
          { site_id: 1, enabled: true, state: "idle", current_job_id: null, latest_job: null, interface: "mock", target: "IC-A" },
          { site_id: 2, enabled: true, state: "idle", current_job_id: null, latest_job: latestJob("job-p", "program", "success"), interface: "mock", target: "IC-A" },
          { site_id: 3, enabled: true, state: "idle", current_job_id: null, latest_job: latestJob("job-v", "verify", "failed"), interface: "mock", target: "IC-A" },
          { site_id: 4, enabled: false, state: "disabled", current_job_id: null, latest_job: null, interface: null, target: null },
        ],
      },
      current_capacity: { site_count: 4, enabled_site_count: 3 }, identity_conflict: false, degraded: false,
    },
    {
      alias: "PPU-B",
      identity: { ppu_id: "PPU-B", facility_id: "FACTORY-1", model: "Mock-2", display_name: "PPU-B" },
      transport_state: "reachable", execution_state: "ready",
      observation: { state: "current", last_success_at: "2026-08-19T13:00:00Z", stale_age_s: 0 },
      topology: {
        source: "current", site_count: 2, enabled_site_count: 2,
        sites: [
          { site_id: 1, enabled: true, state: "running", current_job_id: "job-running", latest_job: latestJob("job-running", "program", "running", 63), interface: "mock", target: "IC-B" },
          { site_id: 2, enabled: true, state: "idle", current_job_id: null, latest_job: null, interface: "mock", target: "IC-B" },
        ],
      },
      current_capacity: { site_count: 2, enabled_site_count: 2 }, identity_conflict: false, degraded: false,
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/fleet", async route => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fleetPayload) });
  });
});

test("Production Mode uses real job state for lamps, operations, selection and local result acknowledgement", async ({ page }) => {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();
  await expect(page.getByText("工廠量產監控 · 所有 PPU × Site 同畫面")).toBeVisible();

  for (const code of ["E", "P", "V", "R"]) {
    await expect(page.locator(".operationChecks label").filter({ hasText: code })).toBeVisible();
  }

  const ppuA = page.locator('[data-ppu="PPU-A"]');
  await expect(ppuA.locator("[data-site-id]")).toHaveCount(4);
  await ppuA.getByRole("button", { name: "全選", exact: true }).click();
  await expect(ppuA.locator('input[type="checkbox"]:checked')).toHaveCount(3);
  await expect(ppuA.getByRole("checkbox", { name: "PPU-A SITE 4" })).toBeDisabled();
  await ppuA.getByRole("button", { name: "全部取消", exact: true }).click();
  await expect(page.getByText(/已選 Sites: 0/)).toBeVisible();

  // IDLE with no job must remain READY; it must never be misread as READ/RUNNING.
  await expect(ppuA.locator('[data-site-id="1"]')).toHaveAttribute("data-status", "ready");
  await expect(ppuA.locator('[data-site-id="1"] .siteCardMeta')).toContainText("—");
  await expect(ppuA.locator('[data-site-id="2"]')).toHaveAttribute("data-status", "pass");
  await expect(ppuA.locator('[data-site-id="2"] .siteCardMeta')).toContainText("P");
  await expect(ppuA.locator('[data-site-id="3"]')).toHaveAttribute("data-status", "fail");
  await expect(ppuA.locator('[data-site-id="3"] .siteCardMeta')).toContainText("V");
  await expect(ppuA.locator('[data-site-id="4"]')).toHaveAttribute("data-status", "disabled");
  await expect(page.locator('[data-ppu="PPU-B"] [data-site-id="1"]')).toHaveAttribute("data-status", "running");
  await expect(page.locator('[data-ppu="PPU-B"] [data-site-id="1"]')).toContainText("63%");

  await ppuA.locator('[data-site-id="3"]').click();
  const detail = page.getByRole("complementary", { name: "Site Detail" });
  await expect(detail.getByRole("heading", { name: "SITE 3" })).toBeVisible();
  await expect(detail.getByText("FAIL", { exact: true })).toBeVisible();
  await expect(detail.getByText("LATCHED", { exact: true })).toBeVisible();
  await expect(detail.getByText("job-v", { exact: true })).toBeVisible();

  await detail.getByRole("button", { name: "清除結果", exact: true }).click();
  await expect(ppuA.locator('[data-site-id="3"]')).toHaveAttribute("data-status", "ready");
  await page.waitForTimeout(2_200);
  await expect(ppuA.locator('[data-site-id="3"]')).toHaveAttribute("data-status", "ready");

  const log = page.getByRole("region", { name: "Factory Log Console" });
  await expect(log).toBeVisible();
  await expect(log).toContainText("Job 狀態更新");
  await expect(log).toContainText("job-p SUCCESS");
  await expect(page.getByText(/latest-job 摘要/)).toBeVisible();

  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Product mode" }).getByRole("link", { name: "Production Mode", exact: true })).toBeVisible();
  await expect(ppuA.getByRole("button", { name: "Select All", exact: true })).toBeVisible();
  await expect(page.locator(".operationChecks label").filter({ hasText: "Program" })).toBeVisible();
});
