import { expect, type APIRequestContext, type Locator, type Page, type Request } from "@playwright/test";

// Real-stack helpers for the Mock CD Browser Runtime Acceptance (U10).
// The stack is Console → BFF → Manager ProgrammingBatchCoordinator → real PPU
// Bootstrap / Reservation / Job Binding → Mock PPU Runtime. Nothing here
// replaces a Plasma API: requests are only OBSERVED (page.on) and Manager
// evidence is read through the same same-origin BFF the Console uses.
// Results are Mock PPU evidence, never physical PPU / FPGA / DUT evidence.

export type Operation = "erase" | "program" | "verify" | "read";

export const managed = {
  consoleAlias: process.env.MOCK_CD_CONSOLE_PPU_ALIAS ?? "ppu-a",
  ppuA: process.env.MOCK_CD_PPU_A_ALIAS ?? "ppu-a",
  ppuASites: Number(process.env.MOCK_CD_PPU_A_SITES ?? "8"),
  ppuB: process.env.MOCK_CD_PPU_B_ALIAS ?? "ppu-b",
  ppuBSites: Number(process.env.MOCK_CD_PPU_B_SITES ?? "4"),
  facilityId: process.env.MOCK_CD_FACILITY_ID ?? "mock-facility",
  icpn: process.env.MOCK_CD_ROUTE_ICPN ?? "STM32F103C8T6",
  flashBase: Number(process.env.MOCK_CD_FLASH_BASE ?? String(0x08000000)),
  flashSize: Number(process.env.MOCK_CD_FLASH_SIZE ?? String(1024 * 1024)),
  harnessControlUrl: process.env.MOCK_CD_HARNESS_CONTROL_URL ?? "http://127.0.0.1:19890",
};

export const BATCHES_PATH = "/api/manager/programming/batches";

/** Plasma API paths the managed Console must never call (retired Browser-owned paths). */
export function isLegacyPath(pathname: string): boolean {
  return pathname === "/api/batches"
    || pathname.startsWith("/api/batches/")
    || pathname.startsWith("/api/engineering/")
    || pathname.includes("/api/programming-assets")
    || /\/api\/jobs(\/|$)/.test(pathname)
    || pathname.startsWith("/api/manager/ppu/api/jobs");
}

export type ObservedBatch = { body: Record<string, unknown>; batchId: string | null };

/**
 * Observe (never intercept) the Manager Batch traffic the Browser sends:
 * every POST /api/manager/programming/batches body with the batch_id the
 * Manager answered, every Batch stop, and any legacy Plasma API request.
 */
export function observeManagedTraffic(page: Page) {
  const batches: ObservedBatch[] = [];
  const stops: string[] = [];
  const legacy: string[] = [];
  const pending = new Map<Request, ObservedBatch>();
  page.on("request", request => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/")) return;
    if (isLegacyPath(url.pathname)) legacy.push(`${request.method()} ${url.pathname}`);
    if (request.method() !== "POST") return;
    if (url.pathname === BATCHES_PATH) {
      const entry: ObservedBatch = { body: request.postDataJSON() as Record<string, unknown>, batchId: null };
      batches.push(entry);
      pending.set(request, entry);
      return;
    }
    const stop = new RegExp(`^${BATCHES_PATH}/([0-9a-f]{32})/stop$`).exec(url.pathname);
    if (stop) stops.push(stop[1]);
  });
  page.on("response", async response => {
    const entry = pending.get(response.request());
    if (!entry) return;
    pending.delete(response.request());
    try {
      const payload = await response.json() as { batch?: { batch_id?: string }; batch_id?: string };
      entry.batchId = payload.batch?.batch_id ?? payload.batch_id ?? null;
    } catch {
      entry.batchId = null;
    }
  });
  return { batches, stops, legacy };
}

export type BatchAttempt = {
  attempt: number;
  cycle_index?: number | null;
  plan_id: string;
  run_id: string | null;
  job_id: string | null;
  outcome: string | null;
  job_key: { ppu_alias?: string; site_id: number };
  job_binding_sha256?: string;
  safe_off?: boolean | null;
};

export type BatchUnit = {
  ppu_alias: string;
  site_id: number;
  attempts: BatchAttempt[];
  cycle?: { planned: number; settled: number; pass: number; fail: number } | null;
};

export type BatchView = {
  batch_id: string;
  outcome: string | null;
  stop_requested?: boolean;
  operations?: string[];
  policy: { repeat: number; retry_limit: number };
  counts: Record<string, number>;
  units: BatchUnit[];
  attempts: BatchAttempt[];
  /** Per PPU alias: the B1/B2/B3 activation this Batch ran before any Reservation (absent when reused). */
  resource_activation?: Record<string, {
    steps: Array<{ step: string; result: string }>;
    fpga_load: boolean;
    result: string;
    reason: string | null;
  }>;
};

/** The Manager's durable Batch record, read through the same-origin BFF. */
export async function managerBatch(request: APIRequestContext, batchId: string): Promise<BatchView> {
  const response = await request.get(`${BATCHES_PATH}/${batchId}`);
  expect(response.ok(), `GET Batch ${batchId}`).toBeTruthy();
  const payload = await response.json() as { batch?: BatchView } & BatchView;
  return payload.batch ?? payload;
}

/** Wait until the Manager reports a terminal outcome for the Batch. */
export async function settledManagerBatch(request: APIRequestContext, batchId: string, timeout = 60_000): Promise<BatchView> {
  let view: BatchView | null = null;
  await expect.poll(async () => {
    view = await managerBatch(request, batchId);
    return view.outcome;
  }, { timeout, intervals: [250, 500, 1000] }).not.toBeNull();
  return view!;
}

export type RunPlan = {
  plan_id: string;
  activation_required: boolean;
  operations?: string[];
  resource: {
    resource_set_sha256: string;
    reuse?: boolean;
    ppu_reported?: { state?: string; asset_set_sha256?: string | null; generation?: number | null; resource_set_sha256?: string | null } | null;
  };
  job_binding?: { range?: { address: number; length: number } };
  job_binding_sha256?: string;
};

export type RunView = {
  run_id: string;
  site_id: number;
  outcome: string | null;
  plan?: RunPlan;
  receipt?: Record<string, unknown> & { read_output?: { filename?: string; bytes?: number; sha256?: string } | null };
};

/** One PPU-scoped Manager run record (plan + receipt), read through the BFF. */
export async function managerRun(request: APIRequestContext, alias: string, runId: string): Promise<RunView> {
  const response = await request.get(`/api/manager/registry/${encodeURIComponent(alias)}/bootstrap/programming/runs/${runId}`);
  expect(response.ok(), `GET run ${alias}/${runId}`).toBeTruthy();
  const payload = await response.json() as { run?: RunView } & RunView;
  return payload.run ?? payload;
}

/** Every submitted attempt of a Batch with its run record. */
export async function batchRuns(request: APIRequestContext, batch: BatchView) {
  const out: Array<{ unit: BatchUnit; attempt: BatchAttempt; run: RunView }> = [];
  for (const unit of batch.units) {
    for (const attempt of unit.attempts) {
      if (!attempt.run_id) continue;
      out.push({ unit, attempt, run: await managerRun(request, unit.ppu_alias, attempt.run_id) });
    }
  }
  return out;
}

// ---- Test-harness-only PPU offline / online switch (not a product API) ----

export async function harnessPpuState(request: APIRequestContext): Promise<Record<string, { state: string }>> {
  const response = await request.get(`${managed.harnessControlUrl}/ppus`);
  expect(response.ok()).toBeTruthy();
  return (await response.json() as { ppus: Record<string, { state: string }> }).ppus;
}

export async function setHarnessPpu(request: APIRequestContext, alias: string, state: "offline" | "online") {
  const response = await request.post(`${managed.harnessControlUrl}/ppus/${encodeURIComponent(alias)}/${state}`, {
    timeout: 60_000,
  });
  expect(response.ok(), `harness ${alias} ${state}: ${await response.text()}`).toBeTruthy();
  const payload = await response.json() as { ppus: Record<string, { state: string }> };
  expect(payload.ppus[alias]?.state).toBe(state);
}

// ---- EMode (Engineering → Programming, managed Single PPU) ----

export async function openEngineering(page: Page, alias = managed.consoleAlias) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: /^(Programming|燒錄)$/ }).first().click();
  const workspace = page.locator('[data-programming-backend="manager"]');
  await expect(workspace).toBeVisible();
  await expect(workspace.getByTestId("managed-backend")).toContainText("ONLINE", { timeout: 30_000 });
  const facility = workspace.getByLabel("Engineering Facility");
  await expect(facility).toHaveValue(managed.facilityId, { timeout: 30_000 });
  const ppu = workspace.getByLabel("Engineering PPU", { exact: true });
  if (await ppu.inputValue() !== alias) await ppu.selectOption(alias);
  await expect(ppu).toHaveValue(alias);
  return workspace;
}

export function engineeringJob(page: Page) {
  return page.getByRole("region", { name: "Engineering Programming Job", exact: true });
}

export async function selectEngineeringIc(page: Page) {
  const job = engineeringJob(page);
  await job.getByPlaceholder("Search ICPN / IC identifier...").fill(managed.icpn);
  await job.getByRole("option", { name: new RegExp(managed.icpn) }).first().click();
  await expect(job.getByPlaceholder("Search ICPN / IC identifier...")).toHaveValue(managed.icpn);
  return job;
}

export async function setEngineeringOperations(job: Locator, operations: Operation[]) {
  for (const name of ["erase", "program", "verify"] as const) {
    const box = job.getByLabel(`Engineering operation ${name}`);
    if (operations.includes(name)) await box.check();
    else await box.uncheck();
  }
}

export async function setEngineeringSites(workspace: Locator, siteIds: number[], siteCount: number) {
  for (let siteId = 1; siteId <= siteCount; siteId += 1) {
    const box = workspace.getByLabel(`Select SITE ${siteId} for programming`);
    if (siteIds.includes(siteId)) await box.check();
    else await box.uncheck();
  }
}

export const engineeringLog = (workspace: Locator) => workspace.getByLabel("Engineering job log");

export function engineeringSiteRow(workspace: Locator, siteId: number) {
  return workspace.getByRole("region", { name: "Engineering Site selection" })
    .locator("tbody tr").filter({ hasText: `SITE-${String(siteId).padStart(2, "0")}` }).first();
}

/** A deterministic, non-erased-looking pattern (never all 0xFF). */
export function imagePattern(length: number, multiplier = 29, offset = 7): Buffer {
  return Buffer.from(Array.from({ length }, (_, index) => (index * multiplier + offset) & 0xff));
}
