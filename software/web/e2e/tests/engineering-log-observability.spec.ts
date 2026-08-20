import { expect, test, type Page, type Route } from "@playwright/test";

const facilityId = "mock-facility-01";
const ppuId = "mock-facility-01-ppu-01";

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 1,
    site_count: 2,
    programming_image_scope: "connection-session-and-ppu",
    facilities: [{
      facility_id: facilityId,
      display_name: "Mock Facility 01",
      ppus: [{
        ppu_id: ppuId,
        display_name: "Mock PPU 01",
        model: "MOCK-PPU",
        site_count: 2,
        provider: "mock",
      }],
    }],
  };
}

function status() {
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: "Mock PPU 01",
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

function jobPayload(
  jobId: string,
  siteId: number,
  operation: string,
  state: "queued" | "running" | "success" | "cancelled",
) {
  return {
    ok: true,
    job: {
      job_id: jobId,
      site_id: siteId,
      operation,
      state,
      cancel_requested: state === "cancelled",
      stage: operation,
      stage_state: state === "success" ? "done" : state,
      stage_progress_percent: state === "success" ? 100 : 25,
      progress_percent: state === "success" ? 100 : 25,
      bytes_done: null,
      bytes_total: null,
      result: state === "success" || state === "cancelled"
        ? { state, output_files: [], error: null }
        : undefined,
    },
  };
}

async function openProgramming(page: Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
}

async function baseRoute(
  route: Route,
  session: { number: number },
): Promise<boolean> {
  const request = route.request();
  const url = new URL(request.url());
  if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
    session.number += 1;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        session: {
          session_id: String(session.number).padStart(32, "0"),
          programming_image_cache_scope: "connection-session-and-ppu",
          previous_session_cleared: session.number > 1,
        },
      }),
    });
    return true;
  }
  if (url.pathname === "/api/engineering/targets") {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
    return true;
  }
  const parts = url.pathname.split("/").filter(Boolean);
  const tail = parts.slice(5).join("/");
  if (request.method() === "GET" && tail === "api/status" && !url.searchParams.has("job")) {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(status()) });
    return true;
  }
  return false;
}

test("Engineering log distinguishes SHA-256 fingerprint-only reuse from binary upload", async ({ page }) => {
  const session = { number: 0 };
  let cachedSha: string | null = null;
  let uploadCount = 0;
  let jobNumber = 0;
  const jobs = new Map<string, { siteId: number; operation: string }>();

  await page.route("**/api/engineering/**", async route => {
    if (await baseRoute(route, session)) {
      if (route.request().url().includes("/api/engineering/session")) cachedSha = null;
      return;
    }
    const request = route.request();
    const url = new URL(request.url());
    const parts = url.pathname.split("/").filter(Boolean);
    const tail = parts.slice(5).join("/");

    if (request.method() === "POST" && tail === "api/programming-images/check") {
      const body = request.postDataJSON() as {
        image_name: string;
        image_size: number;
        image_sha256: string;
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          programming_image: {
            cache_hit: cachedSha === body.image_sha256,
            ...body,
          },
        }),
      });
      return;
    }
    if (request.method() === "POST" && tail === "api/programming-images") {
      uploadCount += 1;
      cachedSha = url.searchParams.get("sha256");
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, programming_image: { uploaded: true, cache_hit: true, image_sha256: cachedSha } }),
      });
      return;
    }
    if (request.method() === "POST" && tail === "api/jobs") {
      const body = request.postDataJSON() as { site_id: number; operation: string };
      jobNumber += 1;
      const jobId = `programming-image-log-job-${jobNumber}`;
      jobs.set(jobId, { siteId: body.site_id, operation: body.operation });
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify(jobPayload(jobId, body.site_id, body.operation, "queued")),
      });
      return;
    }
    if (request.method() === "GET" && tail === "api/status" && url.searchParams.has("job")) {
      const jobId = url.searchParams.get("job")!;
      const job = jobs.get(jobId)!;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(jobPayload(jobId, job.siteId, job.operation, "success")),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: `unhandled ${tail}` } }) });
  });

  await openProgramming(page);
  const log = page.getByLabel("Engineering job log");
  await expect(log).toContainText("[SESSION] NEW · fresh connection");

  await page.getByLabel("Engineering Firmware file").setInputFiles({
    name: "observable.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(1024 * 1024, 0x5a),
  });
  await page.getByLabel("Engineering batch program").check();

  await page.locator(".executeBatch").click();
  await expect.poll(() => jobNumber).toBe(2);
  await expect.poll(() => page.locator(".executeBatch").isEnabled()).toBe(true);
  expect(uploadCount).toBe(1);
  await expect(log).toContainText("[DAT] [IMG] CACHE CHECK · observable.bin · 1.00 MiB · SHA256");
  await expect(log).toContainText("fingerprint only");
  await expect(log).toContainText("[DAT] [IMG] CACHE MISS · SHA256");
  await expect(log).toContainText("[DAT] [IMG] UPLOAD START · observable.bin · 1.00 MiB · SHA256");
  await expect(log).toContainText("[DAT] [IMG] UPLOAD COMPLETE · observable.bin · 1.00 MiB · SHA256");

  await page.locator(".executeBatch").click();
  await expect.poll(() => jobNumber).toBe(4);
  await expect.poll(() => page.locator(".executeBatch").isEnabled()).toBe(true);
  expect(uploadCount).toBe(1);
  await expect(log).toContainText("[DAT] [IMG] CACHE HIT · SHA256");
  await expect(log).toContainText("reference only · no binary upload");

  await page.locator(".engineeringGateway button[type=submit]").click();
  await expect(log).toContainText("[SESSION] NEW · previous firmware cache cleared");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
});

test("independent Site cancellation produces a PARTIAL aggregate batch summary", async ({ page }) => {
  const session = { number: 0 };
  let jobNumber = 0;
  const jobs = new Map<string, {
    siteId: number;
    operation: string;
    cancelled: boolean;
  }>();

  await page.route("**/api/engineering/**", async route => {
    if (await baseRoute(route, session)) return;
    const request = route.request();
    const url = new URL(request.url());
    const parts = url.pathname.split("/").filter(Boolean);
    const tail = parts.slice(5).join("/");

    if (request.method() === "POST" && tail === "api/jobs") {
      const body = request.postDataJSON() as { site_id: number; operation: string };
      jobNumber += 1;
      const jobId = `partial-job-${jobNumber}`;
      jobs.set(jobId, { siteId: body.site_id, operation: body.operation, cancelled: false });
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify(jobPayload(jobId, body.site_id, body.operation, "queued")),
      });
      return;
    }
    if (request.method() === "POST" && tail.startsWith("api/jobs/") && tail.endsWith("/cancel")) {
      const jobId = parts[7];
      const job = jobs.get(jobId);
      if (job) job.cancelled = true;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, accepted: true }) });
      return;
    }
    if (request.method() === "GET" && tail === "api/status" && url.searchParams.has("job")) {
      const jobId = url.searchParams.get("job")!;
      const job = jobs.get(jobId)!;
      const state = job.cancelled ? "cancelled" : job.siteId === 1 ? "success" : "running";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(jobPayload(jobId, job.siteId, job.operation, state)),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: `unhandled ${tail}` } }) });
  });

  await openProgramming(page);
  await page.getByLabel("Engineering batch erase").check();
  await page.locator(".executeBatch").click();
  await expect.poll(() => jobNumber).toBe(2);
  await expect(page.getByLabel("Cancel SITE 2")).toBeEnabled();
  await page.getByLabel("Cancel SITE 2").click();

  const log = page.getByLabel("Engineering job log");
  await expect(log).toContainText("[PPU] [SITE-02] Cancel requested", { timeout: 15_000 });
  await expect(log).toContainText("[BAT] PARTIAL · success: SITE-01 · cancelled: SITE-02 · failed: —", { timeout: 15_000 });
  await expect(page.locator(".executeBatch")).toBeEnabled();
});
