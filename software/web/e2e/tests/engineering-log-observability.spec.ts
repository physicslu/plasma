import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppuId = "mock-facility-01-ppu-01";

type BatchState = "running" | "success" | "cancelled";
type BatchBody = Record<string, unknown>;

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 1,
    site_count: 2,
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
      capabilities: {
        max_supported_sites: 2,
        operations: ["erase", "program", "verify", "read"],
      },
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

function batchPayload(body: BatchBody, state: BatchState, cancelRequested = false) {
  const operations = (body.operations as string[] | undefined) ?? ["erase"];
  const executionPolicy = (body.execution_policy as {
    repeat_count: number;
    site_retry_limit: number;
    failed_site_stop_threshold: number | null;
  } | undefined) ?? {
    repeat_count: 1,
    site_retry_limit: 3,
    failed_site_stop_threshold: null,
  };
  const targets = (body.targets as Array<{ facility_id: string; ppu_id: string; site_ids: number[] }> | undefined)
    ?? [{ facility_id: facilityId, ppu_id: ppuId, site_ids: [1, 2] }];
  const terminal = state !== "running";
  const siteState = state === "success" ? "success" : state === "cancelled" ? "cancelled" : "running";
  const sites = targets.flatMap(target => target.site_ids.map(siteId => ({
    facility_id: target.facility_id,
    ppu_id: target.ppu_id,
    site_id: siteId,
    key: `${target.facility_id}/${target.ppu_id}/${siteId}`,
    state: siteState,
    current_round: 1,
    completed_rounds: state === "success" ? executionPolicy.repeat_count : 0,
    current_operation: terminal ? null : operations[0],
    current_job_id: terminal ? null : `server-batch-job-${siteId}`,
    progress_percent: terminal ? 100 : 35,
    total_attempts: terminal ? executionPolicy.repeat_count * operations.length : 1,
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
  const assetRequest = body.asset as {
    asset_name?: string;
    asset_type?: string;
    asset_format?: string;
    asset_size?: number;
    asset_sha256?: string;
  } | undefined;
  return {
    ok: true,
    rest_contract_version: "3",
    batch: {
      batch_id: "engineering-log-batch",
      state,
      created_at: "2026-08-26T08:00:00Z",
      started_at: "2026-08-26T08:00:00Z",
      finished_at: terminal ? "2026-08-26T08:00:01Z" : null,
      operations,
      execution_policy: executionPolicy,
      target_device: body.target_device ?? null,
      asset: assetRequest ? {
        name: assetRequest.asset_name ?? "image.bin",
        asset_type: assetRequest.asset_type ?? "image",
        asset_format: assetRequest.asset_format ?? "binary",
        size_bytes: assetRequest.asset_size ?? 0,
        sha256: assetRequest.asset_sha256 ?? "",
      } : null,
      read: body.read ?? { offset: 0, length: 256 },
      cancel_requested: cancelRequested,
      stop_reason: cancelRequested ? "operator_cancel" : null,
      error: null,
      faulted_site_count: 0,
      site_counts: {
        ready: 0,
        running: state === "running" ? sites.length : 0,
        success: state === "success" ? sites.length : 0,
        faulted: 0,
        error: 0,
        stopped: 0,
        cancelled: state === "cancelled" ? sites.length : 0,
      },
      operation_statistics: {},
      sites,
    },
  };
}

async function openProgramming(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
}

async function installApi(page: Page, autoComplete: boolean) {
  let sessionNumber = 0;
  let currentBody: BatchBody = {};
  let batchState: BatchState = autoComplete ? "success" : "running";
  let batchSubmissions = 0;
  let batchCancels = 0;
  let legacyAssetCalls = 0;
  let directJobCalls = 0;

  await page.route("**/api/batches**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/batches" && request.method() === "POST") {
      currentBody = request.postDataJSON() as BatchBody;
      batchSubmissions += 1;
      batchState = autoComplete ? "success" : "running";
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify(batchPayload(currentBody, batchState)),
      });
      return;
    }
    if (path === "/api/batches/engineering-log-batch" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(batchPayload(currentBody, batchState, batchState === "cancelled")) });
      return;
    }
    if (path === "/api/batches/engineering-log-batch/cancel" && request.method() === "POST") {
      batchCancels += 1;
      batchState = "cancelled";
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(batchPayload(currentBody, "cancelled", true)) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: `unhandled ${path}` } }) });
  });

  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      sessionNumber += 1;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: String(sessionNumber).padStart(32, "0"),
            programming_asset_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: sessionNumber > 1,
          },
        }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }
    const parts = url.pathname.split("/").filter(Boolean);
    const tail = parts.slice(5).join("/");
    if (request.method() === "GET" && tail === "api/status" && !url.searchParams.has("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(status()) });
      return;
    }
    if (tail.startsWith("api/programming-assets")) {
      legacyAssetCalls += 1;
    }
    if (request.method() === "POST" && tail === "api/jobs") {
      directJobCalls += 1;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: `unhandled ${tail}` } }) });
  });

  return {
    get batchSubmissions() { return batchSubmissions; },
    get batchCancels() { return batchCancels; },
    get legacyAssetCalls() { return legacyAssetCalls; },
    get directJobCalls() { return directJobCalls; },
    get body() { return currentBody; },
  };
}

test("Engineering log records server Batch Programming Image submission without reviving the legacy Asset cache", async ({ page }) => {
  const api = await installApi(page, true);
  await openProgramming(page);
  const log = page.getByLabel("Engineering job log");

  await page.getByLabel("Engineering Programming Image Asset file").setInputFiles({
    name: "observable.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(1024 * 1024, 0x5a),
  });
  await page.getByLabel("Engineering batch program").check();
  await page.locator(".executeBatch").click();

  await expect.poll(() => api.batchSubmissions).toBe(1);
  expect(api.directJobCalls).toBe(0);
  expect(api.legacyAssetCalls).toBe(0);
  const asset = api.body.asset as Record<string, unknown>;
  expect(asset.asset_name).toBe("observable.bin");
  expect(asset.asset_size).toBe(1024 * 1024);
  expect(typeof asset.asset_sha256).toBe("string");
  expect(typeof asset.asset_base64).toBe("string");

  await expect(log).toContainText("[USR] [IMG] SELECT · observable.bin · 1.00 MiB");
  await expect(log).toContainText("[USR] [BATCH] SUBMIT · PROGRAM");
  await expect(log).toContainText("[BAT] [BATCH] ACCEPTED · engineering-log-batch");
  await expect(log).toContainText("[BAT] [BATCH] SUCCESS · engineering-log-batch");
  await expect(log).not.toContainText("CACHE CHECK");
  await expect(log).not.toContainText("CACHE HIT");
});

test("server-owned Engineering Batch exposes whole-Batch ABORT and disables per-Site cancellation", async ({ page }) => {
  const api = await installApi(page, false);
  await openProgramming(page);
  await page.getByLabel("Engineering batch erase").check();
  await page.locator(".executeBatch").click();

  await expect.poll(() => api.batchSubmissions).toBe(1);
  await expect(page.getByRole("button", { name: "ABORT" })).toBeEnabled();
  await expect(page.getByLabel("Cancel SITE 1")).toBeDisabled();
  await expect(page.getByLabel("Cancel SITE 2")).toBeDisabled();
  expect(api.directJobCalls).toBe(0);

  await page.getByRole("button", { name: "ABORT" }).click();
  await expect.poll(() => api.batchCancels).toBe(1);
  const log = page.getByLabel("Engineering job log");
  await expect(log).toContainText("[USR] [BATCH] ABORT REQUESTED · engineering-log-batch");
  await expect(log).toContainText("[BAT] [BATCH] CANCELLED · engineering-log-batch");
  await expect(page.locator(".executeBatch")).toBeEnabled();
});
