import { expect, test, type Page } from "@playwright/test";
import { legacyRequests, mockFleet, mockManager, operationsRoute, type Counters } from "./managed-programming-helpers";
import {
  programmingJob as sharedProgrammingJob,
  programmingJobAction,
  programmingJobField,
  programmingJobOperation,
  programmingJobStatusValue,
} from "./programming-job-test-helpers";
import {
  chooseTestTarget,
  commitProductionSites,
  factoryConsoleHeading,
  productionOperation,
  programmingJob,
} from "./production-console-helpers";

// U10: Manager-managed only. The E / P / V readiness guard is kept in both
// modes. The Mock provider's "Mock Synthetic Image" is gone with the
// standalone engine: a Mock Site (Mock Profile) needs a real Programming Image
// exactly like a hardware Site, and nothing is submitted while not ready.

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

async function installManager(page: Page, siteInterface: "mock" | "openocd") {
  const ppus = mockFleet(1, [2]).map(ppu => ({ ...ppu, siteInterface }));
  return await mockManager(page, { ppus, routes: [{ ...operationsRoute(), site_interface: siteInterface }] });
}

const submissions = (counters: Counters) => counters.batches.length + counters.issued.length + legacyRequests(counters).length;

async function chooseFileFromButton(page: Page, buttonName: string, expectedFileName: string) {
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: buttonName, exact: true }).click();
  const chooser = await chooserPromise;
  await chooser.setFiles({ name: expectedFileName, mimeType: "application/octet-stream", buffer: Buffer.from([0x50, 0x4c, 0x41, 0x53, 0x4d, 0x41]) });
}

async function expectEngineeringV2Geometry(page: Page) {
  const job = sharedProgrammingJob(page, "engineering");
  const image = programmingJobField(job, "image");
  const operations = programmingJobField(job, "operations");
  const actions = job.locator('[data-programming-job-actions="engineering"]');
  const imageBox = await image.boundingBox();
  const operationBox = await operations.boundingBox();
  const actionBox = await actions.boundingBox();
  expect(imageBox).not.toBeNull();
  expect(operationBox).not.toBeNull();
  expect(actionBox).not.toBeNull();
  expect(imageBox!.y + imageBox!.height).toBeLessThanOrEqual(operationBox!.y);
  expect(operationBox!.y + operationBox!.height).toBeLessThanOrEqual(actionBox!.y);
  await expect(image.locator("[data-image-source]")).toHaveCSS("font-size", "10px");
}

test("PMode readiness on a Mock Site requires a Programming Image; no synthetic Image is offered", async ({ page }) => {
  const counters = await installManager(page, "mock");
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await commitProductionSites(page, facilityId, ppuId, [1]);
  await chooseTestTarget(page);
  const job = programmingJob(page);
  const readiness = programmingJobStatusValue(job);
  const execute = programmingJobAction(job, "start");
  const fileName = programmingJobField(job, "image").locator("[data-image-source]");
  for (const code of ["E", "P", "V"] as const) await productionOperation(page, code).uncheck();
  // PMode names an empty operation list OPERATIONS INVALID (EMode: NO OP).
  await expect(readiness).toHaveText("OPERATIONS INVALID");
  await expect(execute).toBeDisabled();
  await productionOperation(page, "P").check();
  await expect(fileName).toHaveAttribute("data-image-source", "none");
  await expect(fileName).not.toContainText("Synthetic");
  await expect(readiness).toHaveText("IMAGE REQUIRED");
  await expect(execute).toBeDisabled();
  await page.getByLabel("Production Programming Image file").setInputFiles({
    name: "pmod-test.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.from([0x50, 0x4c, 0x41, 0x53, 0x4d, 0x41]),
  });
  await expect(fileName).toHaveText("pmod-test.bin");
  await expect(readiness).toHaveText("MANAGER BATCH READY");
  await expect(execute).toBeEnabled();
  expect(submissions(counters)).toBe(0);
});

test("EMode readiness on a Mock Site requires a Programming Image and READ stays the Site row's action", async ({ page }) => {
  const counters = await installManager(page, "mock");
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await chooseTestTarget(page, "engineering");
  await page.getByLabel("Select SITE 1 for programming").check();
  const job = sharedProgrammingJob(page, "engineering");
  const readiness = programmingJobStatusValue(job);
  const execute = programmingJobAction(job, "start");
  const fileName = programmingJobField(job, "image").locator("[data-image-source]");
  for (const operation of ["erase", "program", "verify"] as const) await programmingJobOperation(job, operation).uncheck();
  await expect(readiness).toHaveText("NO OP");
  await expect(execute).toBeDisabled();
  await expect(programmingJobOperation(job, "read")).toHaveCount(0);
  await expect(page.getByLabel("Read SITE 1 Flash")).toBeVisible();
  await programmingJobOperation(job, "program").check();
  await expect(fileName).toHaveAttribute("data-image-source", "none");
  await expect(fileName).not.toContainText("Synthetic");
  await expect(readiness).toHaveText("IMAGE REQUIRED");
  await expect(execute).toBeDisabled();
  await chooseFileFromButton(page, "Browse...", "emode-test.bin");
  await expect(fileName).toHaveText("emode-test.bin");
  await expect(fileName).toHaveAttribute("data-image-source", "user_image");
  await expect(readiness).toHaveText("BATCH READY");
  await expect(execute).toBeEnabled();
  await expectEngineeringV2Geometry(page);
  expect(submissions(counters)).toBe(0);
});

test("hardware-path Sites remain fail-closed without a Programming Image in both modes", async ({ page }) => {
  const counters = await installManager(page, "openocd");
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await chooseTestTarget(page, "engineering");
  await page.getByLabel("Select SITE 1 for programming").check();
  const emodeJob = sharedProgrammingJob(page, "engineering");
  await programmingJobOperation(emodeJob, "program").check();
  await expect(programmingJobField(emodeJob, "image").locator("[data-image-source]")).toHaveAttribute("data-image-source", "none");
  await expect(programmingJobStatusValue(emodeJob)).toHaveText("IMAGE REQUIRED");
  await expect(programmingJobAction(emodeJob, "start")).toBeDisabled();
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await commitProductionSites(page, facilityId, ppuId, [1]);
  await chooseTestTarget(page);
  const pmodJob = programmingJob(page);
  const program = productionOperation(page, "P");
  if (!(await program.isChecked())) await program.check();
  await expect(programmingJobField(pmodJob, "image").locator("[data-image-source]")).toHaveText("Select programming image (.bin)…");
  await expect(programmingJobStatusValue(pmodJob)).toHaveText("IMAGE REQUIRED");
  await expect(programmingJobAction(pmodJob, "start")).toBeDisabled();
  expect(submissions(counters)).toBe(0);
});
