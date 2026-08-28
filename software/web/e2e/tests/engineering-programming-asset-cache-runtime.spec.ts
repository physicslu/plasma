import { expect, test } from "@playwright/test";
import {
  expectProgrammingJobContract,
  programmingJob,
  programmingJobAction,
  programmingJobOperation,
} from "./programming-job-test-helpers";

const engineeringFacilityId = process.env.MOCK_CD_ENGINEERING_FACILITY_ID ?? "mock-facility-02";
const engineeringPpuId = process.env.MOCK_CD_ENGINEERING_PPU_ID ?? "mock-facility-02-ppu-03";
const engineeringPpuSites = Number(process.env.MOCK_CD_ENGINEERING_PPU_SITES ?? "6");
const targetBase = `/api/engineering/targets/${engineeringFacilityId}/${engineeringPpuId}`;
const oneMiB = Buffer.from(Array.from({ length: 1024 * 1024 }, (_, index) => (index * 29 + 7) & 0xff));

type RuntimeCounters = {
  sessions: number;
  batches: number;
  directJobs: number;
  legacyAssetChecks: number;
  legacyAssetUploads: number;
};

async function selectSitesOneAndTwo(page: import("@playwright/test").Page) {
  for (let siteId = 1; siteId <= engineeringPpuSites; siteId += 1) {
    const checkbox = page.getByLabel(`Batch select SITE ${siteId}`);
    const shouldSelect = siteId <= 2;
    if (shouldSelect && !(await checkbox.isChecked())) await checkbox.check();
    if (!shouldSelect && await checkbox.isChecked()) await checkbox.uncheck();
  }
  await expect(page.getByLabel("Engineering Site selection").locator("tbody input[type=checkbox]:checked")).toHaveCount(2);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(engineeringPpuSites);
}

async function runTwoSiteProgram(
  page: import("@playwright/test").Page,
  expectedBatchCount: number,
  counters: RuntimeCounters,
) {
  const job = programmingJob(page, "engineering");
  const execute = programmingJobAction(job, "start");
  await expect(execute).toBeEnabled();
  await execute.click();
  await expect.poll(() => counters.batches, { timeout: 30_000 }).toBe(expectedBatchCount);
  await expect(execute).toBeEnabled({ timeout: 30_000 });
}

test("1 MiB Engineering Image Asset is submitted once per server Batch and remains usable after reconnect", async ({ page }) => {
  const counters: RuntimeCounters = {
    sessions: 0,
    batches: 0,
    directJobs: 0,
    legacyAssetChecks: 0,
    legacyAssetUploads: 0,
  };
  const sessionBodies: Array<Record<string, unknown>> = [];
  const batchBodies: Array<Record<string, unknown>> = [];

  page.on("request", request => {
    const url = new URL(request.url());
    if (request.method() !== "POST") return;
    if (url.pathname === "/api/engineering/session") {
      counters.sessions += 1;
      sessionBodies.push(request.postDataJSON() as Record<string, unknown>);
      return;
    }
    if (url.pathname === "/api/batches") {
      counters.batches += 1;
      batchBodies.push(request.postDataJSON() as Record<string, unknown>);
      return;
    }
    if (url.pathname === `${targetBase}/api/programming-assets/check`) {
      counters.legacyAssetChecks += 1;
      return;
    }
    if (url.pathname === `${targetBase}/api/programming-assets`) {
      counters.legacyAssetUploads += 1;
      return;
    }
    if (url.pathname === `${targetBase}/api/jobs`) {
      counters.directJobs += 1;
    }
  });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  await expect(facility.locator("option")).toHaveCount(8, { timeout: 15_000 });
  await facility.selectOption(engineeringFacilityId);
  await ppu.selectOption(engineeringPpuId);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(engineeringPpuSites, { timeout: 15_000 });

  await selectSitesOneAndTwo(page);
  const job = programmingJob(page, "engineering");
  await expectProgrammingJobContract(job);
  await page.getByLabel("Engineering Programming Image Asset file").setInputFiles({
    name: "engineering-cache-1MiB.bin",
    mimeType: "application/octet-stream",
    buffer: oneMiB,
  });
  await programmingJobOperation(job, "program").check();

  const sessionsAtFirstRun = counters.sessions;
  await runTwoSiteProgram(page, 1, counters);
  expect(counters.sessions).toBe(sessionsAtFirstRun);
  expect(counters.directJobs).toBe(0);
  expect(counters.legacyAssetChecks).toBe(0);
  expect(counters.legacyAssetUploads).toBe(0);

  const firstBatch = batchBodies[0];
  expect(firstBatch.targets).toEqual([{
    facility_id: engineeringFacilityId,
    ppu_id: engineeringPpuId,
    site_ids: [1, 2],
  }]);
  expect(firstBatch.operations).toEqual(["program"]);
  expect(typeof firstBatch.session_id).toBe("string");
  const firstAsset = firstBatch.asset as Record<string, unknown>;
  expect(firstAsset.asset_name).toBe("engineering-cache-1MiB.bin");
  expect(firstAsset.asset_type).toBe("image");
  expect(firstAsset.asset_format).toBe("binary");
  expect(firstAsset.asset_size).toBe(oneMiB.length);
  expect(typeof firstAsset.asset_sha256).toBe("string");
  expect(typeof firstAsset.asset_base64).toBe("string");
  expect(Buffer.from(String(firstAsset.asset_base64), "base64").equals(oneMiB)).toBe(true);
  expect(Object.hasOwn(firstAsset, "image_sha256")).toBe(false);

  await runTwoSiteProgram(page, 2, counters);
  expect(counters.directJobs).toBe(0);
  expect(counters.legacyAssetChecks).toBe(0);
  expect(counters.legacyAssetUploads).toBe(0);
  const secondAsset = batchBodies[1].asset as Record<string, unknown>;
  expect(secondAsset.asset_sha256).toBe(firstAsset.asset_sha256);
  expect(secondAsset.asset_size).toBe(oneMiB.length);

  const sessionsBeforeReconnect = counters.sessions;
  const previousBatchSession = batchBodies[1].session_id;
  await page.locator(".engineeringGateway button[type=submit]").click();
  await expect.poll(() => counters.sessions).toBeGreaterThan(sessionsBeforeReconnect);
  await expect(facility.locator("option")).toHaveCount(8, { timeout: 15_000 });
  await expect(facility).toHaveValue(engineeringFacilityId);
  await expect(ppu).toHaveValue(engineeringPpuId);
  await expect(page.getByLabel("Engineering Site selection").locator("tbody input[type=checkbox]:checked")).toHaveCount(2);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(engineeringPpuSites, { timeout: 15_000 });
  expect(sessionBodies.at(-1)?.previous_session_id).toBeTruthy();

  await selectSitesOneAndTwo(page);
  await runTwoSiteProgram(page, 3, counters);
  expect(batchBodies[2].session_id).toBeTruthy();
  expect(batchBodies[2].session_id).not.toBe(previousBatchSession);
  expect(counters.directJobs).toBe(0);
  expect(counters.legacyAssetChecks).toBe(0);
  expect(counters.legacyAssetUploads).toBe(0);
});
