import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppuId = "mock-facility-01-ppu-01";

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 3,
    ppu_count: 12,
    site_count: 60,
    programming_asset_scope: "connection-session-and-ppu",
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

function ppuStatus() {
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

async function installApi(page: Page, submissions: Array<Record<string, unknown>>) {
  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: "engineering-programming-v2-session-0001",
            programming_asset_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: false,
          },
        }),
      });
      return;
    }
    if (path === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }
    if (path === `/api/engineering/targets/${facilityId}/${ppuId}/api/status` && request.method() === "GET" && !url.searchParams.has("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ppuStatus()) });
      return;
    }
    if (path === `/api/engineering/targets/${facilityId}/${ppuId}/api/jobs` && request.method() === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      submissions.push(body);
      const siteId = Number(body.site_id);
      const operation = String(body.operation);
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job: {
            job_id: `engineering-v2-${operation}-${siteId}`,
            site_id: siteId,
            operation,
            state: "queued",
            cancel_requested: false,
            stage: null,
            stage_state: null,
            stage_progress_percent: 0,
            progress_percent: 0,
            bytes_done: null,
            bytes_total: null,
          },
        }),
      });
      return;
    }
    if (path === `/api/engineering/targets/${facilityId}/${ppuId}/api/status` && request.method() === "GET" && url.searchParams.has("job")) {
      const jobId = url.searchParams.get("job") ?? "";
      const parts = jobId.split("-");
      const siteId = Number(parts.at(-1));
      const operation = parts.at(-2) ?? "erase";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job: {
            job_id: jobId,
            site_id: siteId,
            operation,
            state: "success",
            cancel_requested: false,
            stage: operation,
            stage_state: "done",
            stage_progress_percent: 100,
            progress_percent: 100,
            bytes_done: null,
            bytes_total: null,
            result: { state: "success", output_files: [] },
          },
        }),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: `unhandled ${path}` } }) });
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
          backend: {
            type: "openocd",
            distribution: "upstream-openocd",
            target_config: "tcl/target/stm32f1x.cfg",
            mapping_status: "mapping_candidate",
          },
          physical_validation: {
            engineering_status: "not_verified",
            ppu_status: "no_evidence",
            socket_status: "no_evidence",
          },
          catalog_origin: "e2e",
        }],
      }),
    });
  });
}

test("Engineering Programming renders the status-first v2 workflow and binds Target IC to a direct PPU job", async ({ page }) => {
  const submissions: Array<Record<string, unknown>> = [];
  await installApi(page, submissions);
  await page.setViewportSize({ width: 1536, height: 1000 });
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  await expect(page.getByRole("heading", { name: "SINGLE PPU PROGRAMMING" })).toBeVisible();
  await expect(page.getByText("SYSTEM SETUP & TARGETING", { exact: true })).toBeVisible();
  await expect(page.getByText("PROGRAMMING JOB", { exact: true })).toBeVisible();
  await expect(page.getByText("LIVE PROGRESS MONITOR", { exact: true })).toHaveCount(0);
  await expect(page.getByText("TARGET SITES", { exact: true })).toHaveCount(0);
  await expect(page.getByText("LIVE SITE STATUS", { exact: true })).toBeVisible();
  await expect(page.getByText("RECENT EVENTS", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Site Retry Limit")).toHaveValue("3");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await expect(page.getByLabel("Batch select SITE 1")).toBeChecked();
  await expect(page.getByLabel("Batch select SITE 2")).toBeChecked();

  const target = page.getByLabel("Target IC");
  await target.fill("STM32F103C8T6");
  await expect(page.getByRole("listbox", { name: "Target IC search results" })).toBeVisible();
  await page.getByRole("option", { name: /STM32F103C8T6/ }).click();
  await expect(target).toHaveValue("STM32F103C8T6");

  await page.getByLabel("SITE 1 擦除").click();
  await expect.poll(() => submissions.length).toBe(1);
  expect(submissions[0].site_id).toBe(1);
  expect(submissions[0].operation).toBe("erase");
  expect(submissions[0].target_device).toEqual({
    vendor: "STMicroelectronics",
    identifier: "STM32F103C8T6",
  });

  const siteOne = page.locator(".channelTable tbody tr").filter({ hasText: "SITE-01" });
  await expect(siteOne.locator(".state")).toContainText("SUCCESS");
  await expect(siteOne.locator(".engineeringResult")).toHaveText("PASS");
});

test("unselected Sites stay visible and START PROGRAMMING snapshots only checked Sites", async ({ page }) => {
  const submissions: Array<Record<string, unknown>> = [];
  await installApi(page, submissions);
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await page.getByLabel("Batch select SITE 2").uncheck();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await expect(page.getByLabel("Batch select SITE 1")).toBeChecked();
  await expect(page.getByLabel("Batch select SITE 2")).not.toBeChecked();

  await page.getByLabel("Engineering batch erase").check();
  await expect(page.getByRole("button", { name: "START PROGRAMMING" })).toBeEnabled();
  await page.getByRole("button", { name: "START PROGRAMMING" }).click();

  await expect.poll(() => submissions.length).toBe(1);
  expect(submissions.map(item => item.site_id)).toEqual([1]);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await expect(page.getByLabel("Batch select SITE 2")).not.toBeChecked();
});
