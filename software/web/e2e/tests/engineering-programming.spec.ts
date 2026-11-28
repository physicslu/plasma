import { createHash } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import { legacyRequests, mockFleet, mockManager } from "./managed-programming-helpers";
import { chooseTestTarget } from "./production-console-helpers";
import {
  programmingJob,
  programmingJobAction,
  programmingJobOperation,
} from "./programming-job-test-helpers";

// U10: Manager-managed only. EMode topology comes from the Manager Registry /
// Fleet (8 Facilities × PPUs of 2/4/6/8 Sites here) and every Programming
// Job is a Manager Batch aimed at the selected PPU's Sites. The Engineering
// session, its Connect button and the direct per-Site /api/jobs action are
// gone.

async function openProgramming(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.getByTestId("managed-backend")).toContainText("ONLINE");
}

const sha256 = (buffer: Buffer) => createHash("sha256").update(buffer).digest("hex");

test("Engineering Programming topology comes from the Manager Registry and Fleet", async ({ page }) => {
  await mockManager(page, { ppus: mockFleet(8) });
  await openProgramming(page);
  const selected = page.getByLabel("Selected Engineering PPU", { exact: true });
  await expect(selected).toContainText("8 Facilities | 32 PPUs | 160 Sites");

  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  await expect(facility.locator("option")).toHaveCount(8);
  await expect(ppu.locator("option")).toHaveCount(4);
  await expect(facility).toHaveValue("mock-facility-01");

  await ppu.selectOption("mock-facility-01-ppu-03");
  await expect(selected).toContainText("Manager Alias: mock-facility-01-ppu-03");
  await expect(selected).toContainText("6 Sites");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(6);

  await facility.selectOption("mock-facility-03");
  await expect(ppu).toHaveValue("mock-facility-03-ppu-01");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await ppu.selectOption("mock-facility-03-ppu-04");
  await expect(selected).toContainText("Manager Alias: mock-facility-03-ppu-04");
  await expect(selected).toContainText("8 Sites");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(8);
});

test("Engineering Erase Batch targets exactly the selected Facility, PPU and Site", async ({ page }) => {
  const counters = await mockManager(page, { ppus: mockFleet() });
  await openProgramming(page);
  await page.getByLabel("Engineering Facility", { exact: true }).selectOption("mock-facility-02");
  await page.getByLabel("Engineering PPU", { exact: true }).selectOption("mock-facility-02-ppu-03");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(6);
  await chooseTestTarget(page, "engineering");
  await page.getByLabel("Select SITE 6 for programming").check();
  const job = programmingJob(page, "engineering");
  await programmingJobOperation(job, "program").uncheck();
  await programmingJobOperation(job, "verify").uncheck();
  await programmingJobAction(job, "start").click();

  await expect.poll(() => counters.batches.length).toBe(1);
  expect(counters.batches[0].body.targets).toEqual([{ ppu_alias: "mock-facility-02-ppu-03", site_ids: [6] }]);
  expect(counters.batches[0].body.operations).toEqual(["erase"]);
  expect(legacyRequests(counters)).toEqual([]);
  await expect(page.getByLabel("Engineering job log")).toContainText("[USR] [START] ERASE · PPU mock-facility-02-ppu-03 (mock-facility-02-ppu-03) · SITE-06 (1 Site)");
  await expect(page.getByLabel("Engineering job log")).toContainText("[RESULT] PASS", { timeout: 20_000 });
});

test("the Programming Image is self-contained in every Manager Batch", async ({ page }) => {
  const counters = await mockManager(page, { ppus: mockFleet(1, [2]) });
  await openProgramming(page);
  await chooseTestTarget(page, "engineering");
  await page.getByLabel("Select SITE 1 for programming").check();
  const job = programmingJob(page, "engineering");
  const log = page.getByLabel("Engineering job log");
  const imageA = Buffer.alloc(32 * 1024, 0x5a);
  const imageB = Buffer.alloc(32 * 1024, 0xa5);
  const runBatch = async (count: number) => {
    await programmingJobAction(job, "start").click();
    await expect.poll(() => counters.batches.length).toBe(count);
    await expect(log.locator("span").filter({ hasText: "[RESULT] PASS" })).toHaveCount(count, { timeout: 20_000 });
    await expect(programmingJobAction(job, "start")).toBeEnabled();
  };

  await page.getByLabel("Engineering Programming Image file").setInputFiles({ name: "A.bin", mimeType: "application/octet-stream", buffer: imageA });
  await runBatch(1);
  await runBatch(2);
  await page.getByLabel("Engineering Programming Image file").setInputFiles({ name: "B.bin", mimeType: "application/octet-stream", buffer: imageB });
  await runBatch(3);

  const images = counters.batches.map(batch => Buffer.from(String(batch.body.image_base64), "base64"));
  expect(images[0].equals(imageA)).toBe(true);
  expect(images[1].equals(imageA)).toBe(true); // re-sent in full, never a cache reference
  expect(images[2].equals(imageB)).toBe(true);
  for (const batch of counters.batches) expect(batch.body).not.toHaveProperty("session_id");
  await expect(log).toContainText(`[DAT] [LOCK] IMAGE · A.bin · 32768 B · SHA256 ${sha256(imageA)}`);
  await expect(log).toContainText(`[DAT] [LOCK] IMAGE · B.bin · 32768 B · SHA256 ${sha256(imageB)}`);
  expect(legacyRequests(counters)).toEqual([]);
  expect(counters.requests.filter(entry => /programming-assets/.test(entry))).toEqual([]);
});
