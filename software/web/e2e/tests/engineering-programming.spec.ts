import { expect, test, type Page, type Route } from "@playwright/test";

const siteCounts = [2, 4, 6, 8] as const;

type BatchTarget = { facility_id: string; ppu_id: string; site_ids: number[] };
type BatchPolicy = { repeat_count: number; site_retry_limit: number; failed_site_stop_threshold: number | null };

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 8,
    ppu_count: 32,
    site_count: 160,
    programming_asset_scope: "connection-session-and-ppu",
    facilities: Array.from({ length: 8 }, (_, facilityIndex) => {
      const facilityNumber = facilityIndex + 1;
      const facilityId = `mock-facility-${String(facilityNumber).padStart(2, "0")}`;
      return {
        facility_id: facilityId,
        display_name: `Server Facility ${String(facilityNumber).padStart(2, "0")}`,
        ppus: siteCounts.map((siteCount, ppuIndex) => ({
          ppu_id: `${facilityId}-ppu-${String(ppuIndex + 1).padStart(2, "0")}`,
          display_name: `Server PPU ${String(ppuIndex + 1).padStart(2, "0")}`,
          model: "MOCK-PPU",
          site_count: siteCount,
          provider: "mock",
        })),
      };
    }),
  };
}

function statusFor(facilityId: string, ppuId: string) {
  const ppuNumber = Number(ppuId.slice(-2));
  const siteCount = siteCounts[ppuNumber - 1];
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: `Server PPU ${String(ppuNumber).padStart(2, "0")}`,
      site_count: siteCount,
      enabled_site_count: siteCount,
      capabilities: { max_supported_sites: siteCount, operations: ["erase", "program", "verify", "read"] },
    },
    sites: Array.from({ length: siteCount }, (_, index) => ({
      site_id: index + 1,
      enabled: true,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: "mock",
      target: "MOCK-IC",
    })),
  };
}

function terminalJob(jobId: string, siteId: number, operation: string) {
  return {
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
  };
}

function completedBatch(body: Record<string, unknown>, index: number) {
  const targets = body.targets as BatchTarget[];
  const operations = body.operations as string[];
  const policy = body.execution_policy as BatchPolicy;
  const assetRequest = body.asset as {
    asset_name?: string;
    asset_type?: string;
    asset_format?: string;
    asset_size?: number;
    asset_sha256?: string;
  } | undefined;
  const sites = targets.flatMap(target => target.site_ids.map(siteId => ({
    facility_id: target.facility_id,
    ppu_id: target.ppu_id,
    site_id: siteId,
    key: `${target.facility_id}/${target.ppu_id}/${siteId}`,
    state: "success",
    current_round: policy.repeat_count,
    completed_rounds: policy.repeat_count,
    current_operation: null,
    current_job_id: null,
    progress_percent: 100,
    total_attempts: policy.repeat_count * operations.length,
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
    batch_id: `engineering-programming-batch-${index}`,
    state: "success",
    created_at: "2026-08-26T08:00:00Z",
    started_at: "2026-08-26T08:00:00Z",
    finished_at: "2026-08-26T08:00:01Z",
    operations,
    execution_policy: policy,
    target_device: body.target_device ?? null,
    asset: assetRequest ? {
      name: assetRequest.asset_name ?? "image.bin",
      asset_type: assetRequest.asset_type ?? "image",
      asset_format: assetRequest.asset_format ?? "binary",
      size_bytes: assetRequest.asset_size ?? 0,
      sha256: assetRequest.asset_sha256 ?? "",
    } : null,
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
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
}

async function installBaseEngineeringApi(page: Page) {
  let sessionRequests = 0;
  let catalogRequests = 0;
  let statusRequests = 0;
  let legacyAssetCalls = 0;
  const previousSessionIds: Array<string | undefined> = [];
  const directSubmissions: Array<{ url: string; body: Record<string, unknown> }> = [];
  const batchBodies: Array<Record<string, unknown>> = [];
  const batches = new Map<string, ReturnType<typeof completedBatch>>();

  await page.route("**/api/batches**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/batches" && request.method() === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      batchBodies.push(body);
      const snapshot = completedBatch(body, batchBodies.length);
      batches.set(snapshot.batch_id, snapshot);
      await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: snapshot }) });
      return;
    }
    const match = /^\/api\/batches\/(engineering-programming-batch-\d+)$/.exec(url.pathname);
    if (request.method() === "GET" && match && batches.has(match[1])) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, rest_contract_version: "3", batch: batches.get(match[1]) }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: `unhandled ${url.pathname}` } }) });
  });

  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      sessionRequests += 1;
      const body = request.postDataJSON() as { previous_session_id?: string };
      previousSessionIds.push(body.previous_session_id);
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: String(sessionRequests).padStart(32, "0"),
            programming_asset_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: Boolean(body.previous_session_id),
          },
        }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets") {
      catalogRequests += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }

    const parts = url.pathname.split("/").filter(Boolean);
    const facilityId = parts[3];
    const ppuId = parts[4];
    const tail = parts.slice(5).join("/");
    if (request.method() === "GET" && tail === "api/status" && !url.searchParams.has("job")) {
      statusRequests += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(statusFor(facilityId, ppuId)) });
      return;
    }
    if (request.method() === "GET" && tail === "api/status" && url.searchParams.has("job")) {
      const jobId = url.searchParams.get("job")!;
      const direct = directSubmissions.find(item => item.body.job_id === jobId);
      const siteId = direct ? Number(direct.body.site_id) : Number(jobId.split("-").at(-1));
      const operation = direct ? String(direct.body.operation) : "erase";
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(terminalJob(jobId, siteId, operation)) });
      return;
    }
    if (request.method() === "POST" && tail === "api/jobs") {
      const body = request.postDataJSON() as Record<string, unknown>;
      const jobId = `engineering-e2e-${String(body.operation)}-${Number(body.site_id)}`;
      body.job_id = jobId;
      directSubmissions.push({ url: url.pathname, body });
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job: {
            job_id: jobId,
            site_id: body.site_id,
            operation: body.operation,
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
    if (tail.startsWith("api/programming-assets")) legacyAssetCalls += 1;
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: `unhandled Engineering route ${tail}` } }) });
  });

  return {
    get sessionRequests() { return sessionRequests; },
    get catalogRequests() { return catalogRequests; },
    get statusRequests() { return statusRequests; },
    get legacyAssetCalls() { return legacyAssetCalls; },
    previousSessionIds,
    directSubmissions,
    batchBodies,
  };
}

test("Engineering Programming topology comes from the Python target catalog", async ({ page }) => {
  await installBaseEngineeringApi(page);
  await openProgramming(page);
  await expect(page.locator(".topologyFoot")).toContainText("System Topology: 8 Facilities | 32 PPUs | 160 Sites");

  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  await expect(facility.locator("option")).toHaveCount(8);
  await expect(ppu.locator("option")).toHaveCount(4);
  await expect(facility.locator("option").first()).toHaveText("Server Facility 01");

  await ppu.selectOption("mock-facility-01-ppu-03");
  await expect(page.getByLabel("Selected Engineering PPU", { exact: true })).toContainText("Server Facility 01 / Server PPU 03");
  await expect(page.getByLabel("Selected Engineering PPU", { exact: true })).toContainText("6 Sites");
  await expect(page.locator(".targetSitesSection").getByRole("checkbox")).toHaveCount(6);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(6);

  await facility.selectOption("mock-facility-03");
  await expect(ppu).toHaveValue("mock-facility-03-ppu-01");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await ppu.selectOption("mock-facility-03-ppu-04");
  await expect(page.getByLabel("Selected Engineering PPU", { exact: true })).toContainText("Server Facility 03 / Server PPU 04");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(8);
});

test("same-URL Connect creates a new session and restores Facility PPU Site topology", async ({ page }) => {
  const api = await installBaseEngineeringApi(page);
  await openProgramming(page);
  await expect(page.getByLabel("Engineering Facility", { exact: true }).locator("option")).toHaveCount(8);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  const sessionsBefore = api.sessionRequests;
  const catalogsBefore = api.catalogRequests;
  const statusesBefore = api.statusRequests;
  await page.locator(".engineeringGateway button[type=submit]").click();

  await expect.poll(() => api.sessionRequests).toBeGreaterThan(sessionsBefore);
  await expect.poll(() => api.catalogRequests).toBeGreaterThan(catalogsBefore);
  await expect.poll(() => api.statusRequests).toBeGreaterThan(statusesBefore);
  await expect(page.getByLabel("Engineering PPU", { exact: true }).locator("option")).toHaveCount(4);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  expect(api.previousSessionIds.at(-1)).toBe(String(sessionsBefore).padStart(32, "0"));
});

test("Engineering EPVR job is posted to the selected Facility and PPU", async ({ page }) => {
  const api = await installBaseEngineeringApi(page);
  await openProgramming(page);
  await page.getByLabel("Engineering Facility", { exact: true }).selectOption("mock-facility-02");
  await page.getByLabel("Engineering PPU", { exact: true }).selectOption("mock-facility-02-ppu-03");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(6);

  await page.getByLabel("SITE 6 擦除").click();
  await expect.poll(() => api.directSubmissions.length).toBe(1);
  expect(api.directSubmissions[0].url).toBe("/api/engineering/targets/mock-facility-02/mock-facility-02-ppu-03/api/jobs");
  expect(api.directSubmissions[0].body.site_id).toBe(6);
  expect(api.directSubmissions[0].body.operation).toBe("erase");
  await expect(page.getByLabel("Engineering job log")).toContainText("SITE-06");
});

test("Server Batch Programming Image is self-contained per Batch and reconnect advances Engineering session provenance", async ({ page }) => {
  const api = await installBaseEngineeringApi(page);
  await openProgramming(page);
  await page.getByLabel("Engineering Programming Image Asset file").setInputFiles({
    name: "A.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(1024 * 1024, 0x5a),
  });
  await page.getByLabel("Engineering batch program").check();

  await page.locator(".executeBatch").click();
  await expect.poll(() => api.batchBodies.length).toBe(1);
  await expect.poll(() => page.locator(".executeBatch").isEnabled()).toBe(true);
  expect(api.directSubmissions).toHaveLength(0);
  expect(api.legacyAssetCalls).toBe(0);
  const first = api.batchBodies[0];
  const firstAsset = first.asset as Record<string, unknown>;
  expect(first.session_id).toBe("00000000000000000000000000000001");
  expect(firstAsset.asset_name).toBe("A.bin");
  expect(firstAsset.asset_size).toBe(1024 * 1024);
  expect(typeof firstAsset.asset_sha256).toBe("string");
  expect(typeof firstAsset.asset_base64).toBe("string");

  await page.locator(".executeBatch").click();
  await expect.poll(() => api.batchBodies.length).toBe(2);
  await expect.poll(() => page.locator(".executeBatch").isEnabled()).toBe(true);
  const secondAsset = api.batchBodies[1].asset as Record<string, unknown>;
  expect(secondAsset.asset_sha256).toBe(firstAsset.asset_sha256);
  expect(typeof secondAsset.asset_base64).toBe("string");

  await page.getByLabel("Engineering Programming Image Asset file").setInputFiles({
    name: "B.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(1024 * 1024, 0xa5),
  });
  await page.locator(".executeBatch").click();
  await expect.poll(() => api.batchBodies.length).toBe(3);
  await expect.poll(() => page.locator(".executeBatch").isEnabled()).toBe(true);
  const thirdAsset = api.batchBodies[2].asset as Record<string, unknown>;
  expect(thirdAsset.asset_sha256).not.toBe(firstAsset.asset_sha256);

  const sessionsBeforeReconnect = api.sessionRequests;
  await page.locator(".engineeringGateway button[type=submit]").click();
  await expect.poll(() => api.sessionRequests).toBeGreaterThan(sessionsBeforeReconnect);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  await page.locator(".executeBatch").click();
  await expect.poll(() => api.batchBodies.length).toBe(4);
  expect(api.batchBodies[3].session_id).toBe("00000000000000000000000000000002");
  expect(api.legacyAssetCalls).toBe(0);
});
