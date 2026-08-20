import { readFile } from "node:fs/promises";
import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppu1 = "mock-facility-01-ppu-01";
const ppu2 = "mock-facility-01-ppu-02";

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 2,
    site_count: 4,
    firmware_scope: "connection-session-and-ppu",
    facilities: [{
      facility_id: facilityId,
      display_name: "Mock Facility 01",
      ppus: [ppu1, ppu2].map((ppuId, index) => ({
        ppu_id: ppuId,
        display_name: `Mock PPU 0${index + 1}`,
        model: "MOCK-PPU",
        site_count: 2,
        provider: "mock",
      })),
    }],
  };
}

function status(ppuId: string) {
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: ppuId === ppu1 ? "Mock PPU 01" : "Mock PPU 02",
      site_count: 2,
      enabled_site_count: 2,
      capabilities: {
        max_supported_sites: 2,
        operations: ["erase", "program", "verify", "read"],
      },
    },
    sites: [1, 2].map(siteId => ({
      site_id: siteId,
      enabled: true,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: "mock",
      target: "MOCK-IC",
    })),
  };
}

function jobPayload(jobId: string, siteId: number, operation: string, state: "queued" | "success") {
  return {
    ok: true,
    job: {
      job_id: jobId,
      site_id: siteId,
      operation,
      state,
      cancel_requested: false,
      stage: operation,
      stage_state: state === "success" ? "done" : state,
      stage_progress_percent: state === "success" ? 100 : 0,
      progress_percent: state === "success" ? 100 : 0,
      bytes_done: null,
      bytes_total: null,
      result: state === "success" ? { state, output_files: [], error: null } : undefined,
    },
  };
}

async function openProgramming(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
}

async function fulfillJson(route: Route, statusCode: number, body: unknown) {
  await route.fulfill({
    status: statusCode,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

test("Engineering audit log reconstructs operator actions and filters without truncating downloaded evidence", async ({ page }) => {
  let sessionNumber = 0;
  let jobNumber = 0;
  const jobs = new Map<string, { siteId: number; operation: string }>();

  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      sessionNumber += 1;
      await fulfillJson(route, 201, {
        ok: true,
        session: {
          session_id: String(sessionNumber).padStart(32, "0"),
          firmware_cache_scope: "connection-session-and-ppu",
          previous_session_cleared: sessionNumber > 1,
        },
      });
      return;
    }

    if (url.pathname === "/api/engineering/targets") {
      await fulfillJson(route, 200, catalog());
      return;
    }

    const parts = url.pathname.split("/").filter(Boolean);
    const currentPpu = parts[4];
    const tail = parts.slice(5).join("/");

    if (request.method() === "GET" && tail === "api/status" && !url.searchParams.has("job")) {
      await fulfillJson(route, 200, status(currentPpu));
      return;
    }

    if (request.method() === "POST" && tail === "api/jobs") {
      const body = request.postDataJSON() as { site_id: number; operation: string };
      jobNumber += 1;
      const jobId = `audit-job-${jobNumber}`;
      jobs.set(jobId, { siteId: body.site_id, operation: body.operation });
      await fulfillJson(route, 202, jobPayload(jobId, body.site_id, body.operation, "queued"));
      return;
    }

    if (request.method() === "GET" && tail === "api/status" && url.searchParams.has("job")) {
      const jobId = url.searchParams.get("job")!;
      const job = jobs.get(jobId)!;
      await fulfillJson(route, 200, jobPayload(jobId, job.siteId, job.operation, "success"));
      return;
    }

    await fulfillJson(route, 404, { error: { message: `unhandled ${tail}` } });
  });

  await openProgramming(page);
  const log = page.getByLabel("Engineering job log");
  await expect(log).toContainText("[NET] [SESSION] NEW · fresh connection");
  await expect(page.locator(".channelChecks label").first()).toContainText("SITE 01");
  await expect(page.locator(".channelChecks label").nth(1)).toContainText("SITE 02");

  await page.getByLabel("Engineering PPU", { exact: true }).selectOption(ppu2);
  await expect(log).toContainText(`[USR] [TARGET] SELECT · ${facilityId} / ${ppu2}`);
  await expect(log).toContainText(`[SYS] [TARGET] ${facilityId} / ${ppu2}`);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  await page.getByLabel("選取 SITE 2").uncheck();
  await expect(log).toContainText("[USR] [SITE] SELECTION · SITE 01");

  await page.getByLabel("Engineering Firmware file").setInputFiles({
    name: "operator-audit.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(1024, 0x5a),
  });
  await expect(log).toContainText("[USR] [FIRMWARE] SELECT · operator-audit.bin · 1.0 KiB");

  await page.getByLabel("Engineering batch erase").check();
  await expect(log).toContainText("[USR] [BATCH] OPERATIONS · ERASE");

  await page.locator(".executeBatch").click();
  await expect.poll(() => jobNumber).toBe(1);
  await expect(page.locator(".executeBatch")).toBeEnabled();
  await expect(log).toContainText("[USR] [BATCH] EXECUTE · ERASE · SITE 01");
  await expect(log).toContainText("[BAT] [BATCH] START ERASE · SITE 01");
  await expect(log).toContainText("[PPU] [SITE 01] ERASE accepted · audit-job-1");
  await expect(log).toContainText("[BAT] [BATCH] COMPLETE · success: SITE 01");

  await expect(page.getByText("FW", { exact: true })).toBeVisible();
  const logHeight = await log.evaluate(element => Number.parseFloat(getComputedStyle(element).height));
  expect(logHeight).toBeGreaterThanOrEqual(260);

  await page.getByLabel("Engineering log filter NET").uncheck();
  await page.getByLabel("Engineering log filter PPU").uncheck();
  await page.getByLabel("Engineering log filter FW").uncheck();
  await page.getByLabel("Engineering log filter BAT").uncheck();
  await page.getByLabel("Engineering log filter SYS").uncheck();

  const visibleEntries = log.locator("span");
  await expect(visibleEntries.first()).toHaveAttribute("data-category", "USR");
  expect(await visibleEntries.count()).toBeGreaterThan(0);
  for (const category of await visibleEntries.evaluateAll(elements => elements.map(element => element.getAttribute("data-category")))) {
    expect(category).toBe("USR");
  }
  await expect(log).not.toContainText("[PPU] [SITE 01] ERASE accepted");
  await expect(log).not.toContainText("[NET] [SESSION] NEW");

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download .log", exact: true }).click();
  const download = await downloadPromise;
  const path = await download.path();
  expect(path).not.toBeNull();
  const fileText = await readFile(path!, "utf8");
  expect(fileText).toContain("[USR] [BATCH] EXECUTE · ERASE · SITE 01");
  expect(fileText).toContain("[NET] [SESSION] NEW · fresh connection");
  expect(fileText).toContain("[PPU] [SITE 01] ERASE accepted · audit-job-1");
  expect(fileText).toContain("[BAT] [BATCH] COMPLETE · success: SITE 01");
});
