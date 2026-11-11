import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import {
  BUNDLE, FIRMWARE, RESOURCE_SHA, Z2, flashBytes, legacyRequests, mockManager, operationsRoute, route,
  type Counters, type MockPpu,
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

async function configure(page: Page, source: "image" | "bundle" = "image") {
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

test("Image is the default Source; E / P / V are three checked, independent checkboxes; Repeat stays disabled", async ({ page }) => {
  await mockManager(page);
  const { job, start } = await configure(page);
  await expect(job.getByRole("radio", { name: "Programming Image", exact: true })).toHaveAttribute("aria-checked", "true");
  await expect(job.getByRole("radio", { name: "Bundle", exact: true })).toHaveAttribute("aria-checked", "false");
  const operations = job.locator("[data-programming-job-operation]");
  // Exactly E, P, V in the fixed order: no Read, no flash_cycle.
  expect(await operations.evaluateAll(nodes => nodes.map(node => node.getAttribute("data-programming-job-operation"))))
    .toEqual(["erase", "program", "verify"]);
  for (const name of ["erase", "program", "verify"]) {
    const box = job.getByLabel(`Engineering operation ${name}`);
    await expect(box).toBeChecked();
    await box.uncheck();
    await expect(box).not.toBeChecked();
    for (const other of ["erase", "program", "verify"].filter(item => item !== name)) {
      await expect(job.getByLabel(`Engineering operation ${other}`)).toBeChecked();
    }
    await box.check();
  }
  await expect(job.getByLabel("Repeat Count")).toBeDisabled();
  await expect(job.getByLabel("Repeat Count")).toHaveValue("1");
  await expect(job.locator('[data-programming-job-policy="note"]')).toContainText(/attempts = 1 · auto retry DISABLED/);
  await expect(job.locator('[data-programming-job-policy="note"]')).toContainText(/Repeat (固定為 1|is fixed at 1)/);
  await expect(page.getByRole("button", { name: "Prepare Programming" })).toHaveCount(0);
  await expect(start).toBeEnabled();
});

const COMBINATIONS: Array<{ uncheck: string[]; operations: string[]; image: boolean }> = [
  { uncheck: ["program", "verify"], operations: ["erase"], image: false },
  { uncheck: ["erase", "verify"], operations: ["program"], image: true },
  { uncheck: ["erase", "program"], operations: ["verify"], image: true },
  { uncheck: ["verify"], operations: ["erase", "program"], image: true },
  { uncheck: ["erase"], operations: ["program", "verify"], image: true },
  { uncheck: [], operations: ["erase", "program", "verify"], image: true },
];

for (const combination of COMBINATIONS) {
  test(`${combination.operations.join(" + ")} runs as ONE programming Job with exactly that operations list`, async ({ page }) => {
    const counters = await mockManager(page);
    const workspace = await open(page);
    const job = await selectIc(page);
    await workspace.getByLabel("Select SITE 2 for programming").check();
    for (const name of combination.uncheck) await job.getByLabel(`Engineering operation ${name}`).uncheck();
    const start = job.getByRole("button", { name: /START PROGRAMMING/ });
    if (combination.image) {
      await expect(start).toBeDisabled(); // an Image is required exactly when P or V is selected
      await job.getByLabel("Engineering Programming Image file").setInputFiles(firmwareFile);
    }
    await expect(start).toBeEnabled();
    await start.dblclick();
    await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
    // One plan, one run, one Job: the list is sent as chosen, never as flash_cycle.
    expect(counters.plans).toHaveLength(1);
    expect(counters.starts).toHaveLength(1);
    const body = counters.plans[0].body;
    expect(body.operations).toEqual(combination.operations);
    expect(body).not.toHaveProperty("operation");
    if (combination.image) {
      expect(Buffer.from(String(body.image_base64), "base64").equals(FIRMWARE)).toBe(true);
      expect(body).not.toHaveProperty("address");
    } else {
      // Erase only: no Programming Image, the whole Flash range of the Profile.
      expect(body).not.toHaveProperty("image_base64");
      expect(body).not.toHaveProperty("bundle_base64");
      expect(body).toMatchObject({ address: 134217728, length: 65536 });
    }
    await expect(workspace.getByTestId("receipt-operations")).toContainText(combination.operations.join(" → "));
    await expect(workspace.getByTestId("receipt-operations")).toContainText("one Job");
    for (const name of combination.operations) {
      await expect(workspace.getByTestId(`receipt-step-${name}`)).toBeVisible();
    }
    for (const name of combination.uncheck) {
      await expect(workspace.getByTestId(`receipt-step-${name}`)).toHaveCount(0);
    }
    await expect(workspace.getByTestId("plan-operation")).toHaveText(combination.operations.join(" → "));
    await expect(workspace.getByTestId("run-policy")).toContainText("attempts 1 · auto retry DISABLED");
    expect(legacyRequests(counters)).toEqual([]);
  });
}

test("no Operation, or Erase + Verify without Program, never reaches the Manager", async ({ page }) => {
  const counters = await mockManager(page);
  const { workspace, job, start } = await configure(page);
  await job.getByLabel("Engineering operation program").uncheck();
  await expect(start).toBeDisabled();
  await expect(workspace.getByTestId("managed-readiness")).toContainText("OPERATIONS INVALID");
  await expect(workspace.getByTestId("managed-readiness")).toContainText("Erase + Verify without Program is not supported");
  await job.getByLabel("Engineering operation erase").uncheck();
  await job.getByLabel("Engineering operation verify").uncheck();
  await expect(start).toBeDisabled();
  await expect(workspace.getByTestId("managed-readiness")).toContainText("NO OP");
  expect(writes(counters)).toEqual([]);
});

test("an Operation no Programming Route declares is disabled, not a fake capability", async ({ page }) => {
  const counters = await mockManager(page, { routes: [route(), operationsRoute([2], ["program", "verify", "read"])] });
  const { workspace, job, start } = await configure(page);
  await expect(job.getByLabel("Engineering operation erase")).toBeDisabled();
  await expect(job.getByLabel("Engineering operation erase")).not.toBeChecked();
  await expect(job.getByLabel("Engineering operation program")).toBeChecked();
  await start.click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  expect(counters.plans[0].body.operations).toEqual(["program", "verify"]);
});

test("a deployment with only the legacy flash_cycle Route offers no E / P / V and no Read", async ({ page }) => {
  const counters = await mockManager(page, { routes: [route()] });
  const { workspace, job, start } = await configure(page);
  for (const name of ["erase", "program", "verify"]) {
    await expect(job.getByLabel(`Engineering operation ${name}`)).toBeDisabled();
  }
  await expect(start).toBeDisabled();
  await expect(workspace.getByTestId("managed-readiness")).toContainText("OPERATIONS UNAVAILABLE");
  await expect(workspace.getByRole("button", { name: "Read SITE 2 Flash" })).toHaveCount(0);
  expect(writes(counters)).toEqual([]);
});

test("the file picker shows the real name, size and format, truncates long names and can re-select", async ({ page }) => {
  await mockManager(page);
  const workspace = await open(page);
  const job = await selectIc(page);
  await workspace.getByLabel("Select SITE 2 for programming").check();
  const name = job.locator("[data-image-source]");
  const browse = job.locator(".programmingJobImageControl button");
  await expect(name).toContainText("Select programming image (.bin)");
  await expect(browse).toHaveText("Browse...");
  await expect(job.locator("[data-image-details]")).toHaveCount(0);
  const long = `${"very-long-customer-release-name-".repeat(8)}v1.2.3.bin`;
  await job.getByLabel("Engineering Programming Image file").setInputFiles({ ...firmwareFile, name: long });
  await expect(name).toHaveText(long);
  await expect(name).toHaveAttribute("title", long);
  await expect(name).toHaveAttribute("data-image-source", "user_image");
  await expect(job.locator("[data-image-details]")).toHaveText("4.0 KiB (4096 B) · Raw binary (.bin)");
  await expect(browse).toHaveText("Change...");
  // The long name is clipped inside its box: the layout does not grow.
  const control = await job.locator(".programmingJobImageControl").boundingBox();
  const field = await job.locator('[data-programming-job-field="image"]').boundingBox();
  expect(control!.x + control!.width).toBeLessThanOrEqual(field!.x + field!.width + 1);
  expect(await name.evaluate(node => node.scrollWidth > node.clientWidth)).toBe(true);
  // No local path is ever shown.
  await expect(job.locator('[data-programming-job-field="image"]')).not.toContainText(/[A-Za-z]:\\|\/home\/|fakepath/);
  await job.getByLabel("Engineering Programming Image file").setInputFiles({ ...firmwareFile, name: "second.bin", buffer: Buffer.alloc(10, 1) });
  await expect(name).toHaveText("second.bin");
  await expect(job.locator("[data-image-details]")).toHaveText("10 B · Raw binary (.bin)");
  await job.getByRole("radio", { name: "Bundle", exact: true }).click();
  await expect(job.locator("[data-image-details]")).toHaveCount(0);
  await job.getByLabel("Engineering Programming Bundle file").setInputFiles(bundleFile);
  await expect(name).toHaveText("customer-release.zip");
  await expect(job.locator("[data-image-details]")).toHaveText("5.9 KiB (6000 B) · Canonical Bundle v3 (.zip)");
});

// ------------------------------------------------------------------ READ (Site row)

type PickerMode = "save" | "cancel" | "none" | "write-fail";
type PickerProbe = { calls: Array<string | null>; saves: Array<{ name: string; bytes: number[] }> };

/**
 * Replace the native Save File Picker before the page loads: a real picker
 * would block a headless Browser. "none" removes it (Firefox / Safari).
 */
async function stubSavePicker(page: Page, mode: PickerMode) {
  await page.addInitScript(pickerMode => {
    const host = window as unknown as Record<string, unknown>;
    const probe: PickerProbe = { calls: [], saves: [] };
    host.__readPicker = probe;
    if (pickerMode === "none") {
      host.showSaveFilePicker = undefined;
      return;
    }
    host.showSaveFilePicker = async (options?: { suggestedName?: string }) => {
      probe.calls.push(options?.suggestedName ?? null);
      if (pickerMode === "cancel") throw new DOMException("The user aborted a request.", "AbortError");
      const chunks: number[] = [];
      return {
        name: "dump.bin",
        createWritable: async () => ({
          write: async (chunk: Blob) => {
            if (pickerMode === "write-fail") throw new Error("disk full");
            chunks.push(...new Uint8Array(await chunk.arrayBuffer()));
          },
          close: async () => { probe.saves.push({ name: "dump.bin", bytes: chunks }); },
        }),
      };
    };
  }, mode);
}

function pickerProbe(page: Page): Promise<PickerProbe> {
  return page.evaluate(() => (window as unknown as { __readPicker: PickerProbe }).__readPicker);
}

async function readSetup(page: Page, mode: PickerMode) {
  await stubSavePicker(page, mode);
  const workspace = await open(page);
  await selectIc(page);
  return {
    workspace,
    button: workspace.getByRole("button", { name: "Read SITE 2 Flash" }),
    status: workspace.getByRole("status", { name: "SITE 2 Read status" }),
    save: workspace.getByRole("link", { name: "Save SITE 2 Read binary" }),
    log: workspace.getByLabel("Engineering job log"),
  };
}

const FULL_FLASH = flashBytes(0x08000000, 65536);

test("READ sits on the qualified Site row, reads the whole Flash and writes the verified bytes to the chosen file", async ({ page }) => {
  const counters = await mockManager(page);
  const { workspace, button, status, save, log } = await readSetup(page, "save");
  // No standalone READ MEMORY block, no Address / Length inputs, not an Operation.
  await expect(workspace.getByTestId("read-memory")).toHaveCount(0);
  await expect(workspace.getByText("READ MEMORY")).toHaveCount(0);
  await expect(workspace.getByLabel("Read Memory Start Address")).toHaveCount(0);
  await expect(workspace.getByLabel("Read Memory Length")).toHaveCount(0);
  await expect(workspace.locator('[data-programming-job-operation="read"]')).toHaveCount(0);
  // One button per Site whose Programming Route declares Read; it lives in LIVE SITE STATUS.
  const live = workspace.getByRole("region", { name: "Engineering Site selection" });
  await expect(live.getByRole("button", { name: /^Read SITE \d+ Flash$/ })).toHaveCount(1);
  // READ needs neither a Programming Image nor the Batch Site checkbox.
  await expect(workspace.getByLabel("Select SITE 2 for programming")).not.toBeChecked();
  await expect(button).toBeEnabled();
  await expect(button).toHaveText("READ");
  await button.dblclick();
  await expect(status).toHaveText("PASS");
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  // Flash Base and Flash Size of the Programming Route: the whole Flash.
  expect(counters.plans[0].body).toEqual({ icpn: "STM32F103C8T6", site_id: 2, operation: "read", address: 0x08000000, length: 65536 });
  const probe = await pickerProbe(page);
  expect(probe.calls).toEqual(["read-STM32F103C8T6-z2-site2.bin"]);
  expect(probe.saves).toHaveLength(1);
  expect(Buffer.from(probe.saves[0].bytes).equals(FULL_FLASH)).toBe(true);
  expect(counters.downloads).toHaveLength(1);
  await expect(save).toHaveCount(0);
  // The row stays short; the evidence is in the Log.
  await expect(workspace.getByTestId("site-read-2")).toHaveText("READPASS");
  const digest = createHash("sha256").update(FULL_FLASH).digest("hex");
  await expect(log).toContainText(`[READ] SAVED · SITE-02 · dump.bin · 65536 B · SHA256 ${digest}`);
  await expect(log).toContainText(/\[READ\] PASS · SITE-02 · Run \S+ · Job \S+ · SAFE_OFF VERIFIED/);
  // Not a Batch: no Batch run, no PASS / FAIL / Yield, no E / P / V Site result.
  await expect(workspace.getByTestId("run-outcome")).toHaveCount(0);
  await expect(workspace.getByTestId("batch-attempts")).toHaveCount(0);
  expect(counters.batches).toHaveLength(0);
  const summary = page.getByRole("region", { name: "Engineering Batch Summary" });
  await expect(summary).toContainText("Run Preview");
  await expect(summary).not.toContainText("100.0%");
  await expect(live.locator("tr", { hasText: "SITE-02" }).locator(".engineeringResult")).toHaveText("—");
  // The Browser reached the Manager only; never a PPU.
  expect(legacyRequests(counters)).toEqual([]);
});

test("cancelling the Save File Picker submits no READ Job", async ({ page }) => {
  const counters = await mockManager(page);
  const { button, status, log } = await readSetup(page, "cancel");
  await button.click();
  await expect(log).toContainText("[READ] CANCELLED · SITE-02 · no file was chosen · no Job was submitted");
  await expect(button).toBeEnabled();
  await expect(button).toHaveText("READ");
  await expect(status).toHaveCount(0);
  expect((await pickerProbe(page)).calls).toHaveLength(1);
  expect(counters.plans).toEqual([]);
  expect(counters.starts).toEqual([]);
  expect(counters.downloads).toEqual([]);
  expect(writes(counters)).toEqual([]);
});

test("a READ failure, a SHA256 mismatch or an unknown outcome writes nothing and is never retried", async ({ page }) => {
  let mode = "fail";
  const counters = await mockManager(page, { script: () => mode === "fail" ? { outcome: "FAIL", reason: "SAFE_OFF_NOT_VERIFIED", safeOff: false }
    : mode === "tamper" ? { readTamper: true } : { outcome: "OUTCOME_UNKNOWN", reason: "JOB_STATUS_UNKNOWN_DO_NOT_RESUBMIT" } });
  const { workspace, button, status, save, log } = await readSetup(page, "save");
  await button.click();
  await expect(status).toHaveText("FAIL");
  await expect(status).toHaveAttribute("title", "SAFE_OFF_NOT_VERIFIED");
  await expect(log).toContainText("[READ] FAIL · SAFE_OFF_NOT_VERIFIED · SITE-02");
  await expect(save).toHaveCount(0);
  // The Manager says PASS but the bytes do not re-hash to the receipt SHA256.
  mode = "tamper";
  await button.click();
  await expect(status).toHaveText("FAIL");
  await expect(status).toHaveAttribute("title", /do not match the receipt SHA256/);
  await expect(log).toContainText("binary rejected: The downloaded bytes do not match the receipt SHA256.");
  await expect(save).toHaveCount(0);
  mode = "unknown";
  await button.click();
  await expect(status).toHaveText("OUTCOME UNKNOWN");
  await expect(save).toHaveCount(0);
  // An unknown READ is never resubmitted and locks the PPU like any unknown run.
  await expect(workspace.getByTestId("managed-unresolved")).toBeVisible();
  await expect(button).toBeDisabled();
  await expect(page.getByRole("button", { name: /START PROGRAMMING/ })).toBeDisabled();
  expect(counters.starts).toHaveLength(3);
  const probe = await pickerProbe(page);
  expect(probe.calls).toHaveLength(3);
  expect(probe.saves).toEqual([]);
  await expect(log).toContainText("[READ] SITE-02 · nothing was written to dump.bin");
});

test("without a Save File Picker the verified READ is offered through the Browser download", async ({ page }) => {
  const counters = await mockManager(page);
  const { button, status, save, log } = await readSetup(page, "none");
  await button.click();
  await expect(status).toHaveText("PASS");
  await expect(log).toContainText("this Browser has no Save File Picker · the verified binary will be offered as a download");
  await expect(save).toHaveAttribute("download", "read-STM32F103C8T6-0x08000000-65536.bin");
  const [download] = await Promise.all([page.waitForEvent("download"), save.click()]);
  expect((await readFile(await download.path())).equals(FULL_FLASH)).toBe(true);
  expect(counters.plans).toHaveLength(1);
  expect(counters.downloads).toHaveLength(1);
});

test("a verified READ that cannot be written to the chosen file is kept as a download", async ({ page }) => {
  await mockManager(page);
  const { button, status, save, log } = await readSetup(page, "write-fail");
  await button.click();
  await expect(status).toHaveText("SAVE FAILED");
  await expect(log).toContainText("[READ] SAVE FAILED · SITE-02 · dump.bin · disk full");
  const [download] = await Promise.all([page.waitForEvent("download"), save.click()]);
  expect((await readFile(await download.path())).equals(FULL_FLASH)).toBe(true);
  expect((await pickerProbe(page)).saves).toEqual([]);
});

test("READ is unavailable on a busy or disabled Site and absent where no Route declares Read", async ({ page }) => {
  // Site 2: Route + busy. Site 3: enabled, no Route. Site 4: Route, disabled on the PPU.
  const counters = await mockManager(page, {
    ppus: [{ ...Z2, enabledSites: [2, 3], busySites: [2] }],
    routes: [operationsRoute([2, 4])],
  });
  const { workspace, button } = await readSetup(page, "save");
  const live = workspace.getByRole("region", { name: "Engineering Site selection" });
  await expect(live.getByRole("button", { name: /^Read SITE \d+ Flash$/ })).toHaveCount(2);
  await expect(workspace.getByRole("button", { name: "Read SITE 3 Flash" })).toHaveCount(0);
  await expect(workspace.getByTestId("site-read-3")).toHaveText("—");
  await expect(button).toBeDisabled();
  await expect(button).toHaveAttribute("title", "The Site is busy or not idle.");
  const disabled = workspace.getByRole("button", { name: "Read SITE 4 Flash" });
  await expect(disabled).toBeDisabled();
  await expect(disabled).toHaveAttribute("title", "The Site is disabled on the PPU.");
  await button.click({ force: true });
  await disabled.click({ force: true });
  expect((await pickerProbe(page)).calls).toEqual([]);
  expect(writes(counters)).toEqual([]);
});

test("READ and a Batch run lock each other out and READ keeps the E / P / V result", async ({ page }) => {
  await stubSavePicker(page, "save");
  const counters = await mockManager(page, { script: () => ({ runningPolls: 4 }) });
  const { workspace, job, start } = await configure(page);
  const button = workspace.getByRole("button", { name: "Read SITE 2 Flash" });
  const result = workspace.locator('tr[data-site-selected="true"] .engineeringResult');
  await start.click();
  await expect(button).toBeDisabled(); // a programming run owns the Site
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS", { timeout: 20_000 });
  await expect(result).toHaveText("PASS");
  const summary = page.getByRole("region", { name: "Engineering Batch Summary" });
  await expect(summary).toContainText("100.0%");
  await button.click();
  await expect(button).toHaveText("READING");
  await expect(start).toBeDisabled(); // and a READ locks Start
  await expect(job.getByLabel("Engineering operation erase")).toBeDisabled();
  await expect(workspace.getByRole("status", { name: "SITE 2 Read status" })).toHaveText("PASS", { timeout: 20_000 });
  await expect(start).toBeEnabled();
  expect(counters.plans.map(plan => plan.body.operation ?? "programming")).toEqual(["programming", "read"]);
  // The READ did not disturb the Batch result or the Yield.
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  await expect(result).toHaveText("PASS");
  await expect(summary).toContainText("100.0%");
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
  expect(body.operations).toEqual(["erase", "program", "verify"]);
  expect(body).not.toHaveProperty("operation"); // E + P + V is never mapped to flash_cycle
  expect(Buffer.from(String(body.image_base64), "base64").equals(FIRMWARE)).toBe(true);
  expect(body).not.toHaveProperty("bundle_base64");
  expect(counters.starts[0].body).toEqual({ plan_id: expect.stringMatching(/^[0-9a-f]{32}$/), confirm: "PROGRAM" });
  // No standing PROGRAMMING PLAN panel; the Backend plan ran and its technical
  // result is in Receipts & Diagnostics and in the Log.
  await expect(workspace.getByTestId("managed-plan")).toHaveCount(0);
  await expect(workspace.getByLabel("Programming plan", { exact: true })).toHaveCount(0);
  await expect(workspace.locator("header").filter({ hasText: "PROGRAMMING PLAN" })).toHaveCount(0);
  const diagnostics = workspace.getByTestId("run-plan-diagnostics");
  await expect(diagnostics.getByTestId("plan-id")).toHaveText(/^[0-9a-f]{32}$/);
  await expect(diagnostics.getByTestId("plan-route")).toContainText("z2-site2-stm32f103c8t6-operations");
  await expect(diagnostics.getByTestId("plan-binding-sha")).toHaveText(/^z2-site2-plan1/);
  await expect(workspace.getByTestId("receipt-range")).toHaveText("0x08000000 + 4096 B");
  await expect(page.getByText(/\[PLAN\] .*Route z2-site2-stm32f103c8t6-operations/)).toHaveCount(1);
  await expect(page.getByText(/\[PLAN\] Range 0x08000000 \+ 4096 B · Resource SHA256 9{64}/)).toHaveCount(1);
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
  for (const step of ["B1_UPLOAD: PASS", "B2_ADMIT: PASS", "B3_ACTIVATE: PASS", "PROGRAMMING_SUBMIT: ACCEPTED", "VERIFY_RECEIPT: PASS"]) {
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
  const counters = await mockManager(page);
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

// ------------------------------------------------- Batch Policy: Retry / Stop

async function setPolicy(job: ReturnType<Page["getByRole"]>, retry: string, stop: "never" | "1" = "never") {
  await job.getByLabel("Site Retry Limit").fill(retry);
  await job.getByLabel("Engineering Stop Policy").selectOption(stop);
}

test("Batch Policy: Repeat stays 1 and disabled; Retry and Stop Policy are real, bounded controls", async ({ page }) => {
  const counters = await mockManager(page);
  const { workspace, job, start } = await configure(page);
  await expect(job.getByLabel("Repeat Count")).toBeDisabled();
  await expect(job.getByLabel("Repeat Count")).toHaveValue("1");
  const retry = job.getByLabel("Site Retry Limit");
  await expect(retry).toBeEnabled();
  await expect(retry).toHaveValue("0");
  await expect(retry).toHaveAttribute("max", "5");
  await retry.fill("99");
  await expect(retry).toHaveValue("5"); // clamped to the Manager limit
  await retry.fill("2");
  const stop = job.getByLabel("Engineering Stop Policy");
  await expect(stop).toBeEnabled();
  expect(await stop.locator("option").allTextContents()).toEqual(["Never", "1 failed Site"]);
  await stop.selectOption("1");
  // The button is "stop queuing", never an abort of a hardware Job.
  await expect(job.getByRole("button", { name: /ABORT/ })).toHaveCount(0);
  await expect(job.getByRole("button", { name: /STOP QUEUING/ })).toBeDisabled();
  await expect(job.locator('[data-programming-job-policy="note"]')).toContainText(/OUTCOME UNKNOWN (永不重送|is never resubmitted)/);
  await start.click();
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  expect(counters.batches).toHaveLength(1);
  expect(counters.batches[0].body).toMatchObject({
    repeat: 1, retry_limit: 2, stop_policy: { kind: "failed_sites", threshold: 1 },
    operations: ["erase", "program", "verify"],
  });
  await expect(workspace.getByTestId("batch-policy")).toContainText("Repeat 1 · Retry limit 2 · Stop Policy 1 failed Site");
  // PASS on the first attempt: one Job, no retry.
  expect(counters.jobs).toHaveLength(1);
});

test("a definite FAIL is retried by the Manager with a new plan, run and Job; the Batch counts once", async ({ page }) => {
  const counters = await mockManager(page, {
    script: (_alias, _site, attempt) => attempt === 1 ? { outcome: "FAIL", reason: "VERIFY_EVIDENCE_MISMATCH", readbackOk: false } : {},
  });
  const { workspace, job, start } = await configure(page);
  await setPolicy(job, "2");
  await start.dblclick();
  await expect(workspace.getByTestId("batch-result")).toContainText("Batch PASS · 2 attempt(s) · counted once", { timeout: 20_000 });
  // Exactly one Batch request from the Browser; the Manager submitted two Jobs.
  expect(counters.batches).toHaveLength(1);
  expect(counters.jobs).toHaveLength(2);
  expect(new Set(counters.jobs).size).toBe(2);
  expect(new Set(counters.starts.map(item => item.body.plan_id)).size).toBe(2);
  const first = workspace.getByTestId("batch-attempt-1");
  const second = workspace.getByTestId("batch-attempt-2");
  await expect(first).toContainText("FAIL");
  await expect(first).toContainText("RETRY · DEFINITE_FAIL_SAFE_OFF_VERIFIED");
  await expect(first).toContainText("VERIFIED");
  await expect(second).toContainText("PASS");
  // One IC: PASS 1, FAIL 0, Yield 100 %; the failed attempt is not a FAIL IC.
  const summary = page.getByRole("region", { name: "Engineering Batch Summary" });
  await expect(summary).toContainText("100.0%");
  await expect(workspace.locator('tr[data-site-selected="true"] .engineeringResult')).toHaveText("PASS");
  await expect(workspace.getByTestId("run-outcome")).toHaveText("PASS");
  await expect(workspace.getByTestId("run-policy")).toContainText("attempts 1 · auto retry DISABLED");
  await expect(page.getByText(/\[ATTEMPT 1\] FAIL .* RETRY \(DEFINITE_FAIL_SAFE_OFF_VERIFIED\)/)).toHaveCount(1);
  expect(legacyRequests(counters)).toEqual([]);
});

test("the Retry limit bounds the attempts; an exhausted Batch is one FAIL", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ outcome: "FAIL", reason: "PROGRAMMING_NOT_PASS" }) });
  const { workspace, job, start } = await configure(page);
  await setPolicy(job, "1");
  await start.click();
  await expect(workspace.getByTestId("batch-result")).toContainText("Batch FAIL · RETRY_LIMIT_EXHAUSTED · 2 attempt(s)", { timeout: 20_000 });
  expect(counters.jobs).toHaveLength(2);
  const summary = page.getByRole("region", { name: "Engineering Batch Summary" });
  await expect(summary).toContainText("0.0%");
  await expect(workspace.locator('tr[data-site-selected="true"] .engineeringResult')).toHaveText("FAIL");
});

test("OUTCOME UNKNOWN is never retried, whatever the Retry limit, and stays latched", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ outcome: "OUTCOME_UNKNOWN", reason: "JOB_STATUS_UNKNOWN_DO_NOT_RESUBMIT" }) });
  const { workspace, job, start } = await configure(page);
  await setPolicy(job, "5");
  await start.click();
  await expect(workspace.getByTestId("batch-result")).toContainText("Batch OUTCOME UNKNOWN · JOB_STATUS_UNKNOWN_DO_NOT_RESUBMIT · 1 attempt(s)");
  expect(counters.jobs).toHaveLength(1);
  await expect(workspace.getByTestId("batch-attempt-1")).toContainText("—"); // no retry decision
  await expect(workspace.getByTestId("managed-unresolved")).toBeVisible();
  await expect(start).toBeDisabled();
  await expect(workspace.getByTestId("managed-readiness")).toContainText("OUTCOME UNKNOWN");
});

test("a FAIL without verified SAFE_OFF is not retried", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ outcome: "FAIL", reason: "SAFE_OFF_NOT_VERIFIED", safeOff: false }) });
  const { workspace, job, start } = await configure(page);
  await setPolicy(job, "3");
  await start.click();
  await expect(workspace.getByTestId("batch-result")).toContainText("RETRY_NOT_ELIGIBLE_SAFE_OFF_NOT_VERIFIED · 1 attempt(s)");
  await expect(workspace.getByTestId("batch-attempt-1")).toContainText("NO RETRY · SAFE_OFF_NOT_VERIFIED");
  await expect(workspace.getByTestId("batch-attempt-1")).toContainText("NOT VERIFIED");
  expect(counters.jobs).toHaveLength(1);
});

test("Stop Policy '1 failed Site' stops queuing after the first FAIL even with retries left", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ outcome: "FAIL", reason: "PROGRAMMING_NOT_PASS" }) });
  const { workspace, job, start } = await configure(page);
  await setPolicy(job, "3", "1");
  await start.click();
  await expect(workspace.getByTestId("batch-result")).toContainText("STOP_POLICY_FAILED_SITES_THRESHOLD_REACHED · 1 attempt(s)");
  expect(counters.jobs).toHaveLength(1);
});

test("STOP QUEUING only stops unsubmitted attempts: the running Job is observed to its end, never cancelled", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ outcome: "FAIL", reason: "PROGRAMMING_NOT_PASS", runningPolls: 4 }) });
  const { workspace, job, start } = await configure(page);
  await setPolicy(job, "3");
  await start.click();
  const stop = job.getByRole("button", { name: /STOP QUEUING/ });
  await expect(stop).toBeEnabled();
  await stop.click();
  await expect(job.getByRole("button", { name: /STOP REQUESTED/ })).toBeDisabled();
  // The submitted Job is still running and is reported as running, not cancelled.
  await expect(workspace.getByTestId("batch-attempt-1")).toContainText("RUNNING");
  await expect(workspace.getByTestId("batch-policy")).toContainText("stop queuing requested");
  await expect(workspace.getByTestId("batch-result")).toContainText("Batch FAIL · STOP_REQUESTED_NO_FURTHER_ATTEMPT · 1 attempt(s)", { timeout: 20_000 });
  await expect(workspace.getByTestId("batch-attempt-1")).toContainText("FAIL"); // its real result
  expect(counters.jobs).toHaveLength(1);
  expect(counters.stops).toEqual([JSON.stringify({ stop: "STOP_QUEUING" })]);
  // No cancel / abort / reset / recovery request ever left the Browser.
  expect(counters.mutations.filter(entry => /cancel|abort|reset|recovery|lease/i.test(entry))).toEqual([]);
  await expect(page.getByText(/\[STOP QUEUING\] .* the running Job is not cancelled/)).toHaveCount(1);
});

test("a lost Batch response is OUTCOME UNKNOWN: the Browser never resends it", async ({ page }) => {
  const counters = await mockManager(page, { batchStatus: 504 });
  const { workspace, job, start } = await configure(page);
  await setPolicy(job, "3");
  await start.click();
  await expect(workspace.getByTestId("managed-start-unknown")).toContainText("The Batch request outcome is unknown");
  await expect(workspace.getByTestId("managed-start-unknown")).toContainText("Nothing was resubmitted");
  expect(counters.batches).toHaveLength(1);
  expect(counters.polls).toBe(0);
});

test("READ ignores the Batch Policy: one Job, no Batch, no retry", async ({ page }) => {
  await stubSavePicker(page, "save");
  const counters = await mockManager(page, { script: () => ({ outcome: "FAIL", reason: "READ_NOT_PASS" }) });
  const { workspace, job } = await configure(page);
  await setPolicy(job, "5");
  await workspace.getByRole("button", { name: "Read SITE 2 Flash" }).click();
  const status = workspace.getByRole("status", { name: "SITE 2 Read status" });
  await expect(status).toHaveText("FAIL");
  await expect(status).toHaveAttribute("title", "READ_NOT_PASS");
  expect(counters.batches).toHaveLength(0);
  expect(counters.starts).toHaveLength(1);
  await expect(workspace.getByTestId("batch-attempts")).toHaveCount(0);
  await expect(workspace.locator('tr[data-site-selected="true"] .engineeringResult')).toHaveText("—");
});
