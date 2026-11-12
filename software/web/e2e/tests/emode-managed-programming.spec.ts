import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test, type Locator, type Page } from "@playwright/test";
import {
  BUNDLE, FIRMWARE, RESOURCE_SHA, Z2, flashBytes, legacyRequests, mockManager, operationsRoute, route,
  type Counters, type MockPpu,
} from "./managed-programming-helpers";

// Host-only Console acceptance of EMode → Programming (Single PPU) on the
// formal Manager backend. Mock Manager / Mock PPU / Fake Provider at the
// Browser boundary: NOT physical PPU, FPGA or DUT evidence.

// The Engineering Job Log is the only on-screen record of a Manager run: the
// BATCH ATTEMPTS table and the standing run view were removed from EMode.
const jobLog = (workspace: Locator) => workspace.getByLabel("Engineering job log");

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
    await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
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
    // The Log carries the planned list, the list the PPU ran and the policy.
    const operations = combination.operations.join(" → ");
    await expect(jobLog(workspace)).toContainText(`Operations ${operations} (one Job · PPU ran: ${operations})`);
    for (const name of combination.uncheck) {
      await expect(jobLog(workspace)).not.toContainText(`PPU ran: ${name}`);
    }
    await expect(jobLog(workspace)).toContainText(`· Operations ${operations}`);
    await expect(jobLog(workspace)).toContainText("attempts 1 · auto retry DISABLED");
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
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
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

type PickerMode = "save" | "cancel" | "deny" | "security" | "none" | "write-fail" | "opfs";
type PickerProbe = { calls: Array<string | null>; saves: Array<{ name: string; bytes: number[] }> };

/**
 * Replace the native Save File Picker before the page loads: a real picker
 * would block a headless Browser. "none" removes it (Firefox / Safari).
 * "opfs" returns a real Chromium FileSystemFileHandle (Origin Private File
 * System), so the write path runs on the Browser's own implementation. None of
 * these modes is an acceptance of the native picker dialog itself.
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
      if (pickerMode === "deny") throw new DOMException("The request is not allowed by the user agent.", "NotAllowedError");
      if (pickerMode === "security") throw new DOMException("Must be handling a user gesture.", "SecurityError");
      if (pickerMode === "opfs") {
        const root = await navigator.storage.getDirectory();
        return root.getFileHandle("dump.bin", { create: true });
      }
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
  await expect(jobLog(workspace)).not.toContainText("[RUN] ");
  await expect(jobLog(workspace)).not.toContainText("[ATTEMPT");
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

test("a refused Save File Picker (permission denied) submits no READ Job", async ({ page }) => {
  const counters = await mockManager(page);
  const { button, status, save, log } = await readSetup(page, "deny");
  await button.click();
  await expect(status).toHaveText("BLOCKED");
  await expect(status).toHaveAttribute("title", /Save File Picker was refused.*No Job was submitted/);
  await expect(log).toContainText("[READ] BLOCKED · SITE-02 · the Save File Picker was refused");
  await expect(save).toHaveCount(0);
  await expect(button).toBeEnabled();
  expect(counters.plans).toEqual([]);
  expect(writes(counters)).toEqual([]);
});

test("a Save File Picker the Browser blocks falls back to the Browser download", async ({ page }) => {
  const counters = await mockManager(page);
  const { button, status, save, log } = await readSetup(page, "security");
  await button.click();
  await expect(status).toHaveText("PASS");
  await expect(log).toContainText("this Browser blocks the Save File Picker here");
  const [download] = await Promise.all([page.waitForEvent("download"), save.click()]);
  expect((await readFile(await download.path())).equals(FULL_FLASH)).toBe(true);
  expect(counters.starts).toHaveLength(1);
});

test("the verified READ is written through a real Chromium FileSystemFileHandle", async ({ page }) => {
  await mockManager(page);
  const { button, status, log } = await readSetup(page, "opfs");
  await button.click();
  await expect(status).toHaveText("PASS");
  await expect(log).toContainText("[READ] SAVED · SITE-02 · dump.bin · 65536 B");
  const saved = await page.evaluate(async () => {
    const root = await navigator.storage.getDirectory();
    const file = await (await root.getFileHandle("dump.bin")).getFile();
    return Array.from(new Uint8Array(await file.arrayBuffer()));
  });
  expect(Buffer.from(saved).equals(FULL_FLASH)).toBe(true);
});

// The Start request never reached the Manager's admission (HTTP 504 before it).
const lostStart = { startStatus: 504, startError: { code: "manager_unavailable", message: "Manager Bootstrap path is unavailable" } };
const HOLD_KEY = "plasma.emode.start-outcome-unknown.v1";
const RECONCILE = "Reconcile Start with Manager";

function holdParts(workspace: Awaited<ReturnType<typeof open>>) {
  return {
    hold: workspace.getByTestId("managed-start-hold"),
    reconcile: workspace.getByRole("button", { name: RECONCILE }),
    step: workspace.getByTestId("managed-start-hold-step"),
    note: workspace.getByTestId("managed-status-note"),
    read: workspace.getByRole("button", { name: "Read SITE 2 Flash" }),
    log: workspace.getByLabel("Engineering job log"),
  };
}

test("a lost READ Start answer is OUTCOME UNKNOWN: no second Job, no Programming Start, held across a reload until the Manager reconciles it", async ({ page }) => {
  await stubSavePicker(page, "save");
  const counters = await mockManager(page, { script: () => lostStart });
  const { workspace, start } = await configure(page);
  const button = workspace.getByRole("button", { name: "Read SITE 2 Flash" });
  const status = workspace.getByRole("status", { name: "SITE 2 Read status" });
  const hold = workspace.getByTestId("managed-start-hold");
  await expect(start).toBeEnabled();
  await button.click();
  // Unknown, not FAIL; nothing written.
  await expect(status).toHaveText("OUTCOME UNKNOWN");
  await expect(hold).toContainText("the READ Start request on PPU z2 · SITE-02 got no answer");
  await expect(hold).toContainText("Nothing was resubmitted");
  // The hold names the Manager-issued start (the plan ID) it will reconcile.
  await expect(hold).toContainText(`reconciles Start ${"1".padStart(32, "0")}`);
  expect((await pickerProbe(page)).saves).toEqual([]);
  // The PPU is held: neither a second READ nor a Programming Start can be sent.
  await expect(button).toBeDisabled();
  await expect(start).toBeDisabled();
  await expect(workspace.getByTestId("managed-readiness")).toContainText("OUTCOME UNKNOWN");
  await button.click({ force: true });
  await start.click({ force: true });
  await page.waitForTimeout(2500);
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  expect(counters.batches).toHaveLength(0);
  expect(counters.polls).toBe(0);
  // Nothing is reconciled, voided or acknowledged on its own.
  expect(counters.reconciles).toEqual([]);
  // A reload does not drop the hold.
  const reloaded = await configure(page);
  const after = holdParts(reloaded.workspace);
  await expect(after.hold).toBeVisible();
  await expect(after.read).toBeDisabled();
  await expect(reloaded.start).toBeDisabled();
  // The Site is idle, yet that alone releases nothing: the Manager still holds
  // a startable plan, so a delayed Start request could still be admitted.
  await after.reconcile.click();
  await expect(after.note).toContainText("the Manager has not admitted this Start, but a delayed request still could be");
  await expect(after.hold).toBeVisible();
  await expect(after.read).toBeDisabled();
  expect(counters.voids).toEqual([]);
  // The operator voids the unstarted Start; only then is "never admitted" proven.
  await expect(after.step).toHaveText("Void the unstarted Start");
  await after.step.click();
  await expect(after.hold).toHaveCount(0);
  await expect(after.log).toContainText("voided on the Manager before admission");
  await expect(after.log).toContainText("the Manager proves the Start was never admitted (START_VOIDED_BEFORE_ADMISSION); no Job was submitted · SITE-02 idle, no Job");
  await expect(after.read).toBeEnabled();
  await expect(reloaded.start).toBeEnabled();
  expect(counters.voids).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  expect(counters.jobs).toEqual([]);
  expect(counters.acks).toBe(0);
});

test("a READ Start the Manager admitted whose answer was lost is reconciled to its real run: still running, then PASS", async ({ page }) => {
  await stubSavePicker(page, "save");
  const counters = await mockManager(page, { script: () => ({ startLost: true, runningPolls: 1 }) });
  const { workspace, start } = await configure(page);
  const parts = holdParts(workspace);
  await parts.read.click();
  await expect(parts.hold).toContainText("the READ Start request on PPU z2");
  // The Site reads idle in the Fleet, but the Manager says the Job is running.
  await parts.reconcile.click();
  await expect(parts.note).toContainText("the Manager admitted this Start and it is still running");
  await expect(parts.hold).toBeVisible();
  await expect(parts.step).toHaveCount(0);
  await expect(parts.read).toBeDisabled();
  await expect(start).toBeDisabled();
  // Later: the same run ended PASS. The hold is released against that run.
  await parts.reconcile.click();
  await expect(parts.hold).toHaveCount(0);
  await expect(parts.log).toContainText(/reconciled with the Manager · the Manager admitted this Start as Run [0-9a-f]{32} and it ended PASS/);
  await expect(parts.read).toBeEnabled();
  // Exactly one start was ever sent; reconciling created no Job, no ack, no void.
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  expect(counters.reconciles).toHaveLength(2);
  expect(counters.acks).toBe(0);
  expect(counters.voids).toEqual([]);
  // The lost READ wrote nothing: its bytes were never fetched or saved.
  expect((await pickerProbe(page)).saves).toEqual([]);
  expect(counters.downloads).toEqual([]);
});

test("a lost READ Start that ended FAIL on the Manager is released as FAIL, never as PASS or retried", async ({ page }) => {
  await stubSavePicker(page, "save");
  const counters = await mockManager(page, { script: () => ({ startLost: true, runningPolls: 0, outcome: "FAIL", reason: "READ_OUTPUT_INTEGRITY_MISMATCH" }) });
  const { workspace } = await configure(page);
  const parts = holdParts(workspace);
  await parts.read.click();
  await expect(parts.hold).toBeVisible();
  await parts.reconcile.click();
  await expect(parts.hold).toHaveCount(0);
  await expect(parts.log).toContainText("it ended FAIL (READ_OUTPUT_INTEGRITY_MISMATCH)");
  expect(counters.starts).toHaveLength(1);
  expect((await pickerProbe(page)).saves).toEqual([]);
});

test("a lost Start whose Manager run is OUTCOME UNKNOWN stays held until the operator acknowledges that run", async ({ page }) => {
  await stubSavePicker(page, "save");
  const counters = await mockManager(page, { script: () => ({
    startLost: true, runningPolls: 0, outcome: "OUTCOME_UNKNOWN", reason: "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT" }) });
  const { workspace, start } = await configure(page);
  const parts = holdParts(workspace);
  await parts.read.click();
  await expect(parts.hold).toBeVisible();
  // Reconciling any number of times acknowledges nothing and resubmits nothing.
  for (let i = 0; i < 3; i += 1) {
    await parts.reconcile.click();
    await expect(parts.note).toContainText("ended OUTCOME UNKNOWN (JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT) and is not acknowledged");
    await expect(parts.reconcile).toBeEnabled();
  }
  await expect(parts.hold).toBeVisible();
  await expect(parts.read).toBeDisabled();
  await expect(start).toBeDisabled();
  expect(counters.acks).toBe(0);
  expect(counters.starts).toHaveLength(1);
  // The explicit operator acknowledgement of THAT Manager run releases it.
  await expect(parts.step).toHaveText("Acknowledge Run reconciliation");
  await parts.step.click();
  await expect(parts.hold).toHaveCount(0);
  await expect(parts.log).toContainText("the device result stays unknown");
  expect(counters.acks).toBe(1);
  expect(counters.starts).toHaveLength(1);
  expect(counters.voids).toEqual([]);
});

const heldRead = (extra: Record<string, unknown> = {}) => ({ z2: {
  alias: "z2", siteId: 2, kind: "READ", detail: "The Read Memory start outcome is unknown (timeout).",
  at: "2026-11-11T00:00:00.000Z", startId: "9".repeat(32), jobBindingSha256: "a".repeat(64), ...extra } });
const provenNotAccepted = (view: Record<string, unknown>) => ({ ...view, kind: "run", state: "NOT_ACCEPTED",
  reason: "START_NEVER_ADMITTED_AND_NO_LONGER_ADMISSIBLE",
  identity: { ppu_alias: "z2", site_id: 2, ppu_id: "z2-hil", operation: "read", operations: null, job_binding_sha256: "a".repeat(64) } });

async function seededHold(page: Page, holds: unknown, options: Parameters<typeof mockManager>[1] = {}) {
  await stubSavePicker(page, "save");
  await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [HOLD_KEY, JSON.stringify(holds)]);
  const counters = await mockManager(page, options);
  // A busy Site cannot be selected for programming; the hold is PPU-wide anyway.
  const busy = (options.ppus ?? []).some(ppu => ppu.busySites?.length);
  if (busy) {
    const workspace = await open(page);
    const job = await selectIc(page);
    return { counters, workspace, job, start: job.getByRole("button", { name: /START PROGRAMMING/ }), ...holdParts(workspace) };
  }
  const { workspace, job, start } = await configure(page);
  return { counters, workspace, job, start, ...holdParts(workspace) };
}

test("an idle Site never releases a Start the Manager has no record of", async ({ page }) => {
  // Journal lost / rolled back / never recorded: the Manager cannot prove anything.
  const held = await seededHold(page, heldRead());
  await expect(held.hold).toBeVisible();
  for (let i = 0; i < 2; i += 1) {
    await held.reconcile.click();
    await expect(held.note).toContainText("the Manager cannot prove what became of this Start (START_NOT_RECORDED)");
  }
  await expect(held.hold).toBeVisible();
  await expect(held.step).toHaveCount(0);
  await expect(held.read).toBeDisabled();
  await expect(held.start).toBeDisabled();
  await expect(held.log).toContainText("[RECONCILE] HOLD KEPT");
  expect(writes(held.counters)).toEqual([]);
});

const mismatches: Array<[string, (view: Record<string, unknown>) => Record<string, unknown>, RegExp]> = [
  ["another start ID", view => ({ ...provenNotAccepted(view), start_id: "8".repeat(32) }), /answered for another start or PPU/],
  ["another PPU", view => ({ ...provenNotAccepted(view), ppu_alias: "z9" }), /answered for another start or PPU/],
  ["another Site", view => ({ ...provenNotAccepted(view), identity: { ...(provenNotAccepted(view).identity), site_id: 1 } }), /does not match this PPU, Site, Operation or Job Binding/],
  ["another Job Binding", view => ({ ...provenNotAccepted(view), identity: { ...(provenNotAccepted(view).identity), job_binding_sha256: "b".repeat(64) } }), /does not match this PPU, Site, Operation or Job Binding/],
  ["another Operation", view => ({ ...provenNotAccepted(view), identity: { ...(provenNotAccepted(view).identity), operation: "programming" } }), /does not match this PPU, Site, Operation or Job Binding/],
  ["a Batch instead of a run", view => ({ ...provenNotAccepted(view), kind: "batch" }), /does not match this PPU, Site, Operation or Job Binding/],
  ["no identity", view => ({ ...provenNotAccepted(view), identity: null }), /carries no identity/],
  ["another schema", view => ({ ...provenNotAccepted(view), schema: "plasma.manager.other.v1" }), /not a Start reconciliation/],
  ["a result without a run", view => ({ ...provenNotAccepted(view), state: "TERMINAL_CONFIRMED", outcome: "PASS" }), /reports no definite result/],
];
for (const [name, edit, message] of mismatches) {
  test(`a reconciliation answer for ${name} keeps the hold`, async ({ page }) => {
    const held = await seededHold(page, heldRead(), { reconcile: edit });
    await held.reconcile.click();
    await expect(held.note).toContainText(message);
    await expect(held.hold).toBeVisible();
    await expect(held.read).toBeDisabled();
    await expect(held.start).toBeDisabled();
    expect(writes(held.counters)).toEqual([]);
  });
}

test("the exact answer for this start releases the hold (control for the mismatch cases)", async ({ page }) => {
  const held = await seededHold(page, heldRead(), { reconcile: provenNotAccepted });
  await held.reconcile.click();
  await expect(held.hold).toHaveCount(0);
  await expect(held.read).toBeEnabled();
  expect(writes(held.counters)).toEqual([]);
});

test("the Start hold is kept when the Manager cannot be asked", async ({ page }) => {
  const held = await seededHold(page, heldRead(), { reconcile: () => 503 });
  await held.reconcile.click();
  await expect(held.note).toContainText("the Manager could not be asked (manager_unavailable: Manager unavailable)");
  await expect(held.hold).toBeVisible();
  await expect(held.read).toBeDisabled();
  expect(held.counters.reconciles).toHaveLength(1);
  expect(writes(held.counters)).toEqual([]);
});

test("a hold recorded without a Manager start ID can never be released by this Console", async ({ page }) => {
  // Written before start IDs existed: there is nothing to ask the Manager about.
  const held = await seededHold(page, { z2: { alias: "z2", siteId: 2, kind: "READ", detail: "old", at: "2026-11-11T00:00:00.000Z" } });
  await expect(held.hold).toContainText("(no Manager start ID recorded)");
  await held.reconcile.click();
  await expect(held.note).toContainText("recorded without a Manager start ID");
  await expect(held.hold).toBeVisible();
  await expect(held.read).toBeDisabled();
  await expect(held.start).toBeDisabled();
  expect(held.counters.reconciles).toEqual([]);
  expect(writes(held.counters)).toEqual([]);
});

test("the Start hold is kept while the Manager Fleet shows the Site busy, even with a proven Manager answer", async ({ page }) => {
  const held = await seededHold(page, heldRead(), { ppus: [{ ...Z2, busySites: [2] }], reconcile: provenNotAccepted });
  await held.reconcile.click();
  await expect(held.note).toContainText("the Manager proves the Start was never admitted");
  await expect(held.note).toContainText("but SITE-02 is RUNNING (Job job-busy)");
  await expect(held.hold).toBeVisible();
  await expect(held.read).toBeDisabled();
  expect(writes(held.counters)).toEqual([]);
});

test("re-selecting the IC, Site, Source or Operations cannot bypass the Start hold", async ({ page }) => {
  const held = await seededHold(page, heldRead());
  await held.job.getByRole("radio", { name: "Bundle", exact: true }).click();
  await held.job.getByLabel("Engineering Programming Bundle file").setInputFiles(bundleFile);
  await expect(held.start).toBeDisabled();
  await held.job.getByRole("radio", { name: "Programming Image", exact: true }).click();
  await held.job.getByLabel("Engineering Programming Image file").setInputFiles(firmwareFile);
  await held.workspace.getByLabel("Select SITE 2 for programming").uncheck();
  await held.workspace.getByLabel("Select SITE 2 for programming").check();
  await selectIc(page);
  await expect(held.hold).toBeVisible();
  await expect(held.start).toBeDisabled();
  await expect(held.read).toBeDisabled();
  await held.read.click({ force: true });
  await held.start.click({ force: true });
  await page.waitForTimeout(1000);
  expect(writes(held.counters)).toEqual([]);
  expect((await pickerProbe(page)).calls).toEqual([]);
});

test("a hold taken in one tab blocks another tab of the same Browser without a reload", async ({ page, context }) => {
  await stubSavePicker(page, "save");
  await mockManager(page, { script: () => ({ startLost: true, runningPolls: 0 }) });
  const first = await configure(page);
  const other = await context.newPage();
  await stubSavePicker(other, "save");
  const otherCounters = await mockManager(other);
  const second = await configure(other);
  const otherParts = holdParts(second.workspace);
  await expect(otherParts.read).toBeEnabled();
  await holdParts(first.workspace).read.click();
  await expect(holdParts(first.workspace).hold).toBeVisible();
  // The other tab learns of the hold through the storage event.
  await expect(otherParts.hold).toContainText("the READ Start request on PPU z2");
  await expect(otherParts.read).toBeDisabled();
  await expect(second.start).toBeDisabled();
  await otherParts.read.click({ force: true });
  await second.start.click({ force: true });
  await other.waitForTimeout(1000);
  expect(writes(otherCounters)).toEqual([]);
});

test("a lost Programming Start answer also holds READ on the same PPU; a Batch that was never admitted is voided, not guessed", async ({ page }) => {
  await stubSavePicker(page, "save");
  const counters = await mockManager(page, { batchStatus: 504 });
  const { workspace, start } = await configure(page);
  const parts = holdParts(workspace);
  await start.click();
  await expect(workspace.getByTestId("managed-start-unknown")).toContainText("The Batch request outcome is unknown");
  await expect(parts.hold).toContainText("the PROGRAMMING Start request on PPU z2");
  await expect(parts.read).toBeDisabled();
  await expect(start).toBeDisabled();
  await parts.read.click({ force: true });
  await start.click({ force: true });
  await page.waitForTimeout(1500);
  // The Manager issued the start ID before the one Batch request.
  expect(counters.issued).toHaveLength(1);
  expect(counters.batches).toHaveLength(1);
  expect(counters.batches[0].body.start_id).toBe(counters.issued[0]);
  expect(counters.starts).toHaveLength(0);
  expect((await pickerProbe(page)).calls).toEqual([]);
  await parts.reconcile.click();
  await expect(parts.note).toContainText("the Manager has not admitted this Start");
  await expect(parts.hold).toBeVisible();
  await parts.step.click();
  await expect(parts.hold).toHaveCount(0);
  expect(counters.voids).toEqual(counters.issued);
  expect(counters.batches).toHaveLength(1);
  expect(counters.jobs).toEqual([]);
});

test("a Batch the Manager admitted whose answer was lost is reconciled to that Batch and blocks READ meanwhile", async ({ page }) => {
  await stubSavePicker(page, "save");
  const counters = await mockManager(page, { batchLost: true, script: () => ({ runningPolls: 1 }) });
  const { workspace, start } = await configure(page);
  const parts = holdParts(workspace);
  await start.click();
  await expect(parts.hold).toContainText("the PROGRAMMING Start request on PPU z2");
  await expect(parts.read).toBeDisabled();
  await parts.reconcile.click();
  await expect(parts.note).toContainText("the Manager admitted this Start and it is still running");
  await expect(parts.read).toBeDisabled();
  await parts.reconcile.click();
  await expect(parts.hold).toHaveCount(0);
  await expect(parts.log).toContainText(/the Manager admitted this Start as Batch [0-9a-f]{32} and it ended PASS/);
  // One Batch, one Job; reconciling never sent another.
  expect(counters.batches).toHaveLength(1);
  expect(counters.jobs).toHaveLength(1);
  expect(counters.acks).toBe(0);
  expect(counters.voids).toEqual([]);
  // The reconciled Batch is not counted as a result of this page: Yield is untouched.
  await expect(parts.read).toBeEnabled();
});

test("a Batch start ID the Manager does not issue is a refusal: no Batch request, no hold", async ({ page }) => {
  const counters = await mockManager(page, { issueStatus: 503 });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(workspace.getByLabel("Engineering job log")).toContainText("The Manager did not issue a start ID");
  await expect(workspace.getByTestId("managed-start-hold")).toHaveCount(0);
  expect(counters.batches).toHaveLength(0);
  expect(counters.jobs).toEqual([]);
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
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·", { timeout: 20_000 });
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
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
  await expect(result).toHaveText("PASS");
  await expect(summary).toContainText("100.0%");
});

test("one Start plans and executes: Firmware Resource Reuse → one Job → PASS receipt", async ({ page }) => {
  const counters = await mockManager(page);
  const { workspace, start } = await configure(page);
  await start.dblclick(); // a double click still submits exactly one plan and one run
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
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
  // No standing PROGRAMMING PLAN panel and no standing run view; the Backend
  // plan ran and its technical result is in the Engineering Job Log only.
  await expect(workspace.getByTestId("managed-plan")).toHaveCount(0);
  await expect(workspace.getByLabel("Programming plan", { exact: true })).toHaveCount(0);
  await expect(workspace.getByLabel("Programming run", { exact: true })).toHaveCount(0);
  await expect(workspace.locator("header").filter({ hasText: "PROGRAMMING PLAN" })).toHaveCount(0);
  await expect(workspace.getByTestId("run-plan-diagnostics")).toHaveCount(0);
  const log = jobLog(workspace);
  await expect(log).toContainText(/\[PLAN\] [0-9a-f]{32} · Route z2-site2-stm32f103c8t6-operations/);
  await expect(log).toContainText(/\[PLAN\] Range 0x08000000 \+ 4096 B · Resource SHA256 9{64}/);
  await expect(log).toContainText("· Source image ·");
  await expect(log).toContainText("[PLAN] Resource Reuse: the PPU verified identical Programming Resources");
  await expect(log).toContainText(`Resource SHA256 ${RESOURCE_SHA}`);
  await expect(log).toContainText("RESOURCE_REUSE: PPU_VERIFIED");
  await expect(log).not.toContainText("B1_UPLOAD");
  // Receipt summary in the Log: full identities, readback, range and SAFE_OFF.
  await expect(log).toContainText(/\[RECEIPT\] Job job-z2-site2-/);
  await expect(log).toContainText(/Readback SHA256 [0-9a-f]{64}/);
  await expect(log).toContainText("Range 0x08000000 + 4096 B · Resources Reused");
  await expect(log).toContainText(/Job Binding SHA256 z2-site2-plan1/);
  await expect(log).toContainText("SAFE_OFF VERIFIED");
  await expect(log).toContainText("attempts 1 · auto retry DISABLED");
  // The whole JSON Receipt is never printed back onto the page.
  await expect(workspace).not.toContainText("observed_steps");
  const row = workspace.locator('tr[data-site-selected="true"]');
  await expect(row.locator(".engineeringResult")).toHaveText("PASS");
  await expect(page.getByRole("region", { name: "Engineering Batch Summary" })).toContainText("100.0%");
  expect(legacyRequests(counters)).toEqual([]);
});

test("Firmware cache miss runs B1/B2/B3 through the Manager, then one Job", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ activationRequired: true }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
  await expect(jobLog(workspace)).toContainText("B1 upload → B2 admit → B3 activate (no FPGA load)");
  for (const step of ["B1_UPLOAD: PASS", "B2_ADMIT: PASS", "B3_ACTIVATE: PASS", "PROGRAMMING_SUBMIT: ACCEPTED", "VERIFY_RECEIPT: PASS"]) {
    await expect(jobLog(workspace)).toContainText(step);
  }
  await expect(jobLog(workspace)).toContainText("Resources Activated");
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  // The Browser itself never uploads, admits or activates anything.
  expect(counters.mutations.filter(entry => /uploads|deployments/.test(entry))).toEqual([]);
});

test("switching Firmware ↔ Bundle clears file, plan and run state and creates no Job", async ({ page }) => {
  const counters = await mockManager(page);
  const { workspace, job, start } = await configure(page);
  await start.click();
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
  const before = writes(counters).length;

  await job.getByRole("radio", { name: "Bundle", exact: true }).click();
  await expect(job.getByRole("radio", { name: "Bundle", exact: true })).toHaveAttribute("aria-checked", "true");
  await expect(job.getByRole("radio", { name: "Programming Image", exact: true })).toHaveAttribute("aria-checked", "false");
  await expect(job.locator("[data-image-source]")).toHaveAttribute("data-image-source", "none");
  await expect(job.locator("[data-image-source]")).toContainText("Select canonical Bundle v3");
  await expect(workspace.getByTestId("managed-plan")).toHaveCount(0);
  // The run state is cleared; the Log keeps the record of what already ran.
  await expect(workspace.locator('tr[data-site-selected="true"] .engineeringResult')).toHaveText("—");
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
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(1);
  const body = counters.plans[0].body;
  expect(Buffer.from(String(body.bundle_base64), "base64").equals(BUNDLE)).toBe(true);
  expect(body).not.toHaveProperty("image_base64");
  expect(body).not.toHaveProperty("image_filename");
  await expect(jobLog(workspace)).toContainText("· Source bundle ·");
  await expect(jobLog(workspace)).toContainText("[PLAN] Resource Reuse:");
  await expect(jobLog(workspace)).toContainText("Resources Reused");
  await expect(jobLog(workspace)).toContainText("SAFE_OFF VERIFIED");
});

test("Bundle cache miss is admitted and activated by the Manager (B1/B2/B3) → PASS", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ activationRequired: true }) });
  const { workspace, start } = await configure(page, "bundle");
  await start.click();
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
  await expect(jobLog(workspace)).toContainText("B3_ACTIVATE: PASS");
  await expect(jobLog(workspace)).toContainText("Resources Activated");
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
  await expect(jobLog(workspace)).not.toContainText("[RUN] ");
  expect(counters.plans).toHaveLength(1);
  expect(counters.starts).toHaveLength(0);
});

test("Manager OUTCOME_UNKNOWN is never resubmitted and latches Start until acknowledged", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({
    outcome: "OUTCOME_UNKNOWN", reason: "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT" }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(jobLog(workspace)).toContainText("[RUN] OUTCOME UNKNOWN ·");
  await expect(jobLog(workspace)).toContainText("DO_NOT_RESUBMIT");
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
  await expect(jobLog(first.workspace)).toContainText("[RUN] FAIL ·");
  await expect(jobLog(first.workspace)).toContainText("[RUN] FAIL · SAFE_OFF_NOT_VERIFIED ·");
  await expect(jobLog(first.workspace)).toContainText("SAFE_OFF NOT VERIFIED");
  await expect(first.workspace.locator('tr[data-site-selected="true"] .engineeringResult')).toHaveText("FAIL");
});

test("a PASS claim without verified SAFE_OFF in the receipt is shown as FAIL", async ({ page }) => {
  await mockManager(page, { script: () => ({ outcome: "PASS", safeOff: false }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(jobLog(workspace)).toContainText("[RUN] FAIL ·");
  await expect(jobLog(workspace)).toContainText("[RUN] FAIL · SAFE_OFF_NOT_VERIFIED ·");
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
  await expect(jobLog(workspace)).toContainText("[RUN] FAIL ·");
  await expect(jobLog(workspace)).toContainText("[RUN] FAIL · READBACK_SHA256_MISMATCH ·");
  await expect(jobLog(workspace)).toContainText(`Readback SHA256 ${"0".repeat(64)}`);
  await expect(workspace.locator('tr[data-site-selected="true"] .engineeringResult')).toHaveText("FAIL");
});

test("a PASS record whose readback differs from the expected Image is shown as FAIL", async ({ page }) => {
  await mockManager(page, { script: () => ({ outcome: "PASS", readbackOk: false }) });
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(jobLog(workspace)).toContainText("[RUN] FAIL ·");
  await expect(jobLog(workspace)).toContainText("[RUN] FAIL · READBACK_SHA256_MISMATCH ·");
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
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
  expect(providerCalls).toBe(0);
  expect(legacyRequests(counters)).toEqual([]);
});

test("a run on a Mock Site is labelled a Mock result; a hardware-path Site is not", async ({ page }) => {
  await mockManager(page, { ppus: [{ ...Z2, siteInterface: "mock" }] });
  const mock = await configure(page);
  await mock.start.click();
  await expect(jobLog(mock.workspace)).toContainText("[RUN] PASS ·");
  await expect(jobLog(mock.workspace)).toContainText("[EVIDENCE] MOCK RESULT · Site interface mock");
  await expect(jobLog(mock.workspace)).toContainText("never a hardware qualification");
});

test("a run on an openocd Site reports its interface and carries no Mock label", async ({ page }) => {
  await mockManager(page);
  const { workspace, start } = await configure(page);
  await start.click();
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
  await expect(jobLog(workspace)).toContainText("[EVIDENCE] Site interface: openocd");
  await expect(jobLog(workspace)).not.toContainText("MOCK RESULT");
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
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
  expect(counters.batches).toHaveLength(1);
  expect(counters.batches[0].body).toMatchObject({
    repeat: 1, retry_limit: 2, stop_policy: { kind: "failed_sites", threshold: 1 },
    operations: ["erase", "program", "verify"],
  });
  await expect(jobLog(workspace)).toContainText("Repeat 1 · Retry limit 2 · Stop Policy 1 failed Site");
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
  await expect(jobLog(workspace)).toContainText(/\[RESULT\] PASS · Batch \S+ · 2 attempt\(s\) · counted once/, { timeout: 20_000 });
  // Exactly one Batch request from the Browser; the Manager submitted two Jobs.
  expect(counters.batches).toHaveLength(1);
  expect(counters.jobs).toHaveLength(2);
  expect(new Set(counters.jobs).size).toBe(2);
  expect(new Set(counters.starts.map(item => item.body.plan_id)).size).toBe(2);
  const log = jobLog(workspace);
  await expect(log).toContainText(/\[ATTEMPT 1\/3\] FAIL · VERIFY_EVIDENCE_MISMATCH · Run \S+ · Job \S+ · SAFE_OFF VERIFIED · RETRY \(DEFINITE_FAIL_SAFE_OFF_VERIFIED\)/);
  await expect(log).toContainText(/\[ATTEMPT 2\/3\] PASS · Run \S+ · Job \S+ · SAFE_OFF VERIFIED/);
  // One IC: PASS 1, FAIL 0, Yield 100 %; the failed attempt is not a FAIL IC.
  const summary = page.getByRole("region", { name: "Engineering Batch Summary" });
  await expect(summary).toContainText("100.0%");
  await expect(workspace.locator('tr[data-site-selected="true"] .engineeringResult')).toHaveText("PASS");
  await expect(jobLog(workspace)).toContainText("[RUN] PASS ·");
  await expect(jobLog(workspace)).toContainText("attempts 1 · auto retry DISABLED");

  expect(legacyRequests(counters)).toEqual([]);
});

test("the Retry limit bounds the attempts; an exhausted Batch is one FAIL", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ outcome: "FAIL", reason: "PROGRAMMING_NOT_PASS" }) });
  const { workspace, job, start } = await configure(page);
  await setPolicy(job, "1");
  await start.click();
  await expect(jobLog(workspace)).toContainText(/\[RESULT\] FAIL · RETRY_LIMIT_EXHAUSTED · Batch \S+ · 2 attempt\(s\)/, { timeout: 20_000 });
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
  await expect(jobLog(workspace)).toContainText(/\[RESULT\] OUTCOME UNKNOWN · JOB_STATUS_UNKNOWN_DO_NOT_RESUBMIT · Batch \S+ · 1 attempt\(s\)/);
  expect(counters.jobs).toHaveLength(1);
  await expect(jobLog(workspace)).not.toContainText("RETRY ("); // no retry decision
  await expect(workspace.getByTestId("managed-unresolved")).toBeVisible();
  await expect(start).toBeDisabled();
  await expect(workspace.getByTestId("managed-readiness")).toContainText("OUTCOME UNKNOWN");
});

test("a FAIL without verified SAFE_OFF is not retried", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ outcome: "FAIL", reason: "SAFE_OFF_NOT_VERIFIED", safeOff: false }) });
  const { workspace, job, start } = await configure(page);
  await setPolicy(job, "3");
  await start.click();
  await expect(jobLog(workspace)).toContainText(/RETRY_NOT_ELIGIBLE_SAFE_OFF_NOT_VERIFIED · Batch \S+ · 1 attempt\(s\)/);
  await expect(jobLog(workspace)).toContainText("SAFE_OFF NOT VERIFIED · NO RETRY (SAFE_OFF_NOT_VERIFIED)");
  expect(counters.jobs).toHaveLength(1);
});

test("Stop Policy '1 failed Site' stops queuing after the first FAIL even with retries left", async ({ page }) => {
  const counters = await mockManager(page, { script: () => ({ outcome: "FAIL", reason: "PROGRAMMING_NOT_PASS" }) });
  const { workspace, job, start } = await configure(page);
  await setPolicy(job, "3", "1");
  await start.click();
  await expect(jobLog(workspace)).toContainText(/STOP_POLICY_FAILED_SITES_THRESHOLD_REACHED · Batch \S+ · 1 attempt\(s\)/);
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
  await expect(jobLog(workspace)).toContainText("no further attempt will be submitted · the running Job is not cancelled");
  await expect(jobLog(workspace)).toContainText(/\[RESULT\] FAIL · STOP_REQUESTED_NO_FURTHER_ATTEMPT · Batch \S+ · 1 attempt\(s\)/, { timeout: 20_000 });
  await expect(jobLog(workspace)).toContainText(/\[ATTEMPT 1\/4\] FAIL · PROGRAMMING_NOT_PASS/); // its real result
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
  await expect(jobLog(workspace)).not.toContainText("[ATTEMPT");
  await expect(workspace.locator('tr[data-site-selected="true"] .engineeringResult')).toHaveText("—");
});
