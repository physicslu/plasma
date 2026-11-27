import { expect, test, type Page, type Route } from "@playwright/test";

// Host-only Console UI acceptance for Console-driven Bundle programming.
// U2: the panel submits one Manager Batch (one Site, one Cycle, no retry) for
// programming and for Read Memory; the single plan + run is retired.
// The Manager BFF is mocked at the Browser boundary (Mock PPU / Fake Provider).
// This proves Console behaviour only; it is NOT physical E2E evidence.

const ALIAS = "z2";
const FIRMWARE = Buffer.from(Array.from({ length: 4096 }, (_, i) => i % 251));
const IMAGE_SHA = "f".repeat(64);
const RUN_ID = "d".repeat(32);
const RESOURCE_SHA = "9".repeat(64);
const BINDING_SHA = "8".repeat(64);
const ACTIVE_SET_SHA = "b".repeat(64);

const registry = {
  ok: true, service: "plasma-manager", contract_version: "1", mutable: true, storage: "file",
  ppus: [{ alias: ALIAS, endpoint: "http://192.168.2.99:18080", lifecycle: "commissioned",
    registered_at: "2026-11-09T00:00:00+00:00", updated_at: "2026-11-09T00:00:00+00:00" }],
};

const bootstrapStatus = {
  ok: true, ppu_alias: ALIAS, bootstrap_endpoint_policy: "z2-ps-same-host:18081",
  pairing: { paired: true, device_id: "ppu-device-0123456789abcdef", device_match: true,
    credential_persistence: "file", updated_at: "2026-11-09T00:00:00+00:00" },
  bootstrap: {
    schema_version: 1, bootstrap: { api_version: "1", version: "0.1.0", state: "bootstrap_ready" },
    identity: { device_id: "ppu-device-0123456789abcdef", ppu_id: "z2-hil", facility_id: "lab", hardware_revision: null },
    runtime: { state: "runtime_active", release_id: "0.2.1-a1b1c6f3b142", product_version: "0.2.1",
      git_sha: "a1b1c6f3b1424ce38d1de7e597ef22d0ef4460f2", target: "linux-armv7l", reason: null },
    fpga: { pl_version: null, pl_compatibility: "not_managed", pl_qualification: "not_qualified" },
    capabilities: { runtime_deployment: true, identity_update: false, fpga_update: false },
    deployment: null,
  },
};

const route = {
  route_id: "z2-site2-stm32f103c8t6-operations", target: { platform: "linux-armv7", board: "pynq-z2", fpga_part: "xc7z020clg400-1" },
  icpn: "STM32F103C8T6", site_interface: "openocd", provider: "openocd-platform-reference", profile: "stm32f103c8t6-site2",
  operations: ["erase", "program", "verify"], driver_abi: "plasma_swd:5", transport: "fpga", max_image_bytes: 65536,
  target_config: "target/stm32f1x.cfg", flash_base: 134217728, flash_size: 65536,
};

const device = {
  vendor: "STMicroelectronics", family: "STM32F1", subfamily: null, plasma_series: "STM32F1",
  identifier: "STM32F103C8T6", identifier_kind: "manufacturer_part_number", icpn: "STM32F103C8T6",
  identity: { state: "IDENTIFIED" }, package: "LQFP48", pin_count: "48", flash_size: "64K",
  temperature_grade: null, option_suffix: null, base_device: "STM32F103C8", cpu_architectures: ["cortex-m3"],
  backend: { type: "openocd", distribution: "upstream", target_config: "target/stm32f1x.cfg", mapping_status: "mapped", mapping_method: null },
  catalog_verification: { status: null, source_type: null, source_authority: null, source_reference: null },
  physical_validation: { engineering_status: "no_evidence", ppu_status: "no_evidence", socket_status: "no_evidence" },
  catalog: { scope: "production_admitted", version: null, revision_sha256: null }, catalog_origin: "test",
  catalog_level: 1, catalog_level_state: "PROGRAMMING_CANDIDATE", job_selectable: false,
};

type Outcome = "PASS" | "FAIL" | "OUTCOME_UNKNOWN";

// A Resource Reuse run never activates: no B1/B2/B3 step and an empty
// activation record, exactly as the Manager journals it.
function run(outcome: Outcome | null, reason: string | null = null, safeOff = true, reuse = true) {
  // U2: a run is a Batch attempt; it never activates (the Batch did that before it).
  const steps = [
    { step: "PREFLIGHT", result: "PASS", at: "t" },
    { step: "RESOURCE_REUSE", result: "PPU_VERIFIED", at: "t", asset_set_sha256: ACTIVE_SET_SHA,
      resource_set_sha256: RESOURCE_SHA, generation: 3 },
    { step: "PROGRAMMING_SUBMIT", result: "ACCEPTED", at: "t" },
  ];
  return {
    schema: "plasma.manager.bundle-programming-run.v1", run_id: RUN_ID, ppu_alias: ALIAS, site_id: 2,
    plan: {}, state: outcome ? "finished" : "running", outcome, reason, created_at: "t", updated_at: "t",
    steps: outcome === "PASS" ? [...steps, { step: "VERIFY_RECEIPT", result: "PASS", at: "t" }] : steps,
    activation: {},
    job: { job_id: "job-20261109-120000-0123abcd", state: outcome ? "success" : "running", progress_percent: outcome ? 100 : 40 },
    receipt: outcome && outcome !== "OUTCOME_UNKNOWN" ? {
      schema: "plasma.manager.programming-receipt.v3",
      job_id: "job-20261109-120000-0123abcd", job_state: "success", operation: "programming", operations: ["erase", "program", "verify"],
      observed_operations: ["erase", "program", "verify"],
      site_id: 2, target: route.icpn, readback_sha256: IMAGE_SHA,
      expected_image_sha256: IMAGE_SHA, expected_image_size: FIRMWARE.length,
      observed_image_sha256: IMAGE_SHA, observed_image_size: FIRMWARE.length,
      bytes_verified: FIRMWARE.length,
      expected_resource_set_sha256: RESOURCE_SHA, observed_resource_set_sha256: RESOURCE_SHA,
      expected_job_binding_sha256: BINDING_SHA, observed_job_binding_sha256: BINDING_SHA,
      active_asset_set_sha256: ACTIVE_SET_SHA, resource_reuse: reuse,
      safe_off: safeOff, flash_result: "PASS", elapsed_ms: 10000,
    } : null,
    job_submission_count: 1, auto_retry: "DISABLED", acknowledged: false,
  };
}

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });

const START_ID = "5".repeat(32);
const BATCH_ID = "4".repeat(32);

type Mocks = {
  routes?: unknown[]; batchStatus?: number; batchBody?: unknown; final?: ReturnType<typeof run>;
  pollStatus?: number;
};

async function mockManager(page: Page, mocks: Mocks = {}) {
  const counters = { issued: 0, batches: 0, polls: 0, acks: 0,
    batchBodies: [] as Array<Record<string, unknown>>, legacy: [] as string[] };
  await page.route(/\/api\/manager\/registry$/, r => r.fulfill(json(registry)));
  // The actual UI discovers Site existence from Manager Fleet, not Route.sites.
  // Only Site 2 is physically enabled in this host-only fixture.
  await page.route(/\/api\/fleet$/, r => r.fulfill(json({
    ok: true, contract_version: "1", observed_at: "2026-11-14T00:00:00Z",
    ppus: [{
      alias: ALIAS, transport_state: "reachable", execution_state: "ready",
      observation: { state: "current", last_success_at: "2026-11-14T00:00:00Z", stale_age_s: 0 },
      identity: { ppu_id: "z2-hil", facility_id: "lab", model: "PYNQ-Z2", display_name: "z2-hil" },
      topology: { source: "current", site_count: 2, enabled_site_count: 1, sites: [
        { site_id: 1, enabled: false, state: "disabled", current_job_id: null, interface: null },
        { site_id: 2, enabled: true, state: "idle", current_job_id: null, interface: "openocd" },
      ] },
      identity_conflict: false, degraded: false,
    }],
  })));
  await page.route(/\/api\/manager\/registry\/z2\/bootstrap$/, r => r.fulfill(json(bootstrapStatus)));
  await page.route(/\/api\/manager\/devices\/search\?/, r => r.fulfill(json({
    ok: true, scope: "customer_ic_selector", query: "STM32", levels: [1, 2, 3], catalog_size: 1,
    count: 1, total_count: 1, limit: 8, offset: 0, results: [device] })));
  await page.route(/\/bootstrap\/programming\/routes$/, r => r.fulfill(json({ ok: true, routes: mocks.routes ?? [route] })));
  // The retired single plan + run must never be called.
  await page.route(/\/bootstrap\/programming\/(plans|runs)$/, async (r: Route) => {
    counters.legacy.push(r.request().url());
    await r.fulfill(json({ ok: false, error: { code: "programming_route_retired", message: "retired" } }, 410));
  });
  await page.route(/\/api\/manager\/programming\/starts(\?|$)/, async (r: Route) => {
    counters.issued += 1;
    await r.fulfill(json({ ok: true, start: { start_id: START_ID, kind: "batch", ppu_alias: null } }, 201));
  });
  let body: Record<string, unknown> = {};
  const batch = (current: ReturnType<typeof run> | null, outcome: string | null) => ({
    schema: "plasma.manager.programming-batch.v1", batch_id: BATCH_ID, start_id: START_ID,
    targets: body.targets, icpn: body.icpn, operations: body.operations ?? null,
    operation: body.operation ?? null, source: "image_base64" in body ? "image" : "range",
    policy: { repeat: 1, retry_limit: 0, replace_ic_before_next_cycle: true, stop_policy: { kind: "never" } },
    state: outcome ? "finished" : "running", execution_status: outcome ? "COMPLETED" : "RUNNING",
    outcome, reason: current?.reason ?? null, failure_domain: null, stop_requested: false,
    units: [{ ppu_alias: ALIAS, site_id: 2, status: outcome ? "FINISHED" : "RUNNING", outcome,
      reason: current?.reason ?? null, failure_domain: null, attempts: [] }],
    attempts: [], current_run: current,
    counts: { pass: outcome === "PASS" ? 1 : 0, fail: outcome === "FAIL" ? 1 : 0, blocked: 0,
      unknown: outcome === "OUTCOME_UNKNOWN" ? 1 : 0, sites: 1, attempts: 1 },
    auto_retry: "DISABLED",
  });
  await page.route(/\/api\/manager\/programming\/batches$/, async (r: Route) => {
    counters.batches += 1;
    body = r.request().postDataJSON();
    counters.batchBodies.push(body);
    if (mocks.batchStatus) return r.fulfill(json(mocks.batchBody, mocks.batchStatus));
    await r.fulfill(json({ ok: true, batch: batch(run(null), null) }, 202));
  });
  await page.route(new RegExp(`/api/manager/programming/batches/${BATCH_ID}$`), async (r: Route) => {
    counters.polls += 1;
    if (mocks.pollStatus) {
      return r.fulfill(json({ ok: false, error: { code: "manager_unavailable", message: "Manager programming path is unavailable" } }, mocks.pollStatus));
    }
    const final = mocks.final ?? run("PASS");
    await r.fulfill(json({ ok: true, batch: counters.polls < 2 ? batch(run(null), null) : batch(final, final.outcome) }));
  });
  await page.route(new RegExp(`/bootstrap/programming/runs/${RUN_ID}/acknowledge$`), async (r: Route) => {
    counters.acks += 1;
    await r.fulfill(json({ ok: true, run: { ...(mocks.final ?? run("OUTCOME_UNKNOWN")), acknowledged: true } }));
  });
  return counters;
}

async function openAndSelectIc(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "PPU", exact: true }).click();
  await page.getByRole("button", { name: "Platform", exact: true }).click();
  const panel = page.getByRole("region", { name: "Bundle Programming" });
  await expect(panel).toBeVisible();
  await panel.getByLabel("Target IC").fill("STM32F103");
  await panel.getByRole("option", { name: /STM32F103C8T6/ }).click();
  return panel;
}

async function openAndSelect(page: Page) {
  const panel = await openAndSelectIc(page);
  await panel.getByLabel("Image file").setInputFiles({ name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE });
  await expect(panel.getByLabel("Programming Site")).toHaveValue("2");
  return panel;
}

async function confirmAndStart(panel: ReturnType<Page["getByRole"]>, click: "click" | "dblclick" = "click") {
  const start = panel.getByRole("button", { name: "Start Programming" });
  await expect(start).toBeDisabled(); // explicit confirmation required
  await panel.getByLabel("Confirm programming").check();
  await expect(start).toBeEnabled();
  await start[click]();
}

test("User programs an image as one Manager Batch: one Site, one Cycle, no retry → receipt", async ({ page }) => {
  const counters = await mockManager(page);
  const panel = await openAndSelect(page);
  await expect(panel.getByLabel("Programming Operation")).toHaveValue("programming");
  await confirmAndStart(panel, "dblclick"); // a double click must still start exactly once
  await expect(panel.getByTestId("run-outcome")).toHaveText("PASS");
  await expect(panel.getByTestId("receipt-readback")).toHaveText(IMAGE_SHA);
  await expect(panel.getByTestId("receipt-bytes")).toHaveText(`${FIRMWARE.length} / ${FIRMWARE.length}`);
  await expect(panel.getByTestId("receipt-safe-off")).toHaveText("VERIFIED");
  await expect(panel.getByTestId("receipt-resource")).toHaveText("Reused");
  await expect(panel.getByTestId("receipt-binding-sha")).toHaveText(BINDING_SHA);
  const steps = panel.getByRole("list", { name: "Programming steps" }).getByRole("listitem");
  await expect(steps).toHaveText([
    "PREFLIGHT: PASS", "RESOURCE_REUSE: PPU_VERIFIED", "PROGRAMMING_SUBMIT: ACCEPTED", "VERIFY_RECEIPT: PASS",
  ]);
  await page.waitForTimeout(1500);
  expect(counters.issued).toBe(1);
  expect(counters.batches).toBe(1);
  expect(counters.legacy).toEqual([]);
  const body = counters.batchBodies[0];
  expect(body.start_id).toBe(START_ID);
  expect(body.icpn).toBe("STM32F103C8T6");
  expect(body.targets).toEqual([{ ppu_alias: ALIAS, site_ids: [2] }]);
  expect(body.operations).toEqual(["erase", "program", "verify"]);
  expect(body).not.toHaveProperty("operation");
  expect(body.retry_limit).toBe(0);
  expect(body.repeat).toBe(1);
  expect(body.stop_policy).toEqual({ kind: "never" });
  expect(Buffer.from(String(body.image_base64), "base64").equals(FIRMWARE)).toBe(true);
});

test("Operation choice is limited to the Route Profile; read sends a range Batch, no image", async ({ page }) => {
  const wide = { ...route, operations: ["erase", "program", "verify", "read"] };
  const counters = await mockManager(page, {
    routes: [wide], batchStatus: 409,
    batchBody: { ok: false, error: { code: "resource_activation_requires_image", message: "program an Image first" } },
  });
  const panel = await openAndSelectIc(page);
  const select = panel.getByLabel("Programming Operation");
  // erase / program / verify are steps of one programming Job (EMode), never a Job of their own.
  await expect(select.locator("option")).toHaveText(["programming", "read"]);
  await select.selectOption("read");
  await expect(panel.getByLabel("Image file")).toHaveCount(0);
  await expect(panel.getByLabel("Confirm programming")).toBeDisabled();
  await panel.getByLabel("Range address").fill("0x08000000");
  await panel.getByLabel("Range length").fill("1024");
  await confirmAndStart(panel);
  await expect(panel.getByRole("alert")).toContainText("program an Image first");
  const body = counters.batchBodies[0];
  expect(body).toEqual({ icpn: "STM32F103C8T6", targets: [{ ppu_alias: ALIAS, site_ids: [2] }],
    operation: "read", address: 134217728, length: 1024, retry_limit: 0,
    stop_policy: { kind: "never" }, repeat: 1, replace_ic_before_next_cycle: true, start_id: START_ID });
  expect(counters.batches).toBe(1);
  expect(counters.legacy).toEqual([]);
});

test("A refused Batch and a permission denial are surfaced without retry", async ({ page }) => {
  const counters = await mockManager(page, {
    batchStatus: 422, batchBody: { ok: false, error: { code: "bundle_incompatible", message: "IMAGE_EXCEEDS_PROFILE_MAX_IMAGE" } },
  });
  const panel = await openAndSelect(page);
  await confirmAndStart(panel);
  await expect(panel.getByRole("alert")).toContainText("IMAGE_EXCEEDS_PROFILE_MAX_IMAGE");
  await page.waitForTimeout(1500);
  expect(counters.batches).toBe(1);
  expect(counters.polls).toBe(0);

  await page.unroute(/\/api\/manager\/programming\/batches$/);
  await page.route(/\/api\/manager\/programming\/batches$/, r => r.fulfill(json(
    { ok: false, error: { code: "maintenance_authorization_required", message: "Browser maintenance authorization is required" } }, 403)));
  await confirmAndStart(panel);
  await expect(panel.getByRole("alert")).toContainText("maintenance authorization is required");
});

test("OUTCOME_UNKNOWN is shown, never resubmitted, and needs explicit acknowledgement", async ({ page }) => {
  const counters = await mockManager(page, { final: run("OUTCOME_UNKNOWN", "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT") });
  const panel = await openAndSelect(page);
  await confirmAndStart(panel);
  await expect(panel.getByTestId("run-outcome")).toHaveText("OUTCOME UNKNOWN");
  await expect(panel.getByRole("alert")).toContainText("Nothing was resubmitted");
  await page.waitForTimeout(1500);
  expect(counters.batches).toBe(1);
  await panel.getByRole("button", { name: "Acknowledge reconciliation" }).click();
  await expect.poll(() => counters.acks).toBe(1);
  expect(counters.batches).toBe(1);
});

test("SAFE_OFF failure is a distinct FAIL", async ({ page }) => {
  await mockManager(page, { final: run("FAIL", "SAFE_OFF_NOT_VERIFIED", false) });
  const panel = await openAndSelect(page);
  await confirmAndStart(panel);
  await expect(panel.getByTestId("run-outcome")).toHaveText("FAIL");
  await expect(panel.getByTestId("run-reason")).toHaveText("Reason: SAFE_OFF_NOT_VERIFIED");
  await expect(panel.getByTestId("receipt-safe-off")).toHaveText("NOT VERIFIED");
});

test("Manager HTTP failure on Batch status keeps the Batch unresolved and never resubmits", async ({ page }) => {
  const counters = await mockManager(page, { pollStatus: 503 });
  const panel = await openAndSelect(page);
  await confirmAndStart(panel);
  await expect(panel.getByRole("alert")).toContainText("Manager programming path is unavailable");
  // Still observing (never resubmitted): the start control stays busy and disabled.
  await expect(panel.getByRole("button", { name: "Running…" })).toBeDisabled();
  await page.waitForTimeout(1500);
  expect(counters.batches).toBe(1);
});
