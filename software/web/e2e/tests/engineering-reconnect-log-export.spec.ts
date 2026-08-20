import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

const siteCounts = [2, 4, 6, 8] as const;

function catalog(includeSelectedTarget = true) {
  return {
    ok: true,
    provider: "mock",
    facility_count: 3,
    ppu_count: includeSelectedTarget ? 12 : 11,
    site_count: includeSelectedTarget ? 60 : 54,
    firmware_scope: "connection-session-and-ppu",
    facilities: Array.from({ length: 3 }, (_, facilityIndex) => {
      const facilityNumber = facilityIndex + 1;
      const facilityId = `mock-facility-${String(facilityNumber).padStart(2, "0")}`;
      const ppus = siteCounts.map((siteCount, ppuIndex) => ({
        ppu_id: `${facilityId}-ppu-${String(ppuIndex + 1).padStart(2, "0")}`,
        display_name: `Server PPU ${String(ppuIndex + 1).padStart(2, "0")}`,
        model: "MOCK-PPU",
        site_count: siteCount,
        provider: "mock",
      }));
      return {
        facility_id: facilityId,
        display_name: `Server Facility ${String(facilityNumber).padStart(2, "0")}`,
        ppus: includeSelectedTarget || facilityId !== "mock-facility-02"
          ? ppus
          : ppus.filter(ppu => ppu.ppu_id !== "mock-facility-02-ppu-03"),
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

async function openProgramming(page: import("@playwright/test").Page) {
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
}

test("Reconnect preserves the selected PPU and falls back to Default only when it disappeared", async ({ page }) => {
  let providerOnline = true;
  let includeSelectedTarget = true;
  let sessionNumber = 0;

  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      if (!providerOnline) {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ error: { message: "temporary provider outage" } }),
        });
        return;
      }
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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(catalog(includeSelectedTarget)),
      });
      return;
    }

    const parts = url.pathname.split("/").filter(Boolean);
    if (request.method() === "GET" && parts.slice(5).join("/") === "api/status" && !url.searchParams.has("job")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(statusFor(parts[3], parts[4])),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "unhandled Engineering route" } }),
    });
  });

  await openProgramming(page);
  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  const connect = page.locator(".engineeringGateway button[type=submit]");
  const log = page.getByLabel("Engineering job log");
  const targetRestores = log.locator('span[data-category="SYS"]').filter({ hasText: "[TARGET] RESTORED" });
  const siteRestores = log.locator('span[data-category="SYS"]').filter({ hasText: "[SITE] RESTORED" });

  await facility.selectOption("mock-facility-02");
  await ppu.selectOption("mock-facility-02-ppu-03");
  await expect(facility).toHaveValue("mock-facility-02");
  await expect(ppu).toHaveValue("mock-facility-02-ppu-03");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(6);

  providerOnline = false;
  await connect.click();
  await expect(page.getByText("temporary provider outage", { exact: true })).toBeVisible();

  providerOnline = true;
  await connect.click();
  await expect(facility).toHaveValue("mock-facility-02");
  await expect(ppu).toHaveValue("mock-facility-02-ppu-03");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(6);
  await expect(targetRestores).toHaveCount(1);
  await expect(siteRestores).toHaveCount(1);
  await expect(targetRestores.first()).toContainText("mock-facility-02 / mock-facility-02-ppu-03");
  await expect(siteRestores.first()).toContainText("SITE-01, SITE-02, SITE-03, SITE-04, SITE-05, SITE-06");

  includeSelectedTarget = false;
  await connect.click();
  await expect(facility).toHaveValue("mock-facility-01");
  await expect(ppu).toHaveValue("mock-facility-01-ppu-01");
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
  await expect(targetRestores).toHaveCount(1);
  await expect(siteRestores).toHaveCount(1);
});

test("Engineering Job Log is newest-first and Download .log exports the same order", async ({ page }) => {
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
    if (request.method() === "GET" && parts.slice(5).join("/") === "api/status" && !url.searchParams.has("job")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(statusFor(parts[3], parts[4])),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "unhandled Engineering route" } }),
    });
  });

  await openProgramming(page);
  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  const log = page.getByLabel("Engineering job log");

  await facility.selectOption("mock-facility-02");
  await ppu.selectOption("mock-facility-02-ppu-02");

  const entries = log.locator("span");
  const systemTargets = log.locator('span[data-category="SYS"]').filter({ hasText: "[TARGET]" });
  await expect(systemTargets.nth(0)).toContainText("[TARGET] mock-facility-02 / mock-facility-02-ppu-02");
  await expect(systemTargets.nth(1)).toContainText("[TARGET] mock-facility-02 / mock-facility-02-ppu-01");

  const visibleLines = await entries.allTextContents();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download .log", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^plasma-engineering-\d{8}-\d{6}\.log$/);

  const path = await download.path();
  expect(path).not.toBeNull();
  const fileText = await readFile(path!, "utf8");
  expect(fileText).toBe(`${visibleLines.join("\n")}\n`);

  await page.getByRole("button", { name: "清除", exact: true }).click();
  await expect(entries).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Download .log", exact: true })).toBeDisabled();
});
