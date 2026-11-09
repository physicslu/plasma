import { expect, test, type Page, type Route } from "@playwright/test";

// Host-only Console UI acceptance for Console-driven Bundle programming.
// The Manager BFF is mocked at the Browser boundary (Mock PPU / Fake Provider).
// This proves Console behaviour only; it is NOT physical E2E evidence.

const ALIAS = "z2";
const FIRMWARE = Buffer.from(Array.from({ length: 4096 }, (_, i) => i % 251));
const BUNDLE_SHA = "a".repeat(64);
const IMAGE_SHA = "f".repeat(64);
const RUN_ID = "d".repeat(32);

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
  icpn: "STM32F103C8T6", sites: [2], provider: "openocd-platform-reference", profile: "stm32f103c8t6-site2",
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
    plan_id: "e".repeat(32), ppu_alias: ALIAS, site_id: 2, route,
    bundle: { archive_sha256: BUNDLE_SHA, archive_size: 5000, bundle_name: "stm32f103c8t6-site2-img-ffffffffffff",
      provider: route.provider, profile: route.profile, asset_package_id: "img-ffffffffffffffff",
      image_filename: "app.bin", image_sha256: IMAGE_SHA, image_size: FIRMWARE.length, icpn: route.icpn },
    active_asset_set: { state: "ACTIVE", asset_set_sha256: activationRequired ? "b".repeat(64) : BUNDLE_SHA },
    activation_required: activationRequired, fpga_load: false,
    steps: [...(activationRequired ? ["B1_UPLOAD", "B2_ADMIT", "B3_ACTIVATE"] : []), "FLASH_CYCLE_JOB", "VERIFY_RECEIPT"],
    catalog_gate: "NOT_USED", confirm_required: "PROGRAM",
  };
}

type Outcome = "PASS" | "FAIL" | "OUTCOME_UNKNOWN";

function run(outcome: Outcome | null, reason: string | null = null, safeOff = true) {
  const steps = [
    { step: "PREFLIGHT", result: "PASS", at: "t" },
    { step: "B1_UPLOAD", result: "PASS", at: "t" },
    { step: "B2_ADMIT", result: "PASS", at: "t" },
    { step: "B3_ACTIVATE", result: "PASS", at: "t" },
    { step: "FLASH_CYCLE_SUBMIT", result: "ACCEPTED", at: "t" },
  ];
  return {
    schema: "plasma.manager.bundle-programming-run.v1", run_id: RUN_ID, ppu_alias: ALIAS, site_id: 2,
    plan: {}, state: outcome ? "finished" : "running", outcome, reason, created_at: "t", updated_at: "t",
    steps: outcome === "PASS" ? [...steps, { step: "VERIFY_RECEIPT", result: "PASS", at: "t" }] : steps,
    activation: { b3_transaction_id: "c".repeat(32) },
    job: { job_id: "job-20261109-120000-0123abcd", state: outcome ? "success" : "running", progress_percent: outcome ? 100 : 40 },
    receipt: outcome && outcome !== "OUTCOME_UNKNOWN" ? {
      job_id: "job-20261109-120000-0123abcd", job_state: "success", readback_sha256: IMAGE_SHA,
      image_sha256: IMAGE_SHA, image_size: FIRMWARE.length, bytes_verified: FIRMWARE.length,
      safe_off: safeOff, flash_result: "PASS", asset_set_sha256: BUNDLE_SHA, elapsed_ms: 10000,
    } : null,
    job_submission_count: 1, auto_retry: "DISABLED", acknowledged: false,
  };
}

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });

type Mocks = {
  planStatus?: number; planBody?: unknown; activationRequired?: boolean;
  startStatus?: number; startBody?: unknown; final?: ReturnType<typeof run>;
};

async function mockManager(page: Page, mocks: Mocks = {}) {
  const counters = { plans: 0, starts: 0, polls: 0, acks: 0, planBodies: [] as Array<Record<string, unknown>> };
  await page.route(/\/api\/manager\/registry$/, r => r.fulfill(json(registry)));
  await page.route(/\/api\/fleet$/, r => r.fulfill(json({ ok: true, contract_version: "1", ppus: [] })));
  await page.route(/\/api\/manager\/registry\/z2\/bootstrap$/, r => r.fulfill(json(bootstrapStatus)));
  await page.route(/\/api\/manager\/devices\/search\?/, r => r.fulfill(json({
    ok: true, scope: "customer_ic_selector", query: "STM32", levels: [1, 2, 3], catalog_size: 1,
    count: 1, total_count: 1, limit: 8, offset: 0, results: [device] })));
  await page.route(/\/bootstrap\/programming\/routes$/, r => r.fulfill(json({ ok: true, routes: [route] })));
  await page.route(/\/bootstrap\/programming\/plans$/, async (r: Route) => {
    counters.plans += 1;
    counters.planBodies.push(r.request().postDataJSON());
    await r.fulfill(json(mocks.planBody ?? { ok: true, plan: plan(mocks.activationRequired ?? true) }, mocks.planStatus ?? 200));
  });
  await page.route(/\/bootstrap\/programming\/runs$/, async (r: Route) => {
    counters.starts += 1;
    await r.fulfill(json(mocks.startBody ?? { ok: true, run: run(null) }, mocks.startStatus ?? 202));
  });
  await page.route(new RegExp(`/bootstrap/programming/runs/${RUN_ID}$`), async (r: Route) => {
    counters.polls += 1;
    await r.fulfill(json({ ok: true, run: counters.polls < 2 ? run(null) : (mocks.final ?? run("PASS")) }));
  });
  await page.route(new RegExp(`/bootstrap/programming/runs/${RUN_ID}/acknowledge$`), async (r: Route) => {
    counters.acks += 1;
    await r.fulfill(json({ ok: true, run: { ...(mocks.final ?? run("OUTCOME_UNKNOWN")), acknowledged: true } }));
  });
  return counters;
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
  await panel.getByRole("button", { name: "Prepare Bundle" }).click();
  await expect(panel.getByTestId("plan-bundle-sha")).toHaveText(BUNDLE_SHA);
  await expect(panel.getByTestId("plan-activation")).toContainText("B3 activate (no FPGA load)");
  const body = counters.planBodies[0];
  expect(body.icpn).toBe("STM32F103C8T6");
  expect(body.site_id).toBe(2);
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

test("Already-active Bundle skips activation in the plan", async ({ page }) => {
  await mockManager(page, { activationRequired: false });
  const panel = await openAndSelect(page);
  await panel.getByRole("button", { name: "Prepare Bundle" }).click();
  await expect(panel.getByTestId("plan-activation")).toContainText("Not required");
});

test("Incompatible selection is rejected at planning and nothing starts", async ({ page }) => {
  const counters = await mockManager(page, {
    planStatus: 422, planBody: { ok: false, error: { code: "bundle_incompatible", message: "IMAGE_EXCEEDS_PROFILE_MAX_IMAGE" } },
  });
  const panel = await openAndSelect(page);
  await panel.getByRole("button", { name: "Prepare Bundle" }).click();
  await expect(panel.getByRole("alert")).toContainText("IMAGE_EXCEEDS_PROFILE_MAX_IMAGE");
  await expect(panel.getByRole("button", { name: "Start Programming" })).toHaveCount(0);
  expect(counters.starts).toBe(0);
});

test("Missing Bundle plan and permission denial are surfaced without retry", async ({ page }) => {
  const counters = await mockManager(page, {
    startStatus: 404, startBody: { ok: false, error: { code: "programming_plan_not_found", message: "programming plan (Bundle) is missing or expired; prepare again" } },
  });
  const panel = await openAndSelect(page);
  await panel.getByRole("button", { name: "Prepare Bundle" }).click();
  await panel.getByLabel("Confirm programming").check();
  await panel.getByRole("button", { name: "Start Programming" }).click();
  await expect(panel.getByRole("alert")).toContainText("missing or expired");
  expect(counters.starts).toBe(1);

  await page.unroute(/\/bootstrap\/programming\/plans$/);
  await page.route(/\/bootstrap\/programming\/plans$/, r => r.fulfill(json(
    { ok: false, error: { code: "maintenance_authorization_required", message: "Browser maintenance authorization is required" } }, 403)));
  await panel.getByRole("button", { name: "Prepare Bundle" }).click();
  await expect(panel.getByRole("alert")).toContainText("maintenance authorization is required");
});

test("OUTCOME_UNKNOWN is shown, never resubmitted, and needs explicit acknowledgement", async ({ page }) => {
  const counters = await mockManager(page, { final: run("OUTCOME_UNKNOWN", "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT") });
  const panel = await openAndSelect(page);
  await panel.getByRole("button", { name: "Prepare Bundle" }).click();
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
  await panel.getByRole("button", { name: "Prepare Bundle" }).click();
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
  await panel.getByRole("button", { name: "Prepare Bundle" }).click();
  await panel.getByLabel("Confirm programming").check();
  await panel.getByRole("button", { name: "Start Programming" }).click();
  await expect(panel.getByRole("alert")).toContainText("Manager Bootstrap path is unavailable");
  await expect(panel.getByRole("button", { name: "Prepare Bundle" })).toBeDisabled();
  expect(counters.starts).toBe(1);
});
