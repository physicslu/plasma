import { expect, test, type Page } from "@playwright/test";
import {
  BUNDLE, FIRMWARE, RESOURCE_SHA, Z2, legacyRequests, mockManager, route, type Counters, type MockPpu,
} from "./managed-programming-helpers";

// Host-only Console acceptance of EMode → Programming (Single PPU) on the
// formal Manager backend. Mock Manager / Mock PPU / Fake Provider at the
// Browser boundary: NOT physical PPU, FPGA or DUT evidence.

const firmwareFile = { name: "app.bin", mimeType: "application/octet-stream", buffer: FIRMWARE };
const bundleFile = { name: "customer-release.zip", mimeType: "application/zip", buffer: BUNDLE };

async function open(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: /Programming|燒錄/ }).first().click();
  const workspace = page.locator('[data-programming-backend="manager"]');
  await expect(workspace).toBeVisible();
  await expect(workspace.getByTestId("managed-backend")).toContainText("ONLINE");
  return workspace;
}

async function selectIc(page: Page) {
  const job = page.getByRole("region", { name: "Engineering Programming Job" });
  await job.getByPlaceholder("Search ICPN / IC identifier...").fill("STM32F103");
  await job.getByRole("option", { name: /STM32F103C8T6/ }).click();
  return job;
}

async function configure(page: Page, source: "image" | "bundle" = "firmware") {
  const workspace = await open(page);
  const job = await selectIc(page);
  await workspace.getByLabel("Select SITE 2 for programming").check();
  if (source === "bundle") {
    await job.getByRole("radio", { name: "Bundle", exact: true }).click();
    await job.getByLabel("Engineering Programming Bundle file").setInputFiles(bundleFile);
  } else {
    await job.getByLabel("Engineering Programming Image file").setInputFiles(firmwareFile);
  }
  return { workspace, job, start: job.getByRole("button", { name: /START PROGRAMMING/ }) };
}

function writes(counters: Counters) {
  return counters.mutations.filter(entry => !entry.endsWith("/api/manager/ppu"));
}

test("topology comes from Manager Registry / Fleet / Routes; Alias and PPU ID stay distinct", async ({ page }) => {
  const counters = await mockManager(page, { ppus: [Z2, { alias: "bench", ppuId: "bench-01", facilityId: "lab", enabledSites: [1] }] });
  const workspace = await open(page);
  await expect(workspace.getByLabel("Engineering Facility")).toHaveValue("lab");
  await expect(workspace.getByLabel("Engineering PPU", { exact: true })).toHaveValue("z2");
  await expect(workspace.getByLabel("Engineering PPU", { exact: true }).locator("option")).toHaveCount(2);
  const foot = workspace.getByLabel("Selected Engineering PPU");
  await expect(foot).toContainText("Manager Alias: z2");
  await expect(foot).toContainText("PPU ID: z2-hil");
  await expect(foot).toContainText("8 Sites");
  await expect(foot).toContainText("PPU ONLINE");
  await expect(foot).toContainText("1 Facilities | 2 PPUs | 16 Sites");
  await expect(workspace.locator("tbody tr")).toHaveCount(8);
  // Nothing is offered before an IC is chosen; then only the Route's Site.
  await expect(workspace.locator('tr[data-site-programmable="true"]')).toHaveCount(0);
  await selectIc(page);
  await expect(workspace.locator('tr[data-site-programmable="true"]')).toHaveCount(1);
  await expect(workspace.getByLabel("Select SITE 2 for programming")).toBeEnabled();
  await expect(workspace.getByLabel("Select SITE 1 for programming")).toBeDisabled();
  expect(legacyRequests(counters)).toEqual([]);
  expect(writes(counters)).toEqual([]);
});

test("Image is the default Source; only Route Operations are offered; legacy policies are disabled", async ({ page }) => {
  await mockManager(page);
  const { job, start } = await configure(page);
  await expect(job.getByRole("radio", { name: "Programming Image", exact: true })).toHaveAttribute("aria-checked", "true");
  await expect(job.getByRole("radio", { name: "Bundle", exact: true })).toHaveAttribute("aria-checked", "false");
  const operations = job.locator("[data-programming-job-operation]");
  await expect(operations).toHaveCount(1);
  await expect(operations).toHaveAttribute("data-programming-job-operation", "flash_cycle");
  await expect(operations).toBeChecked();
  await expect(job.getByLabel("Site Retry Limit")).toBeDisabled();
  await expect(job.getByLabel("Site Retry Limit")).toHaveValue("0");
  await expect(job.getByLabel("Repeat Count")).toBeDisabled();
  await expect(job.getByLabel("Repeat Count")).toHaveValue("1");
  await expect(job.getByLabel("Engineering Stop Policy")).toBeDisabled();
  await expect(job.locator('[data-programming-job-policy="note"]')).toContainText(/attempts = 1 · auto retry DISABLED/);
  await expect(job.getByRole("button", { name: /ABORT/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Prepare Programming" })).toHaveCount(0);
  await expect(start).toBeEnabled();
});

test("one Start plans and executes: Firmware Resource Reuse → one Job → PASS receipt", async ({ page }) => {
  const counters = await mockManager(page);
  const { workspace, start } = await configure(page);
  await start.dblclick(); // a double click still submits exactly one plan and one run
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  const body = counters.plans[0].body;
  expect(counters.plans[0].alias).toBe("z2");
  expect(body.icpn).toBe("STM32F103C8T6");
  expect(body.site_id).toBe(2);
  expect(body.operation).toBe("flash_cycle");
  expect(Buffer.from(String(body.image_base64), "base64").equals(FIRMWARE)).toBe(true);
  expect(body).not.toHaveProperty("bundle_base64");
  expect(counters.starts[0].body).toEqual({ plan_id: expect.stringMatching(/^[0-9a-f]{32}$/), confirm: "PROGRAM" });
  await expect(workspace.getByTestId("plan-source")).toHaveText("image");
  await expect(workspace.getByTestId("plan-activation")).toContainText("Resource Reuse");
  await expect(workspace.getByTestId("plan-resource-sha")).toHaveText(RESOURCE_SHA);
  await expect(workspace.getByRole("list", { name: "Programming steps" })).toContainText("RESOURCE_REUSE: PPU_VERIFIED");
  await expect(workspace.getByRole("list", { name: "Programming steps" })).not.toContainText("B1_UPLOAD");
  // Receipt: full identities, readback and SAFE_OFF.
  await expect(workspace.getByTestId("receipt-job")).toHaveText(/^job-z2-site2-/);
  await expect(workspace.getByTestId("receipt-readback")).toHaveText(/^[0-9a-f]{64}$/);
  await expect(workspace.getByTestId("receipt-resource")).toHaveText("Reused");
  await expect(workspace.getByTestId("receipt-resource-sha")).toHaveText(RESOURCE_SHA);
  await expect(workspace.getByTestId("receipt-binding-sha")).toHaveText(/^z2-site2-plan1/);
  await expect(workspace.getByTestId("receipt-safe-off")).toHaveText("VERIFIED");
  await expect(workspace.getByTestId("run-policy")).toContainText("attempts 1 · auto retry DISABLED");
  const row = workspace.locator('tr[data-site-selected="true"]');
  await expect(row.locator(".engineeringResult")).toHaveText("PASS");
  await expect(page.getByRole("region", { name: "Engineering Batch Summary" })).toContainText("100.0%");
  expect(legacyRequests(counters)).toEqual([]);
});

test("Firmware cache miss runs B1/B2/B3 through the Manager, then one Job", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ activationRequired: true }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  await expect(workspace.getByTestId("plan-activation")).toContainText("B1 upload → B2 admit → B3 activate (no FPGA load)");
  const steps = workspace.getByRole("list", { name: "Programming steps" });
  for (const step of ["B1_UPLOAD: PASS", "B2_ADMIT: PASS", "B3_ACTIVATE: PASS", "FLASH_CYCLE_SUBMIT: ACCEPTED", "VERIFY_RECEIPT: PASS"]) {
    await expect(steps).toContainText(step);
  }
  await expect(workspace.getByTestId("receipt-resource")).toHaveText("Activated");
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  // The Browser itself never uploads, admits or activates anything.
  expect(counters.mutations.filter(entry => /uploads|deployments/.test(entry))).toEqual([]);
});

test("switching Firmware ↔ Bundle clears file, plan and run state and creates no Job", async ({ page }) => {
  const counters = await mockManager(page);
  const { workspace, job, start } = await configure(page);
  await start.click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  const before = writes(counters).length;

  await job.getByRole("radio", { name: "Bundle", exact: true }).click();
  await expect(job.getByRole("radio", { name: "Bundle", exact: true })).toHaveAttribute("aria-checked", "true");
  await expect(job.getByRole("radio", { name: "Programming Image", exact: true })).toHaveAttribute("aria-checked", "false");
  await expect(job.locator("[data-image-source]")).toHaveAttribute("data-image-source", "none");
  await expect(job.locator("[data-image-source]")).toContainText("Select canonical Bundle v3");
  await expect(workspace.getByTestId("managed-plan")).toHaveCount(0);
  await expect(workspace.getByTestId("run-outcome")).toHaveCount(0);
  await expect(start).toBeDisabled();
  await expect(workspace.getByTestId("managed-readiness")).toContainText("BUNDLE REQUIRED");
  expect(await job.getByLabel("Engineering Programming Bundle file").evaluate(input => (input as HTMLInputElement).files?.length)).toBe(0);

  await job.getByRole("radio", { name: "Programming Image", exact: true }).click();
  await expect(workspace.getByTestId("managed-readiness")).toContainText("IMAGE REQUIRED");
  await expect(start).toBeDisabled();
  // Switching alone never plans, starts, deploys or flashes.
  expect(writes(counters).length).toBe(before);
});

test("Bundle Resource Reuse: the user's Bundle bytes go to the Manager unchanged → PASS", async ({ page }) => {
  const counters = await mockManager(page);
  const { workspace, start } = await configure(page, "bundle");
  await start.dblclick();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  const body = counters.plans[0].body;
  expect(Buffer.from(String(body.bundle_base64), "base64").equals(BUNDLE)).toBe(true);
  expect(body).not.toHaveProperty("image_base64");
  expect(body).not.toHaveProperty("image_filename");
  await expect(workspace.getByTestId("plan-source")).toHaveText("bundle");
  await expect(workspace.getByTestId("plan-activation")).toContainText("Resource Reuse");
  await expect(workspace.getByTestId("receipt-resource")).toHaveText("Reused");
  await expect(workspace.getByTestId("receipt-safe-off")).toHaveText("VERIFIED");
});

test("Bundle cache miss is admitted and activated by the Manager (B1/B2/B3) → PASS", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ activationRequired: true }) });
  const { workspace, start } = await configure(page, "bundle");
  await start.click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  await expect(workspace.getByRole("list", { name: "Programming steps" })).toContainText("B3_ACTIVATE: PASS");
  await expect(workspace.getByTestId("receipt-resource")).toHaveText("Activated");
  expect(counters.starts).toHaveLength(1);
});

test("incompatible Bundle fails closed: no run, no Job, exact reason", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({
    planError: { code: "bundle_resource_not_qualified", message: "BUNDLE_RESOURCE_NOT_ROUTE" } }) });
  const { workspace, start } = await configure(page, "bundle");
  await start.click();
  const blocked = workspace.getByTestId("managed-blocked");
  await expect(blocked).toContainText("no Job was submitted");
  await expect(blocked).toContainText("bundle_resource_not_qualified");
  await expect(blocked).toContainText("cannot replace hardware qualification");
  await expect(blocked).toContainText("BUNDLE_RESOURCE_NOT_ROUTE");
  await expect(workspace.getByTestId("run-outcome")).toHaveCount(0);
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(0);
});

test("Manager OUTCOME_UNKNOWN is never resubmitted and latches Start until acknowledged", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({
    outcome: "OUTCOME_UNKNOWN", reason: "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT" }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("OUTCOME UNKNOWN");
  await expect(workspace.getByTestId("run-reason")).toContainText("DO_NOT_RESUBMIT");
  await expect(workspace.getByTestId("managed-unresolved")).toContainText("Nothing was resubmitted");
  await expect(start).toBeDisabled();
  await expect(workspace.getByTestId("managed-readiness")).toContainText("OUTCOME UNKNOWN");
  await page.waitForTimeout(2500); // no background retry appears later
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  await workspace.getByTestId("managed-unresolved").getByRole("button", { name: "Acknowledge reconciliation" }).click();
  await expect(workspace.getByTestId("managed-unresolved")).toHaveCount(0);
  expect(counters.acks).toBe(1);
  expect(counters.starts).toHaveLength(1);
});

test("a lost start response (Manager timeout) is OUTCOME UNKNOWN and is not retried", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({
    startStatus: 504, startError: { code: "manager_unavailable", message: "Manager Bootstrap path is unavailable" } }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(workspace.getByTestId("managed-start-unknown")).toContainText("OUTCOME UNKNOWN");
  await expect(workspace.getByTestId("managed-start-unknown")).toContainText("Nothing was resubmitted");
  await page.waitForTimeout(2500);
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  expect(counters.polls).toBe(0);
});

test("SAFE_OFF not verified is never PASS, even if a run record claims PASS", async ({ page }) => {
  await mockManager(page, { script: () => ({ outcome: "FAIL", reason: "SAFE_OFF_NOT_VERIFIED", safeOff: false }) });
  const first = await configure(page);
  await first.start.click();
  await expect(first.workspace.getByTestId("run-outcome")).toHaveText("FAIL");
  await expect(first.workspace.getByTestId("run-reason")).toHaveText("Reason: SAFE_OFF_NOT_VERIFIED");
  await expect(first.workspace.getByTestId("receipt-safe-off")).toHaveText("NOT VERIFIED");
  await expect(first.workspace.locator('tr[data-site-selected="true"] .engineeringResult')).toHaveText("FAIL");
});

test("a PASS claim without verified SAFE_OFF in the receipt is shown as FAIL", async ({ page }) => {
  await mockManager(page, { script: () => ({ outcome: "PASS", safeOff: false }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("FAIL");
  await expect(workspace.getByTestId("run-reason")).toHaveText("Reason: SAFE_OFF_NOT_VERIFIED");
  await expect(page.getByRole("region", { name: "Engineering Batch Summary" })).toContainText("0.0%");
});

const blockedCases: Array<{ name: string; ppu: MockPpu; label: string; reason: RegExp }> = [
  { name: "Offline", ppu: { ...Z2, transport: "unreachable" }, label: "PPU OFFLINE", reason: /cannot reach this PPU Gateway/ },
  { name: "Degraded", ppu: { ...Z2, execution: "unavailable" }, label: "PPU DEGRADED", reason: /not ready for execution/ },
  { name: "Stale", ppu: { ...Z2, observation: "stale" }, label: "PPU STALE", reason: /stale/ },
  { name: "not authorized", ppu: { ...Z2, paired: false }, label: "NOT AUTHORIZED", reason: /nothing is enrolled or rotated automatically/ },
  { name: "Recovery Required", ppu: { ...Z2, deploymentState: "recovery_required" }, label: "RECOVERY REQUIRED", reason: /explicit recovery/ },
  { name: "Runtime not active", ppu: { ...Z2, runtimeState: "runtime_stopped" }, label: "RUNTIME NOT ACTIVE", reason: /runtime_stopped/ },
];

for (const item of blockedCases) {
  test(`selected PPU ${item.name}: exact reason shown and Start disabled without any write`, async ({ page }) => {
    const counters = await mockManager(page, { ppus: [item.ppu] });
    const workspace = await open(page);
    const readiness = workspace.getByTestId("managed-readiness");
    await expect(readiness).toContainText(item.label);
    await expect(readiness).toContainText(item.reason);
    await expect(page.getByRole("button", { name: /START PROGRAMMING/ })).toBeDisabled();
    await page.getByRole("button", { name: /START PROGRAMMING/ }).click({ force: true }).catch(() => {});
    expect(writes(counters)).toEqual([]);
    // Fixing the UI never enrolls, rotates a credential or takes over recovery.
    expect(counters.requests.filter(entry => /enrollment|recovery/.test(entry))).toEqual([]);
  });
}

test("Manager-side refusals at plan time submit no Job (Recovery / SEALED / busy)", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ planStatus: 409,
    planError: { code: "ppu_recovery_required", message: "PPU Active Asset Set requires explicit recovery" } }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(workspace.getByTestId("managed-blocked")).toContainText("ppu_recovery_required");
  await expect(workspace.getByTestId("managed-blocked")).toContainText("no Job was submitted");
  expect(counters.starts).toHaveLength(0);
});

test("a start refused by the Manager (unresolved OUTCOME_UNKNOWN latch) is a definite block, not a retry", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ startStatus: 409,
    startError: { code: "programming_outcome_unknown_unresolved", message: "run 00 ended OUTCOME_UNKNOWN; reconcile and acknowledge first" } }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(workspace.getByTestId("managed-blocked")).toContainText("programming_outcome_unknown_unresolved");
  expect(counters.starts).toHaveLength(1);
  expect(counters.polls).toBe(0);
});

test("incomplete or invalid settings never reach the Manager", async ({ page }) => {
  const counters = await mockManager(page, { routes: [route([2], ["flash_cycle"])] });
  const workspace = await open(page);
  const start = page.getByRole("button", { name: /START PROGRAMMING/ });
  await expect(workspace.getByTestId("managed-readiness")).toContainText("NO TARGET");
  const job = await selectIc(page);
  await expect(workspace.getByTestId("managed-readiness")).toContainText("NO SITE");
  await workspace.getByLabel("Select SITE 2 for programming").check();
  await expect(workspace.getByTestId("managed-readiness")).toContainText("IMAGE REQUIRED");
  await expect(start).toBeDisabled();
  await job.getByLabel("Engineering Programming Image file").setInputFiles({ name: "empty.bin", mimeType: "application/octet-stream", buffer: Buffer.alloc(0) });
  await expect(workspace.getByTestId("managed-readiness")).toContainText("FILE INVALID");
  await expect(start).toBeDisabled();
  expect(writes(counters)).toEqual([]);
});

test("Programming Routes unavailable is a capability fault, not PPU OFFLINE", async ({ page }) => {
  await mockManager(page, { routesStatus: 503 });
  const workspace = await open(page);
  await expect(workspace.getByLabel("Selected Engineering PPU")).toContainText("PPU ONLINE");
  await expect(workspace.getByTestId("managed-readiness")).toContainText("ROUTES UNAVAILABLE");
  await expect(workspace.getByTestId("managed-readiness")).toContainText("ROUTE_ROOT_UNAVAILABLE");
});

test("Manager Registry unreachable shows the backend offline instead of an empty silent list", async ({ page }) => {
  await mockManager(page, { registryStatus: 503 });
  await page.goto("/engineering");
  await page.getByRole("button", { name: /Programming|燒錄/ }).first().click();
  const workspace = page.locator('[data-programming-backend="manager"]');
  await expect(workspace.getByTestId("managed-backend")).toContainText("OFFLINE");
  await expect(workspace.getByTestId("managed-readiness")).toContainText("MANAGER OFFLINE");
  await expect(workspace.getByTestId("managed-readiness")).toContainText("Manager Registry unavailable");
});

test("Readback mismatch is FAIL, whether the Manager reports it or a PASS record carries a wrong readback", async ({ page }) => {
  await mockManager(page, { script: () => ({ outcome: "FAIL", reason: "READBACK_SHA256_MISMATCH", readbackOk: false }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("FAIL");
  await expect(workspace.getByTestId("run-reason")).toHaveText("Reason: READBACK_SHA256_MISMATCH");
  await expect(workspace.getByTestId("receipt-readback")).toHaveText("0".repeat(64));
  await expect(workspace.locator('tr[data-site-selected="true"] .engineeringResult')).toHaveText("FAIL");
});

test("a PASS record whose readback differs from the expected Image is shown as FAIL", async ({ page }) => {
  await mockManager(page, { script: () => ({ outcome: "PASS", readbackOk: false }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("FAIL");
  await expect(workspace.getByTestId("run-reason")).toHaveText("Reason: READBACK_SHA256_MISMATCH");
});

test("switching the Programming Source cannot bypass an unresolved OUTCOME_UNKNOWN lock", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ outcome: "OUTCOME_UNKNOWN", reason: "JOB_RESULT_UNKNOWN_DO_NOT_RESUBMIT" }) });
  const { workspace, job, start } = await configure(page);
  await start.click();
  await expect(workspace.getByTestId("managed-unresolved")).toBeVisible();
  await job.getByRole("radio", { name: "Bundle", exact: true }).click();
  await job.getByLabel("Engineering Programming Bundle file").setInputFiles(bundleFile);
  await expect(workspace.getByTestId("managed-unresolved")).toBeVisible();
  await expect(workspace.getByTestId("managed-readiness")).toContainText("OUTCOME UNKNOWN");
  await expect(start).toBeDisabled();
  await job.getByRole("radio", { name: "Programming Image", exact: true }).click();
  await expect(start).toBeDisabled();
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
});

test("the Mock-only Engineering provider answering 503 (real PPU Runtime) no longer affects the managed page", async ({ page }) => {
  const counters = await mockManager(page);
  let providerCalls = 0;
  await page.route("**/api/manager/ppu/api/engineering/**", async r => {
    providerCalls += 1;
    await r.fulfill({ status: 503, contentType: "application/json",
      body: JSON.stringify({ ok: false, provider: "unavailable", error: { message: "Engineering PPU provider is not enabled" } }) });
  });
  const { workspace, start } = await configure(page);
  await expect(workspace.locator("tbody tr")).toHaveCount(8);
  await expect(workspace.getByLabel("Selected Engineering PPU")).toContainText("PPU ID: z2-hil");
  await start.click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  expect(providerCalls).toBe(0);
  expect(legacyRequests(counters)).toEqual([]);
});

test("a run on a Mock Site is labelled a Mock result; a hardware-path Site is not", async ({ page }) => {
  await mockManager(page, { ppus: [{ ...Z2, siteInterface: "mock" }] });
  const mock = await configure(page);
  await mock.start.click();
  await expect(mock.workspace.getByTestId("run-outcome")).toHaveText("PASS");
  await expect(mock.workspace.getByTestId("run-evidence")).toHaveAttribute("data-run-evidence", "mock");
  await expect(mock.workspace.getByTestId("run-evidence")).toContainText("MOCK RESULT");
  await expect(mock.workspace.getByTestId("run-evidence")).toContainText("never a hardware qualification");
});

test("a run on an openocd Site reports its interface and carries no Mock label", async ({ page }) => {
  await mockManager(page);
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  await expect(workspace.getByTestId("run-evidence")).toHaveAttribute("data-run-evidence", "ppu");
  await expect(workspace.getByTestId("run-evidence")).toHaveText("Site interface: openocd");
});
