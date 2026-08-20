import { expect, test } from "@playwright/test";

const siteCounts = [2, 4, 6, 8] as const;

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 3,
    ppu_count: 12,
    site_count: 60,
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

test("Engineering Programming topology comes from the Python target catalog", async ({ page }) => {
  await page.route("**/api/engineering/targets**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/engineering/targets") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }

    const parts = url.pathname.split("/").filter(Boolean);
    const facilityId = parts[3];
    const ppuId = parts[4];
    if (route.request().method() === "GET" && parts.slice(5).join("/") === "api/status" && !url.searchParams.has("job")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(statusFor(facilityId, ppuId)) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "unhandled Engineering route" } }) });
  });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
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
  await expect(page.getByText("SITE 0", { exact: true })).toHaveCount(0);
  await expect(page.getByText("SITE 7", { exact: true })).toHaveCount(0);

  await facility.selectOption("mock-facility-03");
  await expect(ppu).toHaveValue("mock-facility-03-ppu-01");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  await ppu.selectOption("mock-facility-03-ppu-04");
  await expect(page.getByLabel("Selected Engineering PPU", { exact: true })).toContainText("Server Facility 03 / Server PPU 04");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(8);
});

test("Engineering EPVR job is posted to the selected Facility and PPU", async ({ page }) => {
  const submissions: Array<{ url: string; body: Record<string, unknown> }> = [];

  await page.route("**/api/engineering/targets**", async route => {
    const request = route.request();
    const url = new URL(request.url());
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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job: {
            job_id: jobId,
            site_id: 6,
            operation: "erase",
            state: "success",
            cancel_requested: false,
            stage: "erase",
            stage_state: "done",
            stage_progress_percent: 100,
            progress_percent: 100,
            bytes_done: null,
            bytes_total: null,
            result: { state: "success", output_files: [] },
          },
        }),
      });
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

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await page.getByLabel("Engineering Facility", { exact: true }).selectOption("mock-facility-02");
  await page.getByLabel("Engineering PPU", { exact: true }).selectOption("mock-facility-02-ppu-03");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(6);

  await page.getByLabel("SITE 6 擦除").click();
  await expect.poll(() => submissions.length).toBe(1);
  expect(submissions[0].url).toBe("/api/engineering/targets/mock-facility-02/mock-facility-02-ppu-03/api/jobs");
  expect(submissions[0].body.site_id).toBe(6);
  expect(submissions[0].body.operation).toBe("erase");
  await expect(page.getByLabel("Engineering job log")).toContainText("SITE 6");
});
