import { expect, test, type Page, type Request } from "@playwright/test";

const facilityId = process.env.MOCK_CD_PRODUCTION_FACILITY_ID ?? "mock-facility-01";
const ppuOne = process.env.MOCK_CD_PRODUCTION_PPU_ONE ?? `${facilityId}-ppu-01`;
const ppuTwo = process.env.MOCK_CD_PRODUCTION_PPU_TWO ?? `${facilityId}-ppu-02`;
const gateway = process.env.MOCK_CD_GATEWAY_URL ?? "http://127.0.0.1:19801";
const targetIc = "ADUC7019BCPZ62I";
const browserJobPath = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/jobs$/;

type RuntimeOperationSettings = {
  error_rate_per_mille: number;
  base_time_ms: number;
  throughput_bytes_per_second: number;
  jitter_ms: number;
};

type RuntimeSettings = {
  enabled: boolean;
  default_image_size_bytes: number;
  operations: Record<"erase" | "program" | "verify" | "read", RuntimeOperationSettings>;
  seed: { mode: "auto" | "fixed"; fixed_seed: number | null };
};

function editableRuntime(settings: RuntimeSettings) {
  return {
    enabled: settings.enabled,
    default_image_size_bytes: settings.default_image_size_bytes,
    operations: settings.operations,
    seed: settings.seed,
  };
}

function ppuCard(page: Page, ppuId: string) {
  return page.locator(`[data-production-ppu="${ppuId}"]`);
}

function siteCard(page: Page, ppuId: string, siteId = 1) {
  return ppuCard(page, ppuId).locator(`[data-production-site="${siteId}"]`);
}

function fpsCheckbox(page: Page, ppuId: string, siteId = 1) {
  return page.getByRole("checkbox", {
    name: `Production Set ${facilityId} ${ppuId} SITE-${String(siteId).padStart(2, "0")}`,
  });
}

function programmingJob(page: Page) {
  return page.getByRole("region", {
    name: "Production Programming Job",
    exact: true,
  });
}

function programmingJobStatus(page: Page) {
  return programmingJob(page).locator('[data-programming-job-action="status"] b');
}

function operationCheckbox(page: Page, index: number) {
  return programmingJob(page)
    .getByRole("group", { name: "Production batch operations", exact: true })
    .getByRole("checkbox")
    .nth(index);
}

async function chooseTarget(page: Page) {
  const target = page.getByLabel("Target IC");
  await target.fill(targetIc);
  await expect(page.getByRole("listbox", { name: "Target IC search results" })).toBeVisible();
  await page.getByRole("option", { name: new RegExp(targetIc) }).click();
}

async function openTwoPpuProductionSet(page: Page) {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "PMODE · FACTORY CONSOLE" })).toBeVisible();

  const facility = page.locator(".productionTreeFacility").first();
  if (!await facility.evaluate((element: HTMLDetailsElement) => element.open)) {
    await facility.locator(":scope > summary").click();
  }
  const ppus = facility.locator(".productionTreePpu");
  await expect(ppus).toHaveCount(4);
  for (const index of [0, 1]) {
    const ppu = ppus.nth(index);
    if (!await ppu.evaluate((element: HTMLDetailsElement) => element.open)) {
      await ppu.locator(":scope > summary").click();
    }
  }

  await expect(fpsCheckbox(page, ppuOne)).toBeVisible();
  await expect(fpsCheckbox(page, ppuTwo)).toBeVisible();

  await fpsCheckbox(page, ppuOne).check();
  await fpsCheckbox(page, ppuTwo).check();
  await page.getByRole("button", { name: "SET PRODUCTION SITES", exact: true }).click();

  const first = ppuCard(page, ppuOne);
  const second = ppuCard(page, ppuTwo);
  await expect(first).toBeVisible();
  await expect(second).toBeVisible();
  await expect(page.locator('[data-kpi="production-sites"] b')).toHaveText("2");

  await chooseTarget(page);
  await operationCheckbox(page, 0).check();
  return { first, second };
}

function observeBrowserOwnership(page: Page) {
  const batchBodies: Array<Record<string, unknown>> = [];
  const batchPpuCancels: string[] = [];
  let browserJobPosts = 0;
  let wholeBatchCancels = 0;
  page.on("request", (request: Request) => {
    if (request.method() !== "POST") return;
    const url = new URL(request.url());
    if (url.pathname === "/api/batches") {
      batchBodies.push(request.postDataJSON() as Record<string, unknown>);
      return;
    }
    if (browserJobPath.test(url.pathname)) {
      browserJobPosts += 1;
      return;
    }
    if (/^\/api\/batches\/[^/]+\/cancel$/.test(url.pathname)) {
      wholeBatchCancels += 1;
      return;
    }
    const ppuCancel = /^\/api\/batches\/[^/]+\/targets\/([^/]+)\/([^/]+)\/cancel$/.exec(url.pathname);
    if (ppuCancel) batchPpuCancels.push(decodeURIComponent(ppuCancel[2]));
  });
  return {
    batchBodies,
    batchPpuCancels,
    browserJobPosts: () => browserJobPosts,
    wholeBatchCancels: () => wholeBatchCancels,
  };
}

test("real Production Mock submits one server Batch for two PPUs and completes both", async ({ page }) => {
  const ownership = observeBrowserOwnership(page);
  const { first, second } = await openTwoPpuProductionSet(page);

  await programmingJob(page).getByRole("button", { name: /START PROGRAMMING/ }).click();

  await expect.poll(() => ownership.batchBodies.length, { timeout: 5_000 }).toBe(1);
  const body = ownership.batchBodies[0] as {
    targets?: Array<{ ppu_id?: string }>;
    execution_policy?: Record<string, unknown>;
  };
  expect(body.targets?.map(target => target.ppu_id)).toEqual([ppuOne, ppuTwo]);
  expect(body.execution_policy).toEqual({
    repeat_count: 1,
    site_retry_limit: 3,
    failed_site_stop_threshold: null,
  });
  expect(ownership.browserJobPosts()).toBe(0);

  await expect(first.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });
  await expect(second.locator('[data-production-site="1"]')).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });

  await expect(siteCard(page, ppuOne)).toHaveAttribute("data-site-state", "success", { timeout: 15_000 });
  await expect(siteCard(page, ppuTwo)).toHaveAttribute("data-site-state", "success", { timeout: 15_000 });
  await expect(programmingJobStatus(page)).toHaveText("SUCCESS");
  await expect(page.locator('[data-kpi="pass"] b')).toHaveText("2");
  await expect(page.locator('[data-kpi="fail"] b')).toHaveText("0");
  expect(ownership.browserJobPosts()).toBe(0);
});

test("real Production Mock shares one Programming Asset across two PPUs for Erase Program Verify", async ({ page }) => {
  const ownership = observeBrowserOwnership(page);
  await openTwoPpuProductionSet(page);

  await page.getByLabel("Production Programming Image file").setInputFiles({
    name: "production-shared-asset.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(4096, 0xa5),
  });
  await operationCheckbox(page, 1).check();
  await operationCheckbox(page, 2).check();
  await programmingJob(page).getByRole("button", { name: /START PROGRAMMING/ }).click();

  await expect.poll(() => ownership.batchBodies.length, { timeout: 5_000 }).toBe(1);
  const body = ownership.batchBodies[0] as {
    targets?: Array<{ ppu_id?: string }>;
    operations?: string[];
    asset?: {
      asset_name?: string;
      asset_size?: number;
      asset_sha256?: string;
      asset_base64?: string;
    };
  };
  expect(body.targets?.map(target => target.ppu_id)).toEqual([ppuOne, ppuTwo]);
  expect(body.operations).toEqual(["erase", "program", "verify"]);
  expect(body.asset?.asset_name).toBe("production-shared-asset.bin");
  expect(body.asset?.asset_size).toBe(4096);
  expect(body.asset?.asset_sha256).toMatch(/^[0-9a-f]{64}$/);
  expect(body.asset?.asset_base64).toBeTruthy();
  expect(ownership.browserJobPosts()).toBe(0);

  await expect(siteCard(page, ppuOne)).toHaveAttribute("data-site-state", "success", { timeout: 30_000 });
  await expect(siteCard(page, ppuTwo)).toHaveAttribute("data-site-state", "success", { timeout: 30_000 });
  await expect(programmingJobStatus(page)).toHaveText("SUCCESS");
  await expect(page.locator('[data-kpi="pass"] b')).toHaveText("2");
  await expect(page.locator('[data-kpi="yield"] b')).toHaveText("100.0%");
  expect(ownership.browserJobPosts()).toBe(0);
});

test("real Production Mock exposes only whole-Batch ABORT for multi-PPU runtime", async ({ page, request }) => {
  const runtimeResponse = await request.get(`${gateway}/api/mock/runtime`);
  expect(runtimeResponse.ok()).toBeTruthy();
  const runtimePayload = await runtimeResponse.json();
  const original = runtimePayload.mock_runtime as RuntimeSettings;
  const slowed = {
    ...editableRuntime(original),
    operations: {
      ...original.operations,
      erase: {
        ...original.operations.erase,
        error_rate_per_mille: 0,
        // Keep the real-stack cancellation window independent of busy-runner
        // browser/actionability latency; the already-terminal ABORT race has
        // its own dedicated mode-guard regression coverage.
        base_time_ms: 3000,
        jitter_ms: 0,
      },
    },
  };

  const updateResponse = await request.post(`${gateway}/api/mock/runtime`, { data: slowed });
  expect(updateResponse.ok()).toBeTruthy();

  try {
    const ownership = observeBrowserOwnership(page);
    await openTwoPpuProductionSet(page);

    const programming = programmingJob(page);
    await programming.getByRole("button", { name: /START PROGRAMMING/ }).click();
    await expect(siteCard(page, ppuOne)).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });
    await expect(siteCard(page, ppuTwo)).toHaveAttribute("data-site-state", "running", { timeout: 5_000 });

    await expect(page.getByRole("button", { name: "Cancel PPU", exact: true })).toHaveCount(0);
    await programming.getByRole("button", { name: /ABORT/ }).click();
    await expect.poll(() => ownership.wholeBatchCancels(), { timeout: 5_000 }).toBe(1);
    await expect(siteCard(page, ppuOne)).toHaveAttribute("data-site-state", "cancelled", { timeout: 10_000 });
    await expect(siteCard(page, ppuTwo)).toHaveAttribute("data-site-state", "cancelled", { timeout: 10_000 });
    await expect(programmingJobStatus(page)).toHaveText("CANCELLED");

    expect(ownership.batchPpuCancels).toEqual([]);
    expect(ownership.browserJobPosts()).toBe(0);
  } finally {
    const restoreResponse = await request.post(`${gateway}/api/mock/runtime`, { data: editableRuntime(original) });
    expect(restoreResponse.ok()).toBeTruthy();
  }
});
