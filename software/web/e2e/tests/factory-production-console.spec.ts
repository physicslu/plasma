import { expect, test, type Page, type Route } from "@playwright/test";
import { commitProductionSites } from "./production-console-helpers";

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 1,
    site_count: 2,
    facilities: [{
      facility_id: facilityId,
      display_name: "Mock Facility 01",
      ppus: [{
        ppu_id: ppuId,
        display_name: "Mock PPU 01",
        model: "MOCK-PPU",
        site_count: 2,
        provider: "mock",
      }],
    }],
  };
}

function status() {
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: "Mock PPU 01",
      site_count: 2,
      enabled_site_count: 2,
      capabilities: { max_supported_sites: 2, operations: ["erase", "program", "verify", "read"] },
    },
    sites: [1, 2].map(siteId => ({
      site_id: siteId,
      enabled: true,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: "mock",
      target: "MOCK-IC",
    })),
  };
}

type BatchRequest = {
  targets: Array<{ facility_id: string; ppu_id: string; site_ids: number[] }>;
  operations: string[];
  execution_policy: { repeat_count: number; site_retry_limit: number; failed_site_stop_threshold: number | null };
  target_device?: { vendor: string; identifier: string };
};

function siteCounts(sites: Array<{ state: string }>) {
  const states = ["ready", "running", "success", "faulted", "error", "stopped", "cancelled"];
  return Object.fromEntries(states.map(state => [state, sites.filter(site => site.state === state).length]));
}

async function installFactoryMock(page: Page, options: { runtimeSiteIds?: number[] } = {}) {
  const submissions: BatchRequest[] = [];
  let request: BatchRequest | null = null;
  let cancelled = false;
  const batchId = "factory-console-v2-batch";

  function snapshot() {
    if (!request) throw new Error("Batch not submitted");
    const membership = request.targets.flatMap(target => target.site_ids
      .filter(siteId => !options.runtimeSiteIds || options.runtimeSiteIds.includes(siteId))
      .map(siteId => ({
      facility_id: target.facility_id,
      ppu_id: target.ppu_id,
      site_id: siteId,
    })));
    const sites = membership.map((site, index) => {
      const state = cancelled ? (index === 0 ? "success" : "cancelled") : "running";
      return {
        ...site,
        key: `${site.facility_id}::${site.ppu_id}::SITE${site.site_id}`,
        state,
        current_round: 1,
        completed_rounds: state === "success" ? 1 : 0,
        current_operation: state === "running" ? request!.operations[0] : null,
        current_job_id: state === "running" ? `job-${site.site_id}` : null,
        progress_percent: state === "running" ? 45 : 100,
        total_attempts: 1,
        retry_count: 0,
        final_failures: 0,
        faulted_round: null,
        faulted_operation: null,
        last_failure_source: null,
        error: null,
        operation_statistics: {},
      };
    });
    return {
      batch_id: batchId,
      state: cancelled ? "cancelled" : "running",
      created_at: "2026-08-25T00:00:00Z",
      started_at: "2026-08-25T00:00:00Z",
      finished_at: cancelled ? "2026-08-25T00:00:01Z" : null,
      operations: request.operations,
      execution_policy: request.execution_policy,
      target_device: request.target_device ? {
        vendor: request.target_device.vendor,
        family: "STM32F1",
        identifier: request.target_device.identifier,
        identifier_kind: "manufacturer_part_number",
        icpn: request.target_device.identifier,
      } : null,
      asset: null,
      read: { offset: 0, length: 256 },
      cancel_requested: cancelled,
      stop_reason: cancelled ? "operator_cancel" : null,
      error: null,
      faulted_site_count: 0,
      site_counts: siteCounts(sites),
      operation_statistics: {},
      sites,
    };
  }

  await page.route("**/api/engineering/**", async (route: Route) => {
    const http = route.request();
    const path = new URL(http.url()).pathname;
    if (path === "/api/engineering/session" && http.method() === "POST") {
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({
        ok: true,
        session: { session_id: "0123456789abcdef0123456789abcdef", previous_session_cleared: false },
      }) });
      return;
    }
    if (path === "/api/engineering/targets") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }
    if (path === `/api/engineering/targets/${facilityId}/${ppuId}/api/status`) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(status()) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });

  await page.route("**/api/devices/search**", async route => {
    const query = new URL(route.request().url()).searchParams.get("q") ?? "";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        rest_contract_version: "3",
        query,
        catalog_size: 7657,
        count: 1,
        results: [{
          vendor: "STMicroelectronics",
          family: "STM32F1",
          subfamily: null,
          plasma_series: "STM32",
          identifier: "STM32F103C8T6",
          identifier_kind: "manufacturer_part_number",
          icpn: "STM32F103C8T6",
          package: null,
          cpu_architectures: ["ARM Cortex-M3"],
          backend: { type: "openocd", distribution: "upstream-openocd", target_config: "tcl/target/stm32f1x.cfg", mapping_status: "mapping_candidate" },
          physical_validation: { engineering_status: "not_verified", ppu_status: "no_evidence", socket_status: "no_evidence" },
          catalog_origin: "test",
        }],
      }),
    });
  });

  await page.route("**/api/batches**", async (route: Route) => {
    const http = route.request();
    const path = new URL(http.url()).pathname;
    if (path === "/api/batches" && http.method() === "POST") {
      request = http.postDataJSON() as BatchRequest;
      submissions.push(request);
      cancelled = false;
      await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: snapshot() }) });
      return;
    }
    if (path === `/api/batches/${batchId}` && http.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: snapshot() }) });
      return;
    }
    if (path === `/api/batches/${batchId}/cancel` && http.method() === "POST") {
      cancelled = true;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: snapshot() }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "missing batch" } }) });
  });

  return { submissions };
}

async function commitTwoSiteProductionSet(page: Page) {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "PMODE · FACTORY CONSOLE" })).toBeVisible();
  await commitProductionSites(page, facilityId, ppuId, [1, 2]);
  await expect(page.getByRole("region", { name: "LIVE SITE STATUS" }).locator(".factorySiteLedCard")).toHaveCount(2);
}

async function chooseTarget(page: Page) {
  const target = page.getByLabel("Target IC");
  await target.fill("STM32F103C8T6");
  await expect(page.getByRole("listbox", { name: "Target IC search results" })).toBeVisible();
  await page.getByRole("option", { name: /STM32F103C8T6/ }).click();
}

test("Production Set stays visible while the operator changes next-Batch PPU/Site membership", async ({ page }) => {
  await installFactoryMock(page);
  await commitTwoSiteProductionSet(page);

  const live = page.getByRole("region", { name: "LIVE SITE STATUS" });
  const ppu = live.getByRole("checkbox", { name: "Batch select Mock PPU 01", exact: true });
  const site1 = live.getByRole("checkbox", { name: "Batch select Mock PPU 01 SITE-01", exact: true });
  const site2 = live.getByRole("checkbox", { name: "Batch select Mock PPU 01 SITE-02", exact: true });
  await expect(ppu).toBeChecked();
  await expect(site1).toBeChecked();
  await expect(site2).toBeChecked();

  await site2.uncheck();
  await expect(page.locator('[data-kpi="production-sites"] b')).toHaveText("2");
  await expect(page.locator('[data-kpi="selected"] b')).toHaveText("1");
  await expect.poll(() => ppu.evaluate((element: HTMLInputElement) => element.indeterminate)).toBe(true);
  await expect(live.locator('[data-production-site="2"]')).toHaveAttribute("data-batch-selected", "false");

  await page.getByRole("button", { name: /收起|Hide/ }).click();
  await expect(page.getByRole("region", { name: "PRODUCTION SITE SELECTION" }).locator(".operatorPanelBody")).toBeHidden();
  await expect(live.locator(".factorySiteLedCard")).toHaveCount(2);
});

test("START snapshots Batch membership; running selection is locked and only whole-Batch ABORT is exposed", async ({ page }) => {
  const mock = await installFactoryMock(page);
  await commitTwoSiteProductionSet(page);
  await chooseTarget(page);

  const programming = page.getByRole("region", { name: "PROGRAMMING JOB" });
  await programming.locator(".factoryOperationChecks label").filter({ hasText: /E/ }).getByRole("checkbox").check();
  await programming.getByRole("button", { name: /START PROGRAMMING/ }).click();

  await expect.poll(() => mock.submissions.length).toBe(1);
  expect(mock.submissions[0].targets).toEqual([{ facility_id: facilityId, ppu_id: ppuId, site_ids: [1, 2] }]);
  expect(mock.submissions[0].target_device).toEqual({ vendor: "STMicroelectronics", identifier: "STM32F103C8T6" });

  const live = page.getByRole("region", { name: "LIVE SITE STATUS" });
  await expect(live.getByRole("checkbox", { name: "Batch select Mock PPU 01", exact: true })).toBeDisabled();
  await expect(live.getByRole("checkbox", { name: "Batch select Mock PPU 01 SITE-01" })).toBeDisabled();
  await expect(live.getByRole("checkbox", { name: "Batch select Mock PPU 01 SITE-02" })).toBeDisabled();
  await expect(page.getByText("Cancel PPU", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/Cancel Site/i)).toHaveCount(0);

  const abort = programming.getByRole("button", { name: /ABORT/ });
  await expect(abort).toBeEnabled();
  await abort.click();
  await expect(page.locator(".factoryBatchStatus b")).toHaveText("CANCELLED");

  await expect(page.locator('[data-kpi="pass"] b')).toHaveText("1");
  await expect(page.locator('[data-kpi="fail"] b')).toHaveText("0");
  await expect(page.locator('[data-kpi="yield"] b')).toHaveText("100.0%");

  await expect(live.getByRole("checkbox", { name: "Batch select Mock PPU 01 SITE-01" })).toBeEnabled();
  await expect(live.getByRole("checkbox", { name: "Batch select Mock PPU 01 SITE-02" })).toBeEnabled();
});

test("active membership and RUNNING KPI follow Server Batch Runtime instead of operator Batch Selection", async ({ page }) => {
  const mock = await installFactoryMock(page, { runtimeSiteIds: [1] });
  await commitTwoSiteProductionSet(page);
  await chooseTarget(page);

  const programming = page.getByRole("region", { name: "PROGRAMMING JOB" });
  await programming.locator(".factoryOperationChecks label").filter({ hasText: /E/ }).getByRole("checkbox").check();
  await programming.getByRole("button", { name: /START PROGRAMMING/ }).click();

  await expect.poll(() => mock.submissions.length).toBe(1);
  expect(mock.submissions[0].targets).toEqual([{ facility_id: facilityId, ppu_id: ppuId, site_ids: [1, 2] }]);

  const live = page.getByRole("region", { name: "LIVE SITE STATUS" });
  await expect(page.locator('[data-kpi="production-sites"] b')).toHaveText("2");
  await expect(page.locator('[data-kpi="selected"] b')).toHaveText("1");
  await expect(page.locator('[data-kpi="running"] b')).toHaveText("1");
  await expect(live.getByRole("checkbox", { name: "Batch select Mock PPU 01 SITE-01" })).toBeChecked();
  await expect(live.getByRole("checkbox", { name: "Batch select Mock PPU 01 SITE-02" })).not.toBeChecked();
  await expect(live.locator('[data-production-site="1"]')).toHaveAttribute("data-batch-selected", "true");
  await expect(live.locator('[data-production-site="2"]')).toHaveAttribute("data-batch-selected", "false");

  await programming.getByRole("button", { name: /ABORT/ }).click();
  await expect(page.locator(".factoryBatchStatus b")).toHaveText("CANCELLED");
  await expect(page.locator('[data-kpi="selected"] b')).toHaveText("2");
  await expect(live.getByRole("checkbox", { name: "Batch select Mock PPU 01 SITE-01" })).toBeChecked();
  await expect(live.getByRole("checkbox", { name: "Batch select Mock PPU 01 SITE-02" })).toBeChecked();
});
