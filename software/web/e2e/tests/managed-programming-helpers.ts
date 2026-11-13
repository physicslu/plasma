import { createHash } from "node:crypto";
import type { Page, Route } from "@playwright/test";

// Host-only helpers for the unified managed Programming UI (EMode + PMode).
// The Manager BFF is mocked at the Browser boundary: Mock Manager, Mock PPU,
// Fake Provider. Results prove Console behaviour only. They are NOT physical
// PPU / FPGA / DUT evidence and never count as production qualification.

export const FIRMWARE = Buffer.from(Array.from({ length: 4096 }, (_, i) => i % 251));
export const BUNDLE = Buffer.from(Array.from({ length: 6000 }, (_, i) => (i * 7) % 253));
export const sha = (digit: string) => digit.repeat(64);
export const RESOURCE_SHA = sha("9");
export const ACTIVE_SET_SHA = sha("b");

export type MockPpu = {
  alias: string;
  ppuId: string | null;
  facilityId?: string;
  lifecycle?: "commissioned" | "pending" | "disabled";
  transport?: "reachable" | "unreachable";
  observation?: "current" | "stale";
  execution?: "ready" | "unavailable";
  enabledSites?: number[];
  busySites?: number[];
  paired?: boolean;
  runtimeState?: string;
  deploymentState?: string | null;
  /** Site interface the PPU reports: "openocd" (hardware path) or "mock". */
  siteInterface?: string;
};

export const Z2: MockPpu = { alias: "z2", ppuId: "z2-hil", facilityId: "lab", enabledSites: [2] };

export function route(sites = [2], operations = ["flash_cycle"]) {
  return {
    route_id: "z2-site2-stm32f103c8t6", target: { platform: "linux-armv7", board: "pynq-z2", fpga_part: "xc7z020clg400-1" },
    icpn: "STM32F103C8T6", sites, provider: "openocd-platform-reference", profile: "stm32f103c8t6-site2",
    operations, driver_abi: "plasma_swd:5", transport: "fpga", max_image_bytes: 65536,
    target_config: "target/stm32f1x.cfg", flash_base: 134217728, flash_size: 65536,
  };
}

/** The Route of one programming Job (E / P / V list) and of the independent Read Job. */
export function operationsRoute(sites = [2], operations = ["erase", "program", "verify", "read"]) {
  return { ...route(sites, operations), route_id: "z2-site2-stm32f103c8t6-operations",
    profile: "stm32f103c8t6-site2-operations" };
}

/** What the mock IC holds: Read Memory returns this pattern from its address. */
export function flashBytes(address: number, length: number): Buffer {
  return Buffer.from(Array.from({ length }, (_, i) => (address + i) % 247));
}

const device = {
  vendor: "STMicroelectronics", family: "STM32F1", subfamily: null, plasma_series: "STM32F1",
  identifier: "STM32F103C8T6", identifier_kind: "manufacturer_part_number", icpn: "STM32F103C8T6",
  identity: { state: "IDENTIFIED" }, package: "LQFP48", pin_count: "48", flash_size: "64K",
  temperature_grade: null, option_suffix: null, base_device: "STM32F103C8", cpu_architectures: ["cortex-m3"],
  backend: { type: "openocd", distribution: "upstream", target_config: "target/stm32f1x.cfg", mapping_status: "mapped", mapping_method: null },
  catalog_verification: { status: null, source_type: null, source_authority: null, source_reference: null },
  physical_validation: { engineering_status: "no_evidence", ppu_status: "no_evidence", socket_status: "no_evidence" },
  catalog: { scope: "production_admitted", version: null, revision_sha256: null }, catalog_origin: "test",
  catalog_level: 3, catalog_level_state: "FAMILY_READY", job_selectable: true,
};

function fleetView(ppu: MockPpu) {
  const enabled = ppu.enabledSites ?? [2];
  const reachable = (ppu.transport ?? "reachable") === "reachable";
  const sites = Array.from({ length: 8 }, (_, index) => {
    const siteId = index + 1;
    const on = enabled.includes(siteId);
    const busy = (ppu.busySites ?? []).includes(siteId);
    return {
      site_id: siteId, enabled: on, state: !on ? "disabled" : busy ? "running" : "idle",
      current_job_id: busy ? "job-busy" : null, latest_job: null,
      interface: on ? ppu.siteInterface ?? "openocd" : null, target: on ? "STM32F103C8T6" : null,
    };
  });
  return {
    alias: ppu.alias,
    identity: { ppu_id: ppu.ppuId, facility_id: ppu.facilityId ?? "lab", model: "PYNQ-Z2", display_name: ppu.ppuId ?? ppu.alias },
    transport_state: ppu.transport ?? "reachable",
    execution_state: reachable ? ppu.execution ?? "ready" : "unknown",
    observation: { state: ppu.observation ?? "current", last_success_at: "2026-11-11T00:00:00+00:00", stale_age_s: 0 },
    topology: { source: "current", site_count: 8, enabled_site_count: enabled.length, sites: reachable ? sites : [] },
    current_capacity: { site_count: 8, enabled_site_count: enabled.length },
    identity_conflict: false,
    degraded: !reachable || (ppu.execution ?? "ready") !== "ready",
  };
}

function bootstrapStatus(ppu: MockPpu) {
  return {
    ok: true, ppu_alias: ppu.alias, bootstrap_endpoint_policy: "same-host:18081",
    pairing: { paired: ppu.paired ?? true, device_id: `device-${ppu.alias}`, device_match: true,
      credential_persistence: "file", updated_at: "2026-11-09T00:00:00+00:00", controller_generation: 2 },
    bootstrap: {
      schema_version: 1, bootstrap: { api_version: "1", version: "0.1.0", state: "bootstrap_ready" },
      identity: { device_id: `device-${ppu.alias}`, ppu_id: ppu.ppuId, facility_id: ppu.facilityId ?? "lab", hardware_revision: null },
      runtime: { state: ppu.runtimeState ?? "runtime_active", release_id: "r", product_version: "0.2.1", git_sha: "a".repeat(40), target: "linux-armv7l", reason: null },
      fpga: { pl_version: null, pl_compatibility: "not_managed", pl_qualification: "not_qualified" },
      capabilities: { runtime_deployment: true, identity_update: false, fpga_update: false },
      deployment: ppu.deploymentState ? { transaction_id: "t", state: ppu.deploymentState, upload_id: "u",
        started_at_epoch_s: 0, updated_at_epoch_s: 0, error: null, result: null } : null,
    },
  };
}

export type RunOutcome = "PASS" | "FAIL" | "OUTCOME_UNKNOWN" | "BLOCKED";

export type RunScript = {
  /** Plan decision: Resource Reuse (default) or B1/B2/B3 activation. */
  activationRequired?: boolean;
  planStatus?: number;
  planError?: { code: string; message: string };
  startStatus?: number;
  startError?: { code: string; message: string };
  /** true: the Manager admits the run but the Start answer never arrives (HTTP 504). */
  startLost?: boolean;
  outcome?: RunOutcome;
  reason?: string | null;
  safeOff?: boolean;
  /** false: the receipt readback SHA256 differs from the expected Image. */
  readbackOk?: boolean;
  /** Number of status reads that still report a running Job. */
  runningPolls?: number;
  /** The list the PPU claims it ran (default: exactly the planned list). */
  observedOperations?: string[];
  /** true: the Read Memory download differs from the receipt SHA256. */
  readTamper?: boolean;
  /** HTTP status of the Read Memory download (default 200). */
  readDownloadStatus?: number;
};

export type Counters = {
  plans: Array<{ alias: string; body: Record<string, unknown> }>;
  starts: Array<{ alias: string; body: Record<string, unknown> }>;
  /** Read Memory binary downloads (run IDs). */
  downloads: string[];
  /** EMode Batch requests, stop-queuing requests and Jobs the mock PPU accepted. */
  batches: Array<{ alias: string; body: Record<string, unknown> }>;
  stops: string[];
  jobs: string[];
  polls: number;
  acks: number;
  /** Start Outcome Reconciliation: issued Batch start IDs, read-only queries, voids. */
  issued: string[];
  reconciles: string[];
  voids: string[];
  requests: string[];
  mutations: string[];
};

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
const hex32 = (n: number) => n.toString(16).padStart(32, "0");

/**
 * Mock Manager. `script(alias, siteId)` decides each run. Every identity is
 * derived per (alias, site, run) so cross-PPU / cross-Site mix-ups are visible.
 */
export async function mockManager(page: Page, options: {
  ppus?: MockPpu[];
  routes?: unknown[];
  routesStatus?: number;
  /** `attempt` is 1 for a single run and the attempt number inside a Batch. */
  script?: (alias: string, siteId: number, attempt: number) => RunScript;
  registryStatus?: number;
  /** Batch request refusal / lost response. */
  batchStatus?: number;
  batchError?: { code: string; message: string };
  /** true: the Manager admits the Batch but the answer never arrives (HTTP 504). */
  batchLost?: boolean;
  /** Fault injection on the reconciliation answer: an HTTP status, or an edited view. */
  reconcile?: (view: Record<string, unknown>) => Record<string, unknown> | number;
  /** HTTP status of the Batch start ID issue (default 200). */
  issueStatus?: number;
} = {}) {
  const ppus = options.ppus ?? [Z2];
  const counters: Counters = { plans: [], starts: [], downloads: [], batches: [], stops: [], jobs: [], polls: 0, acks: 0, issued: [], reconciles: [], voids: [], requests: [], mutations: [] };
  // Journalled start admissions, as the Manager keeps them.
  // A Batch start is issued under no PPU: it gets one only when a Target Set
  // is admitted with it (PR-C, ADR 5.8).
  type StartRecord = { alias: string | null; kind: "run" | "batch"; state: "ISSUED" | "CONSUMED" | "VOIDED";
    siteId: number | null; targets?: Array<{ ppu_alias: string; site_ids: number[] }> | null;
    operation: string; operations: string[] | null; bindingSha: string | null; runId: string | null; batchId: string | null };
  const startRecords = new Map<string, StartRecord>();
  const pendingBatchStarts = new Set<string>();
  const plans = new Map<string, { alias: string; siteId: number; body: Record<string, unknown>; script: RunScript; payload: Record<string, unknown> }>();
  const runs = new Map<string, { alias: string; planId: string; polls: number; acknowledged: boolean }>();
  let sequence = 0;

  page.on("request", request => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/")) return;
    counters.requests.push(`${request.method()} ${url.pathname}`);
    if (request.method() !== "GET") counters.mutations.push(`${request.method()} ${url.pathname}`);
  });

  await page.route("**/api/manager/ppu", r => r.fulfill(json({ ok: true, managed: true, configured: true, ppu_alias: ppus[0]?.alias ?? "z2" })));
  await page.route(/\/api\/manager\/registry$/, r => r.fulfill(options.registryStatus
    ? json({ ok: false, error: { code: "manager_unavailable", message: "Manager Registry unavailable" } }, options.registryStatus)
    : json({ ok: true, service: "plasma-manager", contract_version: "1", mutable: true, storage: "file",
      ppus: ppus.map(ppu => ({ alias: ppu.alias, endpoint: "http://192.0.2.10:18080", lifecycle: ppu.lifecycle ?? "commissioned",
        registered_at: "2026-11-09T00:00:00+00:00", updated_at: "2026-11-09T00:00:00+00:00" })) })));
  await page.route(/\/api\/fleet$/, r => r.fulfill(json({
    ok: true, contract_version: "1", observed_at: "2026-11-11T00:00:00+00:00", degraded: false,
    summary: {}, manager: {}, ppus: ppus.map(fleetView) })));
  await page.route(/\/api\/manager\/devices\/search\?/, r => r.fulfill(json({
    ok: true, scope: "customer_ic_selector", query: "STM32", levels: [1, 2, 3], catalog_size: 1,
    count: 1, total_count: 1, limit: 8, offset: 0, results: [device] })));
  await page.route(/\/api\/manager\/registry\/[^/]+\/bootstrap$/, r => {
    const alias = new URL(r.request().url()).pathname.split("/")[4];
    const ppu = ppus.find(item => item.alias === alias);
    return r.fulfill(ppu ? json(bootstrapStatus(ppu)) : json({ ok: false, error: { code: "ppu_not_found", message: "not found" } }, 404));
  });
  await page.route(/\/bootstrap\/programming\/routes$/, r => r.fulfill(options.routesStatus
    ? json({ ok: false, error: { code: "programming_routes_unavailable", message: "Programming Routes are unavailable: ROUTE_ROOT_UNAVAILABLE" } }, options.routesStatus)
    : json({ ok: true, routes: options.routes ?? [route(), operationsRoute()] })));

  function makePlan(alias: string, body: Record<string, unknown>, attempt: number) {
    const siteId = Number(body.site_id);
    const script = options.script?.(alias, siteId, attempt) ?? {};
    if (script.planError) return { error: script.planError, status: script.planStatus ?? 422 };
    sequence += 1;
    const planId = hex32(sequence);
    // One programming Job carries `operations`; read / legacy flash_cycle a single `operation`.
    const operations = Array.isArray(body.operations) ? body.operations as string[] : null;
    const kind = operations ? "programming" : String(body.operation);
    const hasImage = "bundle_base64" in body || "image_base64" in body;
    const source = "bundle_base64" in body ? "bundle" : hasImage ? "image" : "range";
    const bytes = hasImage ? Buffer.from(String(body.bundle_base64 ?? body.image_base64), "base64") : Buffer.alloc(0);
    const digest = createHash("sha256").update(bytes).digest("hex");
    const range = hasImage ? { address: 134217728, length: bytes.length }
      : { address: Number(body.address), length: Number(body.length) };
    const activation = script.activationRequired ?? false;
    const ppu = ppus.find(item => item.alias === alias);
    const planRoute = kind === "flash_cycle" ? route() : operationsRoute();
    const payload = {
      schema: "plasma.manager.bundle-programming-plan.v3", plan_id: planId, ppu_alias: alias, site_id: siteId,
      operation: kind, operations, source, route: planRoute,
      bundle: hasImage ? { archive_sha256: source === "bundle" ? digest : sha("a"), archive_size: bytes.length, bundle_name: "bundle",
        provider: planRoute.provider, profile: planRoute.profile, asset_package_id: "fw",
        image_filename: "image.bin", image_sha256: source === "bundle" ? sha("5") : digest, image_size: bytes.length, icpn: "STM32F103C8T6" } : null,
      resource: { resource_set_sha256: RESOURCE_SHA, reuse: !activation,
        ppu_reported: { state: "VERIFIED", asset_set_sha256: ACTIVE_SET_SHA, generation: 3,
          resource_set_sha256: activation ? sha("7") : RESOURCE_SHA } },
      image_asset: hasImage ? { image_asset_sha256: sha("6"), sha256: source === "bundle" ? sha("5") : digest, size: bytes.length,
        load_address: 134217728, format: "binary" } : null,
      job_binding: { operation: kind, ...(operations ? { operations } : {}), range,
        image_asset_sha256: hasImage ? sha("6") : null, resource_set_sha256: RESOURCE_SHA, ppu_id: ppu?.ppuId, site_id: siteId },
      // Binding identity is unique per (PPU, Site, plan): never shared.
      job_binding_sha256: `${alias}-site${siteId}-plan${sequence}`.padEnd(64, "0").slice(0, 64),
      active_asset_set: { state: "ACTIVE", asset_set_sha256: ACTIVE_SET_SHA },
      activation_required: activation, fpga_load: false,
      steps: [...(activation ? ["B1_UPLOAD", "B2_ADMIT", "B3_ACTIVATE"] : ["RESOURCE_REUSE"]), `${kind.toUpperCase()}_JOB`, "VERIFY_RECEIPT"],
      catalog_gate: "NOT_USED", confirm_required: "PROGRAM",
    };
    plans.set(planId, { alias, siteId, body, script, payload });
    startRecords.set(planId, { alias, kind: "run", state: "ISSUED", siteId, operation: kind, operations,
      bindingSha: payload.job_binding_sha256, runId: null, batchId: null });
    return { payload };
  }

  await page.route(/\/bootstrap\/programming\/plans$/, async (r: Route) => {
    const alias = new URL(r.request().url()).pathname.split("/")[4];
    const body = r.request().postDataJSON() as Record<string, unknown>;
    counters.plans.push({ alias, body });
    const made = makePlan(alias, body, 1);
    if (!made.payload) return r.fulfill(json({ ok: false, error: made.error }, made.status));
    await r.fulfill(json({ ok: true, plan: made.payload }));
  });

  function runRecord(runId: string) {
    const state = runs.get(runId)!;
    const planned = plans.get(state.planId)!;
    const script = planned.script;
    const finished = state.polls > (script.runningPolls ?? 1);
    const outcome = finished ? script.outcome ?? "PASS" : null;
    const activation = Boolean(planned.payload.activation_required);
    const asset = planned.payload.image_asset as { sha256: string; size: number } | null;
    const imageSha = asset?.sha256 ?? null;
    const size = asset?.size ?? null;
    const kind = String(planned.payload.operation);
    const operations = planned.payload.operations as string[] | null;
    const range = (planned.payload.job_binding as { range: { address: number; length: number } }).range;
    const readback = script.readbackOk === false ? sha("0") : imageSha;
    const expectedSteps: Record<string, Record<string, unknown>> = {};
    if (operations?.includes("erase")) {
      expectedSteps.erase = { erase_address: range.address, erase_length: Math.ceil(range.length / 1024) * 1024,
        ...(operations.length === 1 ? { blank_verified: true, bytes_verified: range.length } : {}) };
    }
    if (operations?.includes("program")) expectedSteps.program = { write_address: range.address, bytes_written: range.length, image_sha256: imageSha };
    if (operations?.includes("verify")) expectedSteps.verify = { verify_address: range.address, bytes_verified: range.length, readback_sha256: imageSha };
    const observedSteps = { ...expectedSteps,
      ...(expectedSteps.verify ? { verify: { ...expectedSteps.verify, readback_sha256: readback } } : {}) };
    const verifies = kind === "flash_cycle" || Boolean(operations?.includes("verify"));
    const readSha = createHash("sha256").update(flashBytes(range.address, range.length)).digest("hex");
    const jobId = `job-${planned.alias}-site${planned.siteId}-${state.planId.slice(-4)}`;
    const steps = [
      { step: "PREFLIGHT", result: "PASS", at: "t" },
      ...(activation
        ? [{ step: "B1_UPLOAD", result: "PASS", at: "t" }, { step: "B2_ADMIT", result: "PASS", at: "t" }, { step: "B3_ACTIVATE", result: "PASS", at: "t" }]
        : [{ step: "RESOURCE_REUSE", result: "PPU_VERIFIED", at: "t" }]),
      { step: `${kind.toUpperCase()}_SUBMIT`, result: "ACCEPTED", at: "t" },
      ...(outcome === "PASS" || outcome === "FAIL" ? [{ step: "VERIFY_RECEIPT", result: outcome, at: "t" }] : []),
    ];
    const safeOff = script.safeOff ?? true;
    return {
      schema: "plasma.manager.bundle-programming-run.v1", run_id: runId, ppu_alias: planned.alias, site_id: planned.siteId,
      plan: planned.payload, state: outcome ? "finished" : "running", outcome,
      reason: outcome === "PASS" ? null : outcome ? script.reason ?? `${outcome}_REASON` : null,
      created_at: "t", updated_at: "t", steps, activation: activation ? { b3_transaction_id: "c".repeat(32) } : {},
      job: { job_id: jobId, state: outcome ? (outcome === "PASS" ? "success" : "failed") : "running", stage: kind,
        progress_percent: outcome ? 100 : 40 },
      receipt: outcome === "PASS" || outcome === "FAIL" ? {
        schema: "plasma.manager.programming-receipt.v3", job_id: jobId, job_state: "success", operation: kind,
        operations, observed_operations: operations ? script.observedOperations ?? operations : null,
        expected_steps: operations ? expectedSteps : null, observed_steps: operations ? observedSteps : null,
        range, read_output: kind === "read" ? { address: range.address, bytes: range.length, sha256: readSha,
          filename: `read-STM32F103C8T6-0x${range.address.toString(16).padStart(8, "0")}-${range.length}.bin`,
          available: outcome === "PASS" } : null,
        site_id: planned.siteId, target: "STM32F103C8T6",
        expected_image_sha256: imageSha, expected_image_size: size, observed_image_sha256: imageSha, observed_image_size: size,
        readback_sha256: verifies ? readback : null, bytes_verified: verifies ? size : null,
        expected_resource_set_sha256: RESOURCE_SHA, observed_resource_set_sha256: RESOURCE_SHA,
        expected_job_binding_sha256: planned.payload.job_binding_sha256, observed_job_binding_sha256: planned.payload.job_binding_sha256,
        active_asset_set_sha256: ACTIVE_SET_SHA, resource_reuse: !activation,
        safe_off: safeOff, flash_result: "PASS", elapsed_ms: 7000,
      } : null,
      job_submission_count: 1, auto_retry: "DISABLED", acknowledged: state.acknowledged,
    };
  }

  await page.route(/\/bootstrap\/programming\/runs$/, async (r: Route) => {
    const alias = new URL(r.request().url()).pathname.split("/")[4];
    const body = r.request().postDataJSON() as Record<string, unknown>;
    counters.starts.push({ alias, body });
    const planned = plans.get(String(body.plan_id));
    if (!planned || runs.has(`run:${body.plan_id}`) || startRecords.get(String(body.plan_id))?.state === "VOIDED") {
      return r.fulfill(json({ ok: false, error: { code: "programming_plan_not_found", message: "plan is missing or already consumed" } }, 404));
    }
    if (planned.script.startError) {
      return r.fulfill(json({ ok: false, error: planned.script.startError }, planned.script.startStatus ?? 409));
    }
    const runId = hex32(0xf000 + counters.starts.length);
    runs.set(runId, { alias, planId: String(body.plan_id), polls: 0, acknowledged: false });
    runs.set(`run:${body.plan_id}`, runs.get(runId)!);
    Object.assign(startRecords.get(String(body.plan_id))!, { state: "CONSUMED", runId });
    if (planned.script.startLost) {
      // Admitted and journalled; only the answer is lost.
      return r.fulfill(json({ ok: false, error: { code: "manager_unavailable", message: "Manager Bootstrap path is unavailable" } }, 504));
    }
    await r.fulfill(json({ ok: true, run: runRecord(runId) }, 202));
  });
  await page.route(/\/bootstrap\/programming\/runs\/[0-9a-f]{32}$/, async (r: Route) => {
    counters.polls += 1;
    const runId = new URL(r.request().url()).pathname.split("/").pop()!;
    const state = runs.get(runId);
    if (!state) return r.fulfill(json({ ok: false, error: { code: "programming_run_not_found", message: "not found" } }, 404));
    state.polls += 1;
    await r.fulfill(json({ ok: true, run: runRecord(runId) }));
  });
  // ---- EMode Batch: the mock Manager applies the same Retry / Stop contract
  // over a Target Set, walking its Sites sequentially like the real one.
  type MockAttempt = { attempt: number; planId: string; runId: string; retry: Record<string, unknown> | null };
  type MockUnit = {
    siteId: number; status: string; outcome: string | null; reason: string | null;
    failureDomain: string | null; attempts: MockAttempt[];
  };
  type MockBatch = {
    alias: string; body: Record<string, unknown>; stopRequested: boolean; startId: string | null;
    units: MockUnit[]; index: number; outcome: string | null; reason: string | null;
  };
  const batches = new Map<string, MockBatch>();

  function batchSites(body: Record<string, unknown>): number[] {
    const targets = (body.targets ?? []) as Array<{ ppu_alias: string; site_ids: number[] }>;
    return targets.flatMap(target => target.site_ids.map(Number));
  }

  function planBodyFor(batch: MockBatch, siteId: number) {
    const { operations, image_base64, image_filename, bundle_base64, address, length, icpn } = batch.body;
    return Object.fromEntries(Object.entries({
      icpn, site_id: siteId, operations, image_base64, image_filename, bundle_base64, address, length,
    }).filter(([, value]) => value !== undefined));
  }

  function submitAttempt(batch: MockBatch, unit: MockUnit, planId: string) {
    const runId = hex32(0xb000 + runs.size + 1);
    runs.set(runId, { alias: batch.alias, planId, polls: 0, acknowledged: false });
    unit.attempts.push({ attempt: unit.attempts.length + 1, planId, runId, retry: null });
    unit.status = "RUNNING";
    Object.assign(startRecords.get(planId)!, { state: "CONSUMED", runId });
    counters.starts.push({ alias: batch.alias, body: { plan_id: planId, confirm: "PROGRAM" } });
    counters.jobs.push(runRecord(runId).job.job_id);
  }

  /** Plan + submit the first attempt of the Site the walk is now on. */
  function startUnit(batch: MockBatch): boolean {
    const unit = batch.units[batch.index];
    if (!unit) return false;
    const made = makePlan(batch.alias, planBodyFor(batch, unit.siteId), 1);
    if (!made.payload) {
      // Nothing was submitted for this Site: provably BLOCKED, and the rest
      // of the Batch is untouched.
      unit.status = "BLOCKED";
      unit.outcome = "BLOCKED";
      unit.reason = String((made.error as { code?: string } | undefined)?.code ?? "programming_plan_refused");
      unit.failureDomain = "TARGET_NOT_READY";
      return nextUnit(batch);
    }
    submitAttempt(batch, unit, String(made.payload.plan_id));
    return true;
  }

  /** Move to the next Site, or finish. Returns whether a Job was submitted. */
  function nextUnit(batch: MockBatch): boolean {
    const failed = batch.units.filter(unit => unit.outcome === "FAIL").length;
    const latched = batch.units.some(unit => unit.outcome === "OUTCOME_UNKNOWN");
    const stop = batch.body.stop_policy as { kind: string; threshold?: number } | undefined;
    batch.index += 1;
    const skip = (reason: string) => {
      for (const unit of batch.units.slice(batch.index)) {
        if (unit.outcome != null) continue;
        unit.status = "SKIPPED";
        unit.outcome = "BLOCKED";
        unit.reason = reason;
        unit.failureDomain = "TARGET_NOT_READY";
      }
      batch.index = batch.units.length;
      finish(batch, reason);
      return false;
    };
    if (batch.index >= batch.units.length) {
      finish(batch, null);
      return false;
    }
    // One PPU: an unknown outcome latches it and skips its remaining Sites.
    if (latched) return skip("PPU_LATCHED_OUTCOME_UNKNOWN");
    if (batch.stopRequested) return skip("STOP_REQUESTED_NOTHING_SUBMITTED");
    if (stop?.kind === "failed_sites" && failed >= Number(stop.threshold ?? 1)) {
      return skip("STOP_POLICY_FAILED_SITES_THRESHOLD_REACHED");
    }
    return startUnit(batch);
  }

  /** Worst wins: OUTCOME_UNKNOWN > FAIL > PARTIAL > PASS; BLOCKED ran nothing. */
  function finish(batch: MockBatch, reason: string | null) {
    const outcomes = batch.units.map(unit => unit.outcome);
    const executed = outcomes.filter(outcome => outcome === "PASS" || outcome === "FAIL"
      || outcome === "OUTCOME_UNKNOWN");
    batch.outcome = outcomes.includes("OUTCOME_UNKNOWN") ? "OUTCOME_UNKNOWN"
      : outcomes.includes("FAIL") ? "FAIL"
      : !executed.length ? "BLOCKED"
      : executed.length < outcomes.length ? "PARTIAL"
      : "PASS";
    batch.reason = reason
      ?? batch.units.find(unit => unit.outcome !== "PASS" && unit.reason)?.reason
      ?? null;
  }

  function advance(batch: MockBatch) {
    if (batch.outcome) return;
    const unit = batch.units[batch.index];
    if (!unit || !unit.attempts.length) return;
    const last = unit.attempts[unit.attempts.length - 1];
    runs.get(last.runId)!.polls += 1;
    const run = runRecord(last.runId);
    if (!run.outcome) return;
    if (run.outcome !== "FAIL") {
      unit.status = run.outcome === "OUTCOME_UNKNOWN" ? "UNKNOWN" : "COMPLETED";
      unit.outcome = run.outcome;
      unit.reason = run.reason;
      if (run.outcome === "OUTCOME_UNKNOWN") unit.failureDomain = "TARGET_TRANSACTION_UNKNOWN";
      nextUnit(batch);
      return;
    }
    const retryLimit = Number(batch.body.retry_limit ?? 0);
    const stop = batch.body.stop_policy as { kind: string; threshold?: number } | undefined;
    const eligible = run.receipt?.safe_off === true;
    const why = eligible ? "DEFINITE_FAIL_SAFE_OFF_VERIFIED" : "SAFE_OFF_NOT_VERIFIED";
    const failedBefore = batch.units.filter(item => item.outcome === "FAIL").length;
    let final: string | null;
    if (last.attempt > retryLimit) final = retryLimit ? "RETRY_LIMIT_EXHAUSTED" : run.reason;
    else if (!eligible) final = `RETRY_NOT_ELIGIBLE_${why}`;
    else if (stop?.kind === "failed_sites" && failedBefore + 1 >= Number(stop.threshold ?? 1)) {
      final = "STOP_POLICY_FAILED_SITES_THRESHOLD_REACHED";
    }
    else if (batch.stopRequested) final = "STOP_REQUESTED_NO_FURTHER_ATTEMPT";
    else final = null;
    last.retry = { eligible, reason: why, decision: final === null ? "RETRY" : "NO_RETRY" };
    if (final !== null) {
      unit.status = "COMPLETED";
      unit.outcome = "FAIL";
      unit.reason = final;
      nextUnit(batch);
      return;
    }
    const made = makePlan(batch.alias, planBodyFor(batch, unit.siteId), last.attempt + 1);
    submitAttempt(batch, unit, String(made.payload!.plan_id));
  }

  function batchRecord(batchId: string) {
    const batch = batches.get(batchId)!;
    const attemptsOf = (unit: MockUnit) => unit.attempts.map(item => {
      const run = runRecord(item.runId);
      return { attempt: item.attempt, plan_id: item.planId, run_id: item.runId, job_id: run.job.job_id,
        job_binding_sha256: plans.get(item.planId)!.payload.job_binding_sha256,
        state: run.outcome ? "finished" : "running", outcome: run.outcome, reason: run.reason,
        safe_off: run.receipt?.safe_off ?? null, retry: item.retry };
    });
    const units = batch.units.map(unit => ({
      ppu_alias: batch.alias, site_id: unit.siteId, status: unit.status, outcome: unit.outcome,
      reason: unit.reason, failure_domain: unit.failureDomain, attempts: attemptsOf(unit),
    }));
    const attempts = units.flatMap(unit => unit.attempts);
    const running = batch.units[batch.index] ?? batch.units[batch.units.length - 1];
    const last = running?.attempts[running.attempts.length - 1]
      ?? [...batch.units].reverse().flatMap(unit => unit.attempts).slice(-1)[0];
    const outcomes = units.map(unit => unit.outcome);
    const record: Record<string, unknown> = {
      schema: "plasma.manager.programming-batch.v1", batch_id: batchId, start_id: batch.startId,
      targets: batch.body.targets, units,
      icpn: "STM32F103C8T6", operations: batch.body.operations,
      source: "bundle_base64" in batch.body ? "bundle" : "image_base64" in batch.body ? "image" : "range",
      policy: { repeat: 1, retry_limit: Number(batch.body.retry_limit ?? 0), stop_policy: batch.body.stop_policy ?? { kind: "never" } },
      state: batch.outcome ? "finished" : "running",
      execution_status: batch.outcome ? (batch.stopRequested ? "STOPPED" : "COMPLETED") : "RUNNING",
      outcome: batch.outcome, reason: batch.reason, failure_domain: null,
      stop_requested: batch.stopRequested, attempts, current_run: last ? runRecord(last.runId) : null,
      counts: {
        pass: outcomes.filter(outcome => outcome === "PASS").length,
        fail: outcomes.filter(outcome => outcome === "FAIL").length,
        blocked: outcomes.filter(outcome => outcome === "BLOCKED").length,
        unknown: outcomes.filter(outcome => outcome === "OUTCOME_UNKNOWN").length,
        sites: units.length, attempts: attempts.length,
      },
      auto_retry: "DISABLED",
    };
    // The projection a single-Site Batch has always carried.
    if (units.length === 1) {
      record.ppu_alias = batch.alias;
      record.site_id = units[0].site_id;
    }
    return record;
  }

  // The canonical Manager-owned Batch resource: not under a PPU (ADR 5.8).
  await page.route(/\/api\/manager\/programming\/batches$/, async (r: Route) => {
    const body = r.request().postDataJSON() as Record<string, unknown>;
    const targets = (body.targets ?? []) as Array<{ ppu_alias: string; site_ids: number[] }>;
    const alias = targets[0]?.ppu_alias ?? "";
    counters.batches.push({ alias, body });
    // A Batch request carries the plan inputs; the Manager plans PER SITE, so
    // the plan counter records the body the first Site is planned with.
    counters.plans.push({ alias, body: planBodyFor({ alias, body } as MockBatch, batchSites(body)[0]) });
    if (options.batchStatus) {
      return r.fulfill(json({ ok: false, error: options.batchError ?? { code: "manager_unavailable", message: "Manager unavailable" } }, options.batchStatus));
    }
    const startId = "start_id" in body ? String(body.start_id) : null;
    // The canonical resource REQUIRES a Manager-issued start (ADR 5.3).
    if (startId === null) {
      return r.fulfill(json({ ok: false, error: { code: "invalid_request", message: "a Batch requires a Manager-issued start_id; obtain one first" } }, 400));
    }
    if (!pendingBatchStarts.has(startId)) {
      return r.fulfill(json({ ok: false, error: { code: "programming_start_not_startable", message: "this start ID is unknown, was already used, was voided or expired; nothing was started" } }, 409));
    }
    const sites = batchSites(body);
    const first = makePlan(alias, planBodyFor({ alias, body } as MockBatch, sites[0]), 1);
    if (!first.payload) return r.fulfill(json({ ok: false, error: first.error }, first.status));
    const planned = plans.get(String(first.payload.plan_id))!;
    if (planned.script.startError) {
      counters.starts.push({ alias, body: { plan_id: first.payload.plan_id, confirm: "PROGRAM" } });
      return r.fulfill(json({ ok: false, error: planned.script.startError }, planned.script.startStatus ?? 409));
    }
    const batchId = hex32(0xba000 + batches.size + 1);
    const batch: MockBatch = {
      alias, body, stopRequested: false, startId, index: 0, outcome: null, reason: null,
      units: sites.map(siteId => ({
        siteId, status: "NOT_RUN", outcome: null, reason: null, failureDomain: null, attempts: [],
      })),
    };
    pendingBatchStarts.delete(startId);
    Object.assign(startRecords.get(startId)!, {
      state: "CONSUMED", batchId, alias, targets: body.targets,
      siteId: sites.length === 1 ? sites[0] : null,
    });
    batches.set(batchId, batch);
    submitAttempt(batch, batch.units[0], String(first.payload.plan_id));
    if (options.batchLost) {
      return r.fulfill(json({ ok: false, error: { code: "manager_unavailable", message: "Manager unavailable" } }, 504));
    }
    await r.fulfill(json({ ok: true, batch: batchRecord(batchId) }, 202));
  });
  await page.route(/\/api\/manager\/programming\/batches\/[0-9a-f]{32}$/, async (r: Route) => {
    counters.polls += 1;
    const batchId = new URL(r.request().url()).pathname.split("/").pop()!;
    advance(batches.get(batchId)!);
    await r.fulfill(json({ ok: true, batch: batchRecord(batchId) }));
  });
  await page.route(/\/api\/manager\/programming\/batches\/[0-9a-f]{32}\/stop$/, async (r: Route) => {
    const batchId = new URL(r.request().url()).pathname.split("/").slice(-2)[0];
    counters.stops.push(JSON.stringify(r.request().postDataJSON()));
    const batch = batches.get(batchId)!;
    if (!batch.outcome) batch.stopRequested = true;
    await r.fulfill(json({ ok: true, batch: batchRecord(batchId) }));
  });

  await page.route(/\/bootstrap\/programming\/runs\/[0-9a-f]{32}\/output$/, async (r: Route) => {
    const runId = new URL(r.request().url()).pathname.split("/").slice(-2)[0];
    counters.downloads.push(runId);
    const planned = plans.get(runs.get(runId)!.planId)!;
    if (planned.script.readDownloadStatus) {
      return r.fulfill(json({ ok: false, error: { code: "read_output_unavailable", message: "the Read Memory output is no longer retained; read again" } },
        planned.script.readDownloadStatus));
    }
    const range = (planned.payload.job_binding as { range: { address: number; length: number } }).range;
    const data = flashBytes(range.address, range.length);
    if (planned.script.readTamper) data[0] ^= 0xff;
    await r.fulfill({ status: 200, contentType: "application/octet-stream", body: data });
  });
  await page.route(/\/bootstrap\/programming\/runs\/[0-9a-f]{32}\/acknowledge$/, async (r: Route) => {
    counters.acks += 1;
    const runId = new URL(r.request().url()).pathname.split("/").slice(-2)[0];
    const state = runs.get(runId)!;
    state.acknowledged = true;
    await r.fulfill(json({ ok: true, run: runRecord(runId) }));
  });

  // ---- Start Outcome Reconciliation (same contract as plasma_manager.programming).
  function reconciliation(alias: string | null, startId: string): Record<string, unknown> {
    const record = startRecords.get(startId);
    const view: Record<string, unknown> = {
      schema: "plasma.manager.programming-start-reconciliation.v1", start_id: startId, ppu_alias: alias,
      kind: null, state: "OUTCOME_UNKNOWN", reason: null, outcome: null, identity: null, run: null, batch: null,
      acknowledged: null, unknown_run_id: null, expires_in_s: null, read_only: true, auto_retry: "DISABLED",
    };
    if (!record) return { ...view, reason: "START_NOT_RECORDED" };
    // The PPU is an answer here, read off the record, never asked for.
    view.ppu_alias = record.alias;
    view.kind = record.kind;
    view.identity = { ppu_alias: record.alias, site_id: record.siteId, targets: record.targets ?? null,
      ppu_id: ppus.find(item => item.alias === record.alias)?.ppuId ?? null,
      operation: record.operation, operations: record.operations, job_binding_sha256: record.bindingSha };
    if (record.state === "VOIDED") return { ...view, state: "NOT_ACCEPTED", reason: "START_VOIDED_BEFORE_ADMISSION" };
    if (record.state === "ISSUED") {
      return { ...view, state: "ACCEPTANCE_PENDING", reason: "START_STILL_ADMISSIBLE", expires_in_s: 1800 };
    }
    if (record.kind === "run") {
      const state = runs.get(record.runId!)!;
      state.polls += 1;  // the Job advances with time, not because it was asked about
      const run = runRecord(record.runId!);
      Object.assign(view, { run, outcome: run.outcome });
      if (run.outcome === null) return { ...view, state: "ACCEPTED_RUNNING", reason: "RUN_IN_PROGRESS" };
      if (run.outcome === "OUTCOME_UNKNOWN") {
        return { ...view, reason: run.reason, acknowledged: state.acknowledged, unknown_run_id: record.runId };
      }
      return { ...view, state: "TERMINAL_CONFIRMED", reason: run.reason };
    }
    const batch = batches.get(record.batchId!)!;
    advance(batch);
    const shown = batchRecord(record.batchId!) as {
      operations: unknown; outcome: string | null; reason: string | null;
      attempts: Array<{ job_binding_sha256: string }>;
      current_run: { acknowledged: boolean; outcome: string | null; run_id: string } | null;
    };
    (view.identity as Record<string, unknown>).operations = shown.operations;
    (view.identity as Record<string, unknown>).job_binding_sha256 = shown.attempts[shown.attempts.length - 1]?.job_binding_sha256 ?? null;
    Object.assign(view, { batch: shown, outcome: shown.outcome });
    if (shown.outcome === null) return { ...view, state: "ACCEPTED_RUNNING", reason: "BATCH_IN_PROGRESS" };
    if (shown.outcome === "OUTCOME_UNKNOWN") {
      const current = shown.current_run;
      return { ...view, reason: shown.reason, acknowledged: current ? current.acknowledged : null,
        unknown_run_id: current?.outcome === "OUTCOME_UNKNOWN" ? current.run_id : null };
    }
    return { ...view, state: "TERMINAL_CONFIRMED", reason: shown.reason };
  }

  // The canonical start resource: Manager-owned, issued under no PPU.
  await page.route(/\/api\/manager\/programming\/starts$/, async (r: Route) => {
    if (options.issueStatus) {
      return r.fulfill(json({ ok: false, error: { code: "manager_unavailable", message: "Manager unavailable" } }, options.issueStatus));
    }
    const startId = hex32(0x5a000 + counters.issued.length + 1);
    counters.issued.push(startId);
    pendingBatchStarts.add(startId);
    startRecords.set(startId, { alias: null, kind: "batch", state: "ISSUED", siteId: null, operation: "programming",
      operations: null, bindingSha: null, runId: null, batchId: null });
    await r.fulfill(json({ ok: true, start: { start_id: startId, kind: "batch", ppu_alias: null, expires_in_s: 1800 } }));
  });
  await page.route(/\/api\/manager\/programming\/starts\/[0-9a-f]{32}$/, async (r: Route) => {
    const startId = new URL(r.request().url()).pathname.split("/").pop()!;
    counters.reconciles.push(startId);
    const view = reconciliation(startRecords.get(startId)?.alias ?? null, startId);
    const edited = options.reconcile ? options.reconcile(view) : view;
    if (typeof edited === "number") {
      return r.fulfill(json({ ok: false, error: { code: "manager_unavailable", message: "Manager unavailable" } }, edited));
    }
    await r.fulfill(json({ ok: true, reconciliation: edited }));
  });
  await page.route(/\/api\/manager\/programming\/starts\/[0-9a-f]{32}\/void$/, async (r: Route) => {
    const startId = new URL(r.request().url()).pathname.split("/").slice(-2)[0];
    counters.voids.push(startId);
    const record = startRecords.get(startId);
    if (!record) {
      return r.fulfill(json({ ok: false, error: { code: "programming_start_not_found", message: "no start with this ID is recorded" } }, 404));
    }
    if (record.state !== "ISSUED") {
      return r.fulfill(json({ ok: false, error: { code: "programming_start_not_voidable", message: "only a start that was never admitted can be voided" } }, 409));
    }
    record.state = "VOIDED";
    pendingBatchStarts.delete(startId);
    await r.fulfill(json({ ok: true, reconciliation: reconciliation(record.alias ?? null, startId) }));
  });
  return counters;
}

/** No request may ever reach a PPU Gateway relay, the Mock provider or the Batch runtime. */
export function legacyRequests(counters: Counters): string[] {
  return counters.requests.filter(entry =>
    /\/api\/manager\/ppu\/|\/api\/engineering\/|\/api\/jobs|\/api\/batches|\/api\/status|\/api\/programming-assets/.test(entry));
}
