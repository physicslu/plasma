import { expect, test } from "@playwright/test";

const siteCounts = [2, 4, 6, 8] as const;

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 3,
    ppu_count: 12,
    site_count: 60,
    firmware_scope: "connection-session-and-ppu",
    facilities: Array.from({ length: 3 }, (_, facilityIndex) => {
      const facilityNumber = facilityIndex + 1;
      const facilityId = `mock-facility-${String(facilityNumber).padStart(2, "0")}`;
      return {
        facility_id: facilityId,
        display_name: `Server Facility ${String(facilityNumber).padStart(2, "0")}`,
        ppus: siteCounts.map((siteCount, ppuIndex) => ({
          ppu_id: `${facilityId}-ppu-${String(ppuIndex + 1).padStart(2, "0")}`,
          display_name: `Server PPU ${String(ppuIndex + 1).padStart(2, "0")}`,
          model: "MOCK-PPU",
          site_count: siteCount,
          provider: "mock",
        })),
      };
    }),
  };
}

function statusFor(facilityId: string, ppuId: string) {
  const ppuNumber = Number(ppuId.slice(-2));
  const siteCount = siteCounts[ppuNumber - 1];
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: `Server PPU ${String(ppuNumber).padStart(2, "0")}`,
      site_count: siteCount,
      enabled_site_count: siteCount,
      capabilities: { max_supported_sites: siteCount, operations: ["erase", "program", "verify", "read"] },
    },
    sites: Array.from({ length: siteCount }, (_, index) => ({
      site_id: index + 1,
      enabled: true,
      state: "idle",
      current_job_id: null,
      queued_jobs: 0,
      interface: "mock",
      target: "MOCK-IC",
    })),
  };
}

function terminalJob(jobId: string, siteId: number, operation: string) {
  return {
    ok: true,
    job: {
      job_id: jobId,
      site_id: siteId,
      operation,
      state: "success",
      cancel_requested: false,
      stage: operation,
      stage_state: "done",
      stage_progress_percent: 100,
      progress_percent: 100,
      bytes_done: null,
      bytes_total: null,
      result: { state: "success", output_files: [] },
    },
  };
}

async function openProgramming(page: import("@playwright/test").Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
}

test("Engineering Programming topology comes from the Python target catalog", async ({ page }) => {
  let sessionNumber = 0;
  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      sessionNumber += 1;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: String(sessionNumber).padStart(32, "0"),
            firmware_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: sessionNumber > 1,
          },
        }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }

    const parts = url.pathname.split("/").filter(Boolean);
    const facilityId = parts[3];
    const ppuId = parts[4];
    if (request.method() === "GET" && parts.slice(5).join("/") === "api/status" && !url.searchParams.has("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(statusFor(facilityId, ppuId)) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled Engineering route" } }) });
  });

  await openProgramming(page);
  await expect(page.getByText("SERVER SOURCE OF TRUTH")).toBeVisible();

  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  await expect(facility.locator("option")).toHaveCount(3);
  await expect(ppu.locator("option")).toHaveCount(4);
  await expect(facility.locator("option").first()).toHaveText("Server Facility 01");

  await ppu.selectOption("mock-facility-01-ppu-03");
  await expect(page.getByLabel("Selected Engineering PPU", { exact: true })).toContainText("Server Facility 01 / Server PPU 03");
  await expect(page.getByLabel("Selected Engineering PPU", { exact: true })).toContainText("6 Sites");
  await expect(page.getByLabel("Engineering Site selection").getByRole("checkbox")).toHaveCount(6);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(6);
  await expect(page.getByText("SITE-00", { exact: true })).toHaveCount(0);
  await expect(page.getByText("SITE-07", { exact: true })).toHaveCount(0);

  await facility.selectOption("mock-facility-03");
  await expect(ppu).toHaveValue("mock-facility-03-ppu-01");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  await ppu.selectOption("mock-facility-03-ppu-04");
  await expect(page.getByLabel("Selected Engineering PPU", { exact: true })).toContainText("Server Facility 03 / Server PPU 04");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(8);
});

test("same-URL Connect creates a new session and restores Facility PPU Site topology", async ({ page }) => {
  let sessionRequests = 0;
  let catalogRequests = 0;
  let statusRequests = 0;
  const previousSessionIds: Array<string | undefined> = [];

  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      sessionRequests += 1;
      const body = request.postDataJSON() as { previous_session_id?: string };
      previousSessionIds.push(body.previous_session_id);
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: String(sessionRequests).padStart(32, "0"),
            firmware_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: Boolean(body.previous_session_id),
          },
        }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets") {
      catalogRequests += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }
    const parts = url.pathname.split("/").filter(Boolean);
    if (request.method() === "GET" && parts.slice(5).join("/") === "api/status" && !url.searchParams.has("job")) {
      statusRequests += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(statusFor(parts[3], parts[4])) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled Engineering route" } }) });
  });

  await openProgramming(page);
  await expect(page.getByLabel("Engineering Facility", { exact: true }).locator("option")).toHaveCount(3);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  const sessionsBefore = sessionRequests;
  const catalogsBefore = catalogRequests;
  const statusesBefore = statusRequests;
  await page.locator(".engineeringGateway button[type=submit]").click();

  await expect.poll(() => sessionRequests).toBeGreaterThan(sessionsBefore);
  await expect.poll(() => catalogRequests).toBeGreaterThan(catalogsBefore);
  await expect.poll(() => statusRequests).toBeGreaterThan(statusesBefore);
  await expect(page.getByLabel("Engineering Facility", { exact: true }).locator("option")).toHaveCount(3);
  await expect(page.getByLabel("Engineering PPU", { exact: true }).locator("option")).toHaveCount(4);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  expect(previousSessionIds.at(-1)).toBe(String(sessionsBefore).padStart(32, "0"));
});

test("Engineering EPVR job is posted to the selected Facility and PPU", async ({ page }) => {
  const submissions: Array<{ url: string; body: Record<string, unknown> }> = [];
  let sessionNumber = 0;

  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session") {
      sessionNumber += 1;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, session: { session_id: String(sessionNumber).padStart(32, "0"), firmware_cache_scope: "connection-session-and-ppu", previous_session_cleared: false } }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }

    const parts = url.pathname.split("/").filter(Boolean);
    const facilityId = parts[3];
    const ppuId = parts[4];
    const tail = parts.slice(5).join("/");

    if (request.method() === "GET" && tail === "api/status" && !url.searchParams.has("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(statusFor(facilityId, ppuId)) });
      return;
    }
    if (request.method() === "GET" && tail === "api/status" && url.searchParams.has("job")) {
      const jobId = url.searchParams.get("job")!;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(terminalJob(jobId, 6, "erase")) });
      return;
    }
    if (request.method() === "POST" && tail === "api/jobs") {
      const body = request.postDataJSON() as Record<string, unknown>;
      submissions.push({ url: url.pathname, body });
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job: {
            job_id: "engineering-e2e-job",
            site_id: body.site_id,
            operation: body.operation,
            state: "queued",
            cancel_requested: false,
            stage: null,
            stage_state: null,
            stage_progress_percent: 0,
            progress_percent: 0,
            bytes_done: null,
            bytes_total: null,
          },
        }),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled Engineering route" } }) });
  });

  await openProgramming(page);
  await page.getByLabel("Engineering Facility", { exact: true }).selectOption("mock-facility-02");
  await page.getByLabel("Engineering PPU", { exact: true }).selectOption("mock-facility-02-ppu-03");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(6);

  await page.getByLabel("SITE 6 擦除").click();
  await expect.poll(() => submissions.length).toBe(1);
  expect(submissions[0].url).toBe("/api/engineering/targets/mock-facility-02/mock-facility-02-ppu-03/api/jobs");
  expect(submissions[0].body.site_id).toBe(6);
  expect(submissions[0].body.operation).toBe("erase");
  await expect(page.getByLabel("Engineering job log")).toContainText("SITE-06");
});

test("PPU firmware cache uploads once, probes on reuse, reloads on change and reconnect", async ({ page }) => {
  let sessionNumber = 0;
  let checkCount = 0;
  let uploadCount = 0;
  let jobCount = 0;
  const jobs = new Map<string, { siteId: number; operation: string }>();
  const cache = new Map<string, string>();
  const jobBodies: Array<Record<string, unknown>> = [];

  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      sessionNumber += 1;
      cache.clear();
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: String(sessionNumber).padStart(32, "0"),
            firmware_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: sessionNumber > 1,
          },
        }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }

    const parts = url.pathname.split("/").filter(Boolean);
    const facilityId = parts[3];
    const ppuId = parts[4];
    const targetKey = `${facilityId}/${ppuId}`;
    const tail = parts.slice(5).join("/");

    if (request.method() === "GET" && tail === "api/status" && !url.searchParams.has("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(statusFor(facilityId, ppuId)) });
      return;
    }
    if (request.method() === "GET" && tail === "api/status" && url.searchParams.has("job")) {
      const jobId = url.searchParams.get("job")!;
      const job = jobs.get(jobId)!;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(terminalJob(jobId, job.siteId, job.operation)) });
      return;
    }
    if (request.method() === "POST" && tail === "api/firmware/check") {
      checkCount += 1;
      const body = request.postDataJSON() as { session_id: string; firmware_sha256: string; firmware_name: string; firmware_size: number };
      const cacheKey = `${body.session_id}|${targetKey}`;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          firmware: {
            cache_hit: cache.get(cacheKey) === body.firmware_sha256,
            firmware_name: body.firmware_name,
            firmware_size: body.firmware_size,
            firmware_sha256: body.firmware_sha256,
          },
        }),
      });
      return;
    }
    if (request.method() === "POST" && tail === "api/firmware") {
      uploadCount += 1;
      const sessionId = url.searchParams.get("session_id")!;
      const sha256 = url.searchParams.get("sha256")!;
      cache.set(`${sessionId}|${targetKey}`, sha256);
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, firmware: { cache_hit: true, uploaded: true, firmware_sha256: sha256 } }),
      });
      return;
    }
    if (request.method() === "POST" && tail === "api/jobs") {
      const body = request.postDataJSON() as Record<string, unknown>;
      jobBodies.push(body);
      jobCount += 1;
      const jobId = `cache-job-${jobCount}`;
      jobs.set(jobId, { siteId: Number(body.site_id), operation: String(body.operation) });
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job: {
            job_id: jobId,
            site_id: body.site_id,
            operation: body.operation,
            state: "queued",
            cancel_requested: false,
            stage: null,
            stage_state: null,
            stage_progress_percent: 0,
            progress_percent: 0,
            bytes_done: null,
            bytes_total: null,
          },
        }),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: `unhandled Engineering route ${tail}` } }) });
  });

  await openProgramming(page);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await page.getByLabel("Engineering Firmware file").setInputFiles({
    name: "A.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(1024 * 1024, 0x5a),
  });
  await page.getByLabel("Engineering batch program").check();

  await page.locator(".executeBatch").click();
  await expect.poll(() => jobCount).toBe(2);
  await expect.poll(() => checkCount).toBe(1);
  expect(uploadCount).toBe(1);
  expect(jobBodies.slice(0, 2).every(body => !Object.hasOwn(body, "firmware_base64"))).toBe(true);
  expect(jobBodies.slice(0, 2).every(body => typeof body.firmware_sha256 === "string")).toBe(true);
  await expect.poll(() => page.locator(".executeBatch").isEnabled()).toBe(true);

  await page.locator(".executeBatch").click();
  await expect.poll(() => jobCount).toBe(4);
  await expect.poll(() => checkCount).toBe(2);
  expect(uploadCount).toBe(1);

  await page.getByLabel("Engineering Firmware file").setInputFiles({
    name: "B.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(1024 * 1024, 0xa5),
  });
  await page.locator(".executeBatch").click();
  await expect.poll(() => jobCount).toBe(6);
  await expect.poll(() => checkCount).toBe(3);
  expect(uploadCount).toBe(2);
  await expect.poll(() => page.locator(".executeBatch").isEnabled()).toBe(true);

  const sessionsBeforeReconnect = sessionNumber;
  await page.locator(".engineeringGateway button[type=submit]").click();
  await expect.poll(() => sessionNumber).toBeGreaterThan(sessionsBeforeReconnect);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  await page.locator(".executeBatch").click();
  await expect.poll(() => jobCount).toBe(8);
  await expect.poll(() => checkCount).toBe(4);
  expect(uploadCount).toBe(3);
});
