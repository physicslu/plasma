import { createHash } from "node:crypto";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import {
  batchRuns,
  engineeringLog,
  engineeringSiteRow,
  managed,
  observeManagedTraffic,
  openEngineering,
  selectEngineeringIc,
  setEngineeringOperations,
  setEngineeringSites,
  settledManagerBatch,
} from "./mock-cd-managed-helpers";
import { expectProgrammingJobContract, programmingJob } from "./programming-job-test-helpers";

// U10: the 1 MiB Programming Image is carried by the Manager Batch, once per
// Batch (never per Site, never through the retired Engineering asset
// or Browser-owned Batch paths). The PPU's Programming Resource Set is activated at
// most once (B1/B2/B3 on first use) and every later Batch reuses it. The
// evidence is the Manager's own Batch and run records, not Browser state.

const oneMiB = Buffer.from(Array.from({ length: 1024 * 1024 }, (_, index) => (index * 29 + 7) & 0xff));
const oneMiBSha = createHash("sha256").update(oneMiB).digest("hex");
const alias = managed.ppuA;
const sites = [1, 2];

async function prepare(page: Page) {
  const workspace = await openEngineering(page, alias);
  const job = await selectEngineeringIc(page);
  await expectProgrammingJobContract(programmingJob(page, "engineering"));
  await setEngineeringSites(workspace, sites, managed.ppuASites);
  await expect(workspace.getByRole("region", { name: "Engineering Site selection" })
    .locator('tbody input[type=checkbox]:checked')).toHaveCount(sites.length);
  await setEngineeringOperations(job, ["program"]);
  await job.getByLabel("Engineering Programming Image file").setInputFiles({
    name: "engineering-cache-1MiB.bin",
    mimeType: "application/octet-stream",
    buffer: oneMiB,
  });
  return { workspace, job };
}

async function runProgram(
  request: APIRequestContext,
  workspace: Locator,
  job: Locator,
  traffic: ReturnType<typeof observeManagedTraffic>,
  expectedBatches: number,
) {
  const start = job.getByRole("button", { name: /START PROGRAMMING/ });
  await expect(start).toBeEnabled();
  await start.click();
  await expect.poll(() => traffic.batches.length, { timeout: 15_000 }).toBe(expectedBatches);
  const sent = traffic.batches[expectedBatches - 1];
  await expect.poll(() => sent.batchId, { timeout: 15_000 }).toMatch(/^[0-9a-f]{32}$/);
  const batch = await settledManagerBatch(request, sent.batchId!, 90_000);
  expect(batch.outcome).toBe("PASS");
  await expect(engineeringLog(workspace)).toContainText(`[RESULT] PASS · Batch ${sent.batchId}`, { timeout: 30_000 });
  for (const siteId of sites) {
    await expect(engineeringSiteRow(workspace, siteId).locator(".engineeringResult")).toHaveText("PASS");
  }
  await expect(start).toBeEnabled({ timeout: 30_000 });
  return { sent, batch, runs: await batchRuns(request, batch) };
}

test("1 MiB Programming Image is sent once per Manager Batch; the Resource Set is activated once and reused, also after a Console reload", async ({ page, request }) => {
  const traffic = observeManagedTraffic(page);
  const uploads: string[] = [];
  page.on("request", item => {
    const url = new URL(item.url());
    // B1 uploads belong to the Manager → PPU Bootstrap path, never the Browser.
    if (item.method() === "POST" && /\/bootstrap\/uploads/.test(url.pathname)) uploads.push(url.pathname);
  });

  let { workspace, job } = await prepare(page);
  const results = [await runProgram(request, workspace, job, traffic, 1)];
  results.push(await runProgram(request, workspace, job, traffic, 2));

  // A Console reload (new Browser session) keeps using the Manager's state.
  await page.reload();
  ({ workspace, job } = await prepare(page));
  results.push(await runProgram(request, workspace, job, traffic, 3));

  // One Image per Batch request, for both Sites, as the canonical Batch body.
  expect(traffic.batches).toHaveLength(3);
  for (const { sent } of results) {
    expect(sent.body.targets).toEqual([{ ppu_alias: alias, site_ids: sites }]);
    expect(sent.body.operations).toEqual(["program"]);
    expect(typeof sent.body.image_base64).toBe("string");
    expect(Buffer.from(String(sent.body.image_base64), "base64").equals(oneMiB)).toBe(true);
    expect(sent.body).not.toHaveProperty("bundle_base64");
    expect(sent.body).not.toHaveProperty("asset_base64");
  }
  expect(new Set(traffic.batches.map(item => item.batchId)).size).toBe(3);

  // Manager evidence: one Job per Site per Batch, every one carrying the same Image.
  const resourceSets = new Set<string>();
  const activations: Array<{ batch: number; site: number }> = [];
  for (const [index, { runs }] of results.entries()) {
    expect(runs.map(item => item.run.site_id).sort((a, b) => a - b)).toEqual(sites);
    for (const { run } of runs) {
      expect(run.outcome).toBe("PASS");
      expect(run.receipt?.expected_image_sha256).toBe(oneMiBSha);
      expect(run.receipt?.expected_image_size).toBe(oneMiB.length);
      expect(run.receipt?.observed_image_sha256).toBe(oneMiBSha);
      resourceSets.add(String(run.plan?.resource.resource_set_sha256));
      if (run.plan?.activation_required) activations.push({ batch: index + 1, site: run.site_id });
      // Every Job ran on the already Active Resource Set.
      if (index > 0) expect(run.receipt?.resource_reuse).toBe(true);
    }
  }
  // Site plans never activate: the Manager activates the Resource Set once,
  // per PPU, before any Reservation (U1), and records it on the Batch.
  expect(activations).toEqual([]);
  const activated = results.map(({ batch }) => batch.resource_activation?.[alias] ?? null);
  // Later Batches find the Resource Set Active: no B1 / B2 / B3 at all.
  expect(activated.slice(1)).toEqual([null, null]);
  if (activated[0]) {
    // First use of this PPU: B1 upload → B2 admit → B3 activate, no FPGA load.
    expect(activated[0].result).toBe("PASS");
    expect(activated[0].fpga_load).toBe(false);
    expect(activated[0].steps.map(step => step.step)).toEqual(
      expect.arrayContaining(["B1_UPLOAD", "B2_ADMIT", "B3_ACTIVATE"]));
  }
  test.info().annotations.push({
    type: "resource-activation",
    description: activated[0] ? `Batch 1 activated the Resource Set on ${alias}` : `${alias} was already active before Batch 1`,
  });
  expect(resourceSets.size).toBe(1);
  const activeSets = new Set(results.flatMap(({ runs }) => runs.map(({ run }) => run.receipt?.active_asset_set_sha256)));
  expect(activeSets.size).toBe(1);
  expect([...activeSets][0]).toMatch(/^[0-9a-f]{64}$/);
  // The PPU's own report: one VERIFIED Active Set at generation 1. The stack
  // starts every PPU with no Active Set, so generation 1 means it was
  // activated exactly once since the stack started, whichever Batch did it.
  for (const { runs } of results) {
    for (const { run } of runs) {
      expect(run.plan?.resource.ppu_reported).toMatchObject({
        state: "VERIFIED",
        generation: 1,
        asset_set_sha256: [...activeSets][0],
        resource_set_sha256: [...resourceSets][0],
      });
    }
  }

  expect(uploads).toEqual([]);
  expect(traffic.legacy).toEqual([]);
});
