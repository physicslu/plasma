import { expect, test } from "@playwright/test";
import { FIRMWARE, legacyRequests, mockFleet, mockManager, operationsRoute } from "./managed-programming-helpers";
import {
  programmingJobAction,
  programmingJobField,
  programmingJobStatusValue,
} from "./programming-job-test-helpers";
import {
  chooseTestTarget,
  commitProductionSites,
  factoryConsoleHeading,
  productionOperation,
  programmingJob,
} from "./production-console-helpers";

// U10: the standalone Mock provider and its "Mock Synthetic Image" intent are
// gone. A Production Batch on a Mock Site (Mock Profile) is a Manager Batch
// that carries the operator's real Programming Image bytes; the Browser never
// sends a synthetic-image intent and the result is labelled a Mock result.

const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

test("Production on a Mock Site submits the operator Image in the Manager Batch, never a synthetic Image intent", async ({ page }) => {
  const ppus = mockFleet(1, [2]).map(ppu => ({ ...ppu, siteInterface: "mock" }));
  const counters = await mockManager(page, { ppus, routes: [{ ...operationsRoute(), site_interface: "mock" }] });
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await commitProductionSites(page, facilityId, ppuId, [1]);
  await chooseTestTarget(page);

  const job = programmingJob(page);
  const imageName = programmingJobField(job, "image").locator("[data-image-source]");
  await productionOperation(page, "E").uncheck();
  await productionOperation(page, "V").uncheck();
  await expect(imageName).not.toContainText("Synthetic");
  await expect(programmingJobStatusValue(job)).toHaveText("IMAGE REQUIRED");
  await page.getByLabel("Production Programming Image file").setInputFiles({
    name: "mock-site.bin", mimeType: "application/octet-stream", buffer: FIRMWARE,
  });
  await expect(programmingJobStatusValue(job)).toHaveText("MANAGER BATCH READY");
  await programmingJobAction(job, "start").click();

  await expect.poll(() => counters.batches.length).toBe(1);
  const submitted = counters.batches[0].body;
  expect(submitted.operations).toEqual(["program"]);
  expect(Buffer.from(String(submitted.image_base64), "base64").equals(FIRMWARE)).toBe(true);
  expect(submitted).not.toHaveProperty("session_id");
  expect(submitted).not.toHaveProperty("asset");
  expect(JSON.stringify(submitted)).not.toMatch(/synthetic/i);
  expect(legacyRequests(counters)).toEqual([]);

  await expect(programmingJobStatusValue(job)).toHaveText("SUCCESS", { timeout: 20_000 });
  await expect(imageName).toHaveText("mock-site.bin");
  await expect(page.getByLabel("Production batch log")).toContainText("MOCK RESULT");
});
