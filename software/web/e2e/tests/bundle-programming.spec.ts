import { expect, test, type Page, type Route } from "@playwright/test";

// Host-only Console UI acceptance for Console-driven Bundle programming.
// The Manager BFF is mocked at the Browser boundary (Mock PPU / Fake Provider).
// This proves Console behaviour only; it is NOT physical E2E evidence.

const ALIAS = "z2";
const FIRMWARE = Buffer.from(Array.from({ length: 4096 }, (_, i) => i % 251));
const BUNDLE_SHA = "a".repeat(64);
const IMAGE_SHA = "f".repeat(64);
const RUN_ID = "d".repeat(32);
const RESOURCE_SHA = "9".repeat(64);
const BINDING_SHA = "8".repeat(64);
const ACTIVE_SET_SHA = "b".repeat(64);
const short = (sha: string) => `${sha.slice(0, 12)}…`;

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
  route_id: "z2-site2-stm32f103c8t6", target: { platform: "linux-armv7", board: "pynq-z2", fpga_part: "xc7z020clg400-1" },
  icpn: "STM32F103C8T6", site_interface: "openocd", provider: "openocd-platform-reference", profile: "stm32f103c8t6-site2",
  operations: ["flash_cycle"], driver_abi: "plasma_swd:5", transport: "fpga", max_image_bytes: 65536,
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

function plan(activationRequired: boolean) {
  return {
    plan_id: "e".repeat(32), ppu_alias: ALIAS, site_id: 2, operation: "flash_cycle", route,
    bundle: { archive_sha256: BUNDLE_SHA, archive_size: 5000, bundle_name: "stm32f103c8t6-site2-img-ffffffffffff",
      provider: route.provider, profile: route.profile, asset_package_id: "img-ffffffffffffffff",
      image_filename: "app.bin", image_sha256: IMAGE_SHA, image_size: FIRMWARE.length, icpn: route.icpn },
    resource: { resource_set_sha256: RESOURCE_SHA, reuse: !activationRequired,
      ppu_reported: { state: "VERIFIED", asset_set_sha256: ACTIVE_SET_SHA, generation: 3,
        resource_set_sha256: activationRequired ? "7".repeat(64) : RESOURCE_SHA } },
    image_asset: { image_asset_sha256: "6".repeat(64), sha256: IMAGE_SHA, size: FIRMWARE.length,
      load_address: 134217728, format: "binary" },
    job_binding: { operation: "flash_cycle", range: { address: 134217728, length: FIRMWARE.length },
      image_asset_sha256: "6".repeat(64), resource_set_sha256: RESOURCE_SHA },
    job_binding_sha256: BINDING_SHA,
    active_asset_set: { state: "ACTIVE", asset_set_sha256: ACTIVE_SET_SHA },
    activation_required: activationRequired, fpga_load: false,
    steps: [...(activationRequired ? ["B1_UPLOAD", "B2_ADMIT", "B3_ACTIVATE"] : ["RESOURCE_REUSE"]), "FLASH_CYCLE_JOB", "VERIFY_RECEIPT"],
    catalog_gate: "NOT_USED", confirm_required: "PROGRAM",
  };
}

type Outcome = "PASS" | "FAIL" | "OUTCOME_UNKNOWN";

// A Resource Reuse run never activates: no B1/B2/B3 step and an empty
// activation record, exactly as the Manager journals it.
function run(outcome: Outcome | null, reason: string | null = null, safeOff = true, reuse = false) {
  const steps = [
    { step: "PREFLIGHT", result: "PASS", at: "t" },
    ...(reuse
      ? [{ step: "RESOURCE_REUSE", result: "PPU_VERIFIED", at: "t", asset_set_sha256: ACTIVE_SET_SHA,
          resource_set_sha256: RESOURCE_SHA, generation: 3 }]
      : [
        { step: "B1_UPLOAD", result: "PASS", at: "t" },
        { step: "B2_ADMIT", result: "PASS", at: "t" },
        { step: "B3_ACTIVATE", result: "PASS", at: "t" },
      ]),
    { step: "FLASH_CYCLE_SUBMIT", result: "ACCEPTED", at: "t" },
  ];
  return {
    schema: "plasma.manager.bundle-programming-run.v1", run_id: RUN_ID, ppu_alias: ALIAS, site_id: 2,
    plan: {}, state: outcome ? "finished" : "running", outcome, reason, created_at: "t", updated_at: "t",
    steps: outcome === "PASS" ? [...steps, { step: "VERIFY_RECEIPT", result: "PASS", at: "t" }] : steps,
    activation: reuse ? {} : { b3_transaction_id: "c".repeat(32) },
    job: { job_id: "job-20261109-120000-0123abcd", state: outcome ? "success" : "running", progress_percent: outcome ? 100 : 40 },
    receipt: outcome && outcome !== "OUTCOME_UNKNOWN" ? {
      schema: "plasma.manager.programming-receipt.v2",
      job_id: "job-20261109-120000-0123abcd", job_state: "success", operation: "flash_cycle",
      site_id: 2, target: route.icpn, readback_sha256: IMAGE_SHA,
      expected_image_sha256: IMAGE_SHA, expected_image_size: FIRMWARE.length,
      observed_image_sha256: IMAGE_SHA, observed_image_size: FIRMWARE.length,
      bytes_verified: FIRMWARE.length,
      expected_resource_set_sha256: RESOURCE_SHA, observed_resource_set_sha256: RESOURCE_SHA,
      expected_job_binding_sha256: BINDING_SHA, observed_job_binding_sha256: BINDING_SHA,
      active_asset_set_sha256: reuse ? ACTIVE_SET_SHA : BUNDLE_SHA, resource_reuse: reuse,
      safe_off: safeOff, flash_result: "PASS", elapsed_ms: 10000,
    } : null,
    job_submission_count: 1, auto_retry: "DISABLED", acknowledged: false,
  };
}

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });

type Mocks = {
  planStatus?: number; planBody?: unknown; activationRequired?: boolean; routes?: unknown[];
  startStatus?: number; startBody?: unknown; final?: ReturnType<typeof run>;
};

async function mockManager(page: Page, mocks: Mocks = {}) {
  const counters = { plans: 0, starts: 0, polls: 0, acks: 0, planBodies: [] as Array<Record<string, unknown>>,
    startBodies: [] as Array<Record<string, unknown>> };
  // Default run records follow the plan: a reuse plan yields a reuse run.
  const reuse = mocks.activationRequired === false;
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
  await page.route(/\/bootstrap\/programming\/plans$/, async (r: Route) => {
    counters.plans += 1;
    counters.planBodies.push(r.request().postDataJSON());
    await r.fulfill(json(mocks.planBody ?? { ok: true, plan: plan(mocks.activationRequired ?? true) }, mocks.planStatus ?? 200));
  });
  await page.route(/\/bootstrap\/programming\/runs$/, async (r: Route) => {
    counters.starts += 1;
    counters.startBodies.push(r.request().postDataJSON());
    await r.fulfill(json(mocks.startBody ?? { ok: true, run: run(null, null, true, reuse) }, mocks.startStatus ?? 202));
  });
  await page.route(new RegExp(`/bootstrap/programming/runs/${RUN_ID}$`), async (r: Route) => {
    counters.polls += 1;
    await r.fulfill(json({ ok: true, run: counters.polls < 2
      ? run(null, null, true, reuse) : (mocks.final ?? run("PASS", null, true, reuse)) }));
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
  await page.goto("/engineering");
  await page.getByRole("button", { name: "PPU", exact: true }).click();
  await page.getByRole("button", { name: "Platform", exact: true }).click();
  const panel = page.getByRole("region", { name: "Bundle Programming" });
  await expect(panel).toBeVisible();
  await panel.getByLabel("Target IC").fill("STM32F103");
  await panel.getByRole("option", { name: /STM32F103C8T6/ }).click();
  await panel.getByLabel("Image file").setInputFiles({ name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE });
  await expect(panel.getByLabel("Programming Site")).toHaveValue("2");
  return panel;
}

test("User programs image: IC → image → PPU/Site → Bundle → B1/B2/B3 → flash_cycle → receipt", async ({ page }) => {
  const counters = await mockManager(page);
  const panel = await openAndSelect(page);
  await expect(panel.getByLabel("Programming Operation")).toHaveValue("flash_cycle");
  await panel.getByRole("button", { name: "Prepare Programming" }).click();
  await expect(panel.getByTestId("plan-resource-sha")).toHaveText(RESOURCE_SHA);
  await expect(panel.getByTestId("plan-operation")).toHaveText("flash_cycle");
  await expect(panel.getByTestId("plan-activation")).toContainText("B3 activate Bundle");
  await expect(panel.getByTestId("plan-activation")).toContainText("(no FPGA load)");
  const body = counters.planBodies[0];
  expect(body.icpn).toBe("STM32F103C8T6");
  expect(body.site_id).toBe(2);
  expect(body.operation).toBe("flash_cycle");
  expect(Buffer.from(String(body.image_base64), "base64").equals(FIRMWARE)).toBe(true);
  const start = panel.getByRole("button", { name: "Start Programming" });
  await expect(start).toBeDisabled(); // explicit confirmation required
  await panel.getByLabel("Confirm programming").check();
  await start.dblclick(); // a double click must still start exactly once
  await expect(panel.getByTestId("run-outcome")).toHaveText("PASS");
  await expect(panel.getByTestId("receipt-readback")).toHaveText(IMAGE_SHA);
  await expect(panel.getByTestId("receipt-bytes")).toHaveText(`${FIRMWARE.length} / ${FIRMWARE.length}`);
  await expect(panel.getByTestId("receipt-safe-off")).toHaveText("VERIFIED");
  expect(counters.starts).toBe(1);
});

test("Resource Reuse: same PPU-verified Resources → no B1/B2/B3 → one flash_cycle → Reused receipt", async ({ page }) => {
  const counters = await mockManager(page, { activationRequired: false });
  const panel = await openAndSelect(page);
  await panel.getByRole("button", { name: "Prepare Programming" }).click();

  // The plan the Console received: PPU-reported VERIFIED Resources equal to the Route's.
  const planned = plan(false);
  expect(planned.resource.reuse).toBe(true);
  expect(planned.resource.ppu_reported.state).toBe("VERIFIED");
  expect(planned.resource.ppu_reported.resource_set_sha256).toBe(planned.resource.resource_set_sha256);
  expect(planned.job_binding.resource_set_sha256).toBe(planned.resource.resource_set_sha256);

  // What the user sees before starting.
  await expect(panel.getByTestId("plan-resource-sha")).toHaveText(RESOURCE_SHA);
  const activation = panel.getByTestId("plan-activation");
  await expect(activation).toContainText("Not required");
  await expect(activation).toContainText("the PPU verified identical Programming Resources");
  await expect(activation).toContainText("no B1/B2/B3");
  await expect(activation).toContainText("no FPGA load");
  await expect(activation).not.toContainText("B1 upload");

  // Explicit confirmation gates Start; a double click still submits once.
  const start = panel.getByRole("button", { name: "Start Programming" });
  await expect(start).toBeDisabled();
  expect(counters.starts).toBe(0);
  await panel.getByLabel("Confirm programming").check();
  await expect(start).toBeEnabled();
  await start.dblclick();

  await expect(panel.getByTestId("run-outcome")).toHaveText("PASS");
  const steps = panel.getByRole("list", { name: "Programming steps" }).getByRole("listitem");
  await expect(steps).toHaveText([
    "PREFLIGHT: PASS", "RESOURCE_REUSE: PPU_VERIFIED", "FLASH_CYCLE_SUBMIT: ACCEPTED", "VERIFY_RECEIPT: PASS",
  ]);

  // Receipt: Reused Resources, the planned Binding, readback, bytes and SAFE_OFF.
  await expect(panel.getByTestId("receipt-resource")).toHaveText("Reused");
  await expect(panel.getByTestId("receipt-resource-sha")).toHaveText(RESOURCE_SHA);
  await expect(panel.getByTestId("receipt-binding-sha")).toHaveText(BINDING_SHA);
  const receipt = panel.getByLabel("Programming receipt");
  await expect(receipt).toContainText(`Job Binding SHA256${BINDING_SHA}`);
  await expect(panel.getByTestId("receipt-readback")).toHaveText(IMAGE_SHA);
  await expect(panel.getByTestId("receipt-bytes")).toHaveText(`${FIRMWARE.length} / ${FIRMWARE.length}`);
  await expect(panel.getByTestId("receipt-safe-off")).toHaveText("VERIFIED");

  // Exactly one plan and one start, bound to that plan; nothing is resubmitted.
  await page.waitForTimeout(1500);
  expect(counters.plans).toBe(1);
  expect(counters.starts).toBe(1);
  expect(counters.startBodies).toEqual([{ plan_id: planned.plan_id, confirm: "PROGRAM" }]);
});

test("Operation choice is limited to single-operation Jobs of the Route Profile; read sends a range, no image", async ({ page }) => {
  const wide = { ...route, operations: ["flash_cycle", "erase", "read"] };
  const counters = await mockManager(page, {
    routes: [wide],
    planStatus: 409,
    planBody: { ok: false, error: { code: "resource_activation_requires_image", message: "program an Image first" } },
  });
  const panel = await openAndSelectIc(page);
  const select = panel.getByLabel("Programming Operation");
  // erase / program / verify are steps of one programming Job (EMode), never a Job of their own.
  await expect(select.locator("option")).toHaveText(["flash_cycle", "read"]);
  await select.selectOption("read");
  await expect(panel.getByLabel("Image file")).toHaveCount(0);
  const prepare = panel.getByRole("button", { name: "Prepare Programming" });
  await expect(prepare).toBeDisabled();
  await panel.getByLabel("Range address").fill("0x08000000");
  await panel.getByLabel("Range length").fill("1024");
  await prepare.click();
  await expect(panel.getByRole("alert")).toContainText("program an Image first");
  const body = counters.planBodies[0];
  expect(body).toEqual({ icpn: "STM32F103C8T6", site_id: 2, operation: "read", address: 134217728, length: 1024 });
  expect(counters.starts).toBe(0);
});

test("Incompatible selection is rejected at planning and nothing starts", async ({ page }) => {
  const counters = await mockManager(page, {
    planStatus: 422, planBody: { ok: false, error: { code: "bundle_incompatible", message: "IMAGE_EXCEEDS_PROFILE_MAX_IMAGE" } },
  });
  const panel = await openAndSelect(page);
  await panel.getByRole("button", { name: "Prepare Programming" }).click();
  await expect(panel.getByRole("alert")).toContainText("IMAGE_EXCEEDS_PROFILE_MAX_IMAGE");
  await expect(panel.getByRole("button", { name: "Start Programming" })).toHaveCount(0);
  expect(counters.starts).toBe(0);
});

test("Missing Bundle plan and permission denial are surfaced without retry", async ({ page }) => {
  const counters = await mockManager(page, {
    startStatus: 404, startBody: { ok: false, error: { code: "programming_plan_not_found", message: "programming plan (Bundle) is missing or expired; prepare again" } },
  });
  const panel = await openAndSelect(page);
  await panel.getByRole("button", { name: "Prepare Programming" }).click();
  await panel.getByLabel("Confirm programming").check();
  await panel.getByRole("button", { name: "Start Programming" }).click();
  await expect(panel.getByRole("alert")).toContainText("missing or expired");
  expect(counters.starts).toBe(1);

  await page.unroute(/\/bootstrap\/programming\/plans$/);
  await page.route(/\/bootstrap\/programming\/plans$/, r => r.fulfill(json(
    { ok: false, error: { code: "maintenance_authorization_required", message: "Browser maintenance authorization is required" } }, 403)));
  await panel.getByRole("button", { name: "Prepare Programming" }).click();
  await expect(panel.getByRole("alert")).toContainText("maintenance authorization is required");
});

test("OUTCOME_UNKNOWN is shown, never resubmitted, and needs explicit acknowledgement", async ({ page }) => {
  const counters = await mockManager(page, { final: run("OUTCOME_UNKNOWN", "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT") });
  const panel = await openAndSelect(page);
  await panel.getByRole("button", { name: "Prepare Programming" }).click();
  await panel.getByLabel("Confirm programming").check();
  await panel.getByRole("button", { name: "Start Programming" }).click();
  await expect(panel.getByTestId("run-outcome")).toHaveText("OUTCOME UNKNOWN");
  await expect(panel.getByRole("alert")).toContainText("Nothing was resubmitted");
  await page.waitForTimeout(1500);
  expect(counters.starts).toBe(1);
  await panel.getByRole("button", { name: "Acknowledge reconciliation" }).click();
  await expect.poll(() => counters.acks).toBe(1);
  expect(counters.starts).toBe(1);
});

test("SAFE_OFF failure is a distinct FAIL", async ({ page }) => {
  await mockManager(page, { final: run("FAIL", "SAFE_OFF_NOT_VERIFIED", false) });
  const panel = await openAndSelect(page);
  await panel.getByRole("button", { name: "Prepare Programming" }).click();
  await panel.getByLabel("Confirm programming").check();
  await panel.getByRole("button", { name: "Start Programming" }).click();
  await expect(panel.getByTestId("run-outcome")).toHaveText("FAIL");
  await expect(panel.getByTestId("run-reason")).toHaveText("Reason: SAFE_OFF_NOT_VERIFIED");
  await expect(panel.getByTestId("receipt-safe-off")).toHaveText("NOT VERIFIED");
});

test("Manager HTTP timeout on run status keeps the run unresolved and never resubmits", async ({ page }) => {
  const counters = await mockManager(page);
  await page.route(new RegExp(`/bootstrap/programming/runs/${RUN_ID}$`), r => r.fulfill(json(
    { ok: false, error: { code: "manager_unavailable", message: "Manager Bootstrap path is unavailable" } }, 503)));
  const panel = await openAndSelect(page);
  await panel.getByRole("button", { name: "Prepare Programming" }).click();
  await panel.getByLabel("Confirm programming").check();
  await panel.getByRole("button", { name: "Start Programming" }).click();
  await expect(panel.getByRole("alert")).toContainText("Manager Bootstrap path is unavailable");
  await expect(panel.getByRole("button", { name: "Prepare Programming" })).toBeDisabled();
  expect(counters.starts).toBe(1);
});
