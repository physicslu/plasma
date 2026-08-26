import { readFile } from "node:fs/promises";
import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppu1 = "mock-facility-01-ppu-01";
const ppu2 = "mock-facility-01-ppu-02";

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 2,
    site_count: 4,
    programming_asset_scope: "connection-session-and-ppu",
    facilities: [{
      facility_id: facilityId,
      display_name: "Mock Facility 01",
      ppus: [ppu1, ppu2].map((ppuId, index) => ({
        ppu_id: ppuId,
        display_name: `Mock PPU 0${index + 1}`,
        model: "MOCK-PPU",
        site_count: 2,
        provider: "mock",
      })),
    }],
  };
}

function status(ppuId: string) {
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: ppuId === ppu1 ? "Mock PPU 01" : "Mock PPU 02",
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

function completedBatch(body: Record<string, unknown>) {
  const targets = body.targets as Array<{ facility_id: string; ppu_id: string; site_ids: number[] }>;
  const operations = body.operations as string[];
  const executionPolicy = body.execution_policy as {
    repeat_count: number;
    site_retry_limit: number;
    failed_site_stop_threshold: number | null;
  };
  const sites = targets.flatMap(target => target.site_ids.map(siteId => ({
    facility_id: target.facility_id,
    ppu_id: target.ppu_id,
    site_id: siteId,
    key: `${target.facility_id}/${target.ppu_id}/${siteId}`,
    state: "success",
    current_round: executionPolicy.repeat_count,
    completed_rounds: executionPolicy.repeat_count,
    current_operation: null,
    current_job_id: null,
    progress_percent: 100,
    total_attempts: executionPolicy.repeat_count * operations.length,
    retry_count: 0,
    final_failures: 0,
    faulted_round: null,
    faulted_operation: null,
    last_failure_source: null,
    communication_state: "connected",
    communication_attempt: 0,
    error: null,
    operation_statistics: {},
  })));
  return {
    batch_id: "operator-audit-batch",
    state: "success",
    created_at: "2026-08-26T08:00:00Z",
    started_at: "2026-08-26T08:00:00Z",
    finished_at: "2026-08-26T08:00:01Z",
    operations,
    execution_policy: executionPolicy,
    target_device: body.target_device ?? null,
    asset: null,
    read: body.read ?? { offset: 0, length: 256 },
    cancel_requested: false,
    stop_reason: null,
    error: null,
    faulted_site_count: 0,
    site_counts: {
      ready: 0,
      running: 0,
      success: sites.length,
      faulted: 0,
      error: 0,
      stopped: 0,
      cancelled: 0,
    },
    operation_statistics: {},
    sites,
  };
}

async function openProgramming(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
}

async function fulfillJson(route: Route, statusCode: number, body: unknown) {
  await route.fulfill({ status: statusCode, contentType: "application/json", body: JSON.stringify(body) });
}

test("Engineering audit log reconstructs operator actions and filters without truncating downloaded evidence", async ({ page }) => {
  let sessionNumber = 0;
  let batchNumber = 0;
  let directJobNumber = 0;

  await page.route("**/api/batches**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/batches" && request.method() === "POST") {
      batchNumber += 1;
      const body = request.postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, 202, { ok: true, rest_contract_version: "3", batch: completedBatch(body) });
      return;
    }
    await fulfillJson(route, 404, { error: { message: `unhandled ${url.pathname}` } });
  });

  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      sessionNumber += 1;
      await fulfillJson(route, 201, {
        ok: true,
        session: {
          session_id: String(sessionNumber).padStart(32, "0"),
          programming_asset_cache_scope: "connection-session-and-ppu",
          previous_session_cleared: sessionNumber > 1,
        },
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets") {
      await fulfillJson(route, 200, catalog());
      return;
    }

    const parts = url.pathname.split("/").filter(Boolean);
    const currentPpu = parts[4];
    const tail = parts.slice(5).join("/");
    if (request.method() === "GET" && tail === "api/status" && !url.searchParams.has("job")) {
      await fulfillJson(route, 200, status(currentPpu));
      return;
    }
    if (request.method() === "POST" && tail === "api/jobs") {
      directJobNumber += 1;
    }
    await fulfillJson(route, 404, { error: { message: `unhandled ${tail}` } });
  });

  await openProgramming(page);
  const log = page.getByLabel("Engineering job log");
  await expect(log).toContainText("[NET] [SESSION] NEW · fresh connection");
  await expect(page.getByLabel("Batch select SITE 1")).toBeChecked();
  await expect(page.getByLabel("Batch select SITE 2")).toBeChecked();

  await page.getByLabel("Engineering PPU", { exact: true }).selectOption(ppu2);
  await expect(log).toContainText(`[USR] [TARGET] SELECT · ${facilityId} / ${ppu2}`);
  await expect(log).toContainText(`[SYS] [TARGET] ${facilityId} / ${ppu2}`);

  await page.getByLabel("Batch select SITE 2").uncheck();
  await expect(log).toContainText("[USR] [SITE] SELECTION · SITE-01");

  await page.getByLabel("Engineering Programming Image Asset file").setInputFiles({
    name: "operator-audit.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(1024, 0x5a),
  });
  await expect(log).toContainText("[USR] [IMG] SELECT · operator-audit.bin · 1.0 KiB");

  await page.getByLabel("Engineering batch erase").check();
  await expect(log).toContainText("[USR] [BATCH] OPERATIONS · ERASE");
  await page.locator(".executeBatch").click();

  await expect.poll(() => batchNumber).toBe(1);
  expect(directJobNumber).toBe(0);
  await expect(page.locator(".executeBatch")).toBeEnabled();
  await expect(log).toContainText("[USR] [BATCH] SUBMIT · ERASE · SITE-01");
  await expect(log).toContainText("[BAT] [BATCH] ACCEPTED · operator-audit-batch");
  await expect(log).toContainText("[BAT] [BATCH] SUCCESS · operator-audit-batch");

  await expect(page.getByText("DAT", { exact: true })).toBeVisible();
  const logHeight = await log.evaluate(element => Number.parseFloat(getComputedStyle(element).height));
  expect(logHeight).toBeGreaterThanOrEqual(260);

  await page.getByLabel("Engineering log filter NET").uncheck();
  await page.getByLabel("Engineering log filter PPU").uncheck();
  await page.getByLabel("Engineering log filter DAT").uncheck();
  await page.getByLabel("Engineering log filter BAT").uncheck();
  await page.getByLabel("Engineering log filter SYS").uncheck();

  const visibleEntries = log.locator("span");
  await expect(visibleEntries.first()).toHaveAttribute("data-category", "USR");
  expect(await visibleEntries.count()).toBeGreaterThan(0);
  for (const category of await visibleEntries.evaluateAll(elements => elements.map(element => element.getAttribute("data-category")))) {
    expect(category).toBe("USR");
  }
  await expect(log).not.toContainText("[BAT] [BATCH] SUCCESS");
  await expect(log).not.toContainText("[NET] [SESSION] NEW");

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download .log", exact: true }).click();
  const download = await downloadPromise;
  const path = await download.path();
  expect(path).not.toBeNull();
  const fileText = await readFile(path!, "utf8");
  expect(fileText).toContain("[USR] [IMG] SELECT · operator-audit.bin · 1.0 KiB");
  expect(fileText).toContain("[USR] [BATCH] SUBMIT · ERASE · SITE-01");
  expect(fileText).toContain("[BAT] [BATCH] ACCEPTED · operator-audit-batch");
  expect(fileText).toContain("[BAT] [BATCH] SUCCESS · operator-audit-batch");
  expect(fileText).toContain("[NET] [SESSION] NEW · fresh connection");
});
