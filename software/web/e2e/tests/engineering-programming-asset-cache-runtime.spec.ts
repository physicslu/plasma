import { expect, test } from "@playwright/test";

const engineeringFacilityId = process.env.MOCK_CD_ENGINEERING_FACILITY_ID ?? "mock-facility-02";
const engineeringPpuId = process.env.MOCK_CD_ENGINEERING_PPU_ID ?? "mock-facility-02-ppu-03";
const engineeringPpuSites = Number(process.env.MOCK_CD_ENGINEERING_PPU_SITES ?? "6");
const targetBase = `/api/engineering/targets/${engineeringFacilityId}/${engineeringPpuId}`;
const oneMiB = Buffer.from(Array.from({ length: 1024 * 1024 }, (_, index) => (index * 29 + 7) & 0xff));

async function selectSitesOneAndTwo(page: import("@playwright/test").Page) {
  for (let siteId = 1; siteId <= engineeringPpuSites; siteId += 1) {
    const checkbox = page.getByLabel(`選取 SITE ${siteId}`);
    const shouldSelect = siteId <= 2;
    if (shouldSelect && !(await checkbox.isChecked())) await checkbox.check();
    if (!shouldSelect && await checkbox.isChecked()) await checkbox.uncheck();
  }
  await expect(page.getByLabel("Engineering Site selection")).toContainText(`2 / ${engineeringPpuSites}`);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);
}

async function runTwoSiteProgram(
  page: import("@playwright/test").Page,
  expectedJobCount: number,
  counters: { jobs: number },
) {
  const execute = page.locator(".executeBatch");
  await expect(execute).toBeEnabled();
  await execute.click();
  await expect.poll(() => counters.jobs, { timeout: 30_000 }).toBe(expectedJobCount);
  await expect(execute).toBeEnabled({ timeout: 30_000 });
}

test("1 MiB Engineering Image Asset uploads once per PPU session and reloads after reconnect", async ({ page }) => {
  const counters = { sessions: 0, checks: 0, uploads: 0, jobs: 0 };
  const sessionBodies: Array<Record<string, unknown>> = [];
  const jobBodies: Array<Record<string, unknown>> = [];

  page.on("request", request => {
    const url = new URL(request.url());
    if (request.method() !== "POST") return;
    if (url.pathname === "/api/engineering/session") {
      counters.sessions += 1;
      sessionBodies.push(request.postDataJSON() as Record<string, unknown>);
      return;
    }
    if (url.pathname === `${targetBase}/api/programming-assets/check`) {
      counters.checks += 1;
      return;
    }
    if (url.pathname === `${targetBase}/api/programming-assets`) {
      counters.uploads += 1;
      return;
    }
    if (url.pathname === `${targetBase}/api/jobs`) {
      counters.jobs += 1;
      jobBodies.push(request.postDataJSON() as Record<string, unknown>);
    }
  });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  const facility = page.getByLabel("Engineering Facility", { exact: true });
  const ppu = page.getByLabel("Engineering PPU", { exact: true });
  await expect(facility.locator("option")).toHaveCount(3, { timeout: 15_000 });
  await facility.selectOption(engineeringFacilityId);
  await ppu.selectOption(engineeringPpuId);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(engineeringPpuSites, { timeout: 15_000 });

  await selectSitesOneAndTwo(page);
  await page.getByLabel("Engineering Programming Image Asset file").setInputFiles({
    name: "engineering-cache-1MiB.bin",
    mimeType: "application/octet-stream",
    buffer: oneMiB,
  });
  await page.getByLabel("Engineering batch program").check();

  const sessionsAtFirstRun = counters.sessions;
  await runTwoSiteProgram(page, 2, counters);
  expect(counters.sessions).toBe(sessionsAtFirstRun);
  expect(counters.checks).toBe(1);
  expect(counters.uploads).toBe(1);
  expect(jobBodies.slice(0, 2).every(body => !Object.hasOwn(body, "asset_base64"))).toBe(true);
  expect(jobBodies.slice(0, 2).every(body => typeof body.asset_sha256 === "string")).toBe(true);
  expect(jobBodies.slice(0, 2).every(body => !Object.hasOwn(body, "image_sha256"))).toBe(true);
  expect(jobBodies.slice(0, 2).every(body => typeof body.session_id === "string")).toBe(true);

  await runTwoSiteProgram(page, 4, counters);
  expect(counters.checks).toBe(2);
  expect(counters.uploads).toBe(1);

  const sessionsBeforeReconnect = counters.sessions;
  await page.locator(".engineeringGateway button[type=submit]").click();
  await expect.poll(() => counters.sessions).toBeGreaterThan(sessionsBeforeReconnect);
  await expect(facility.locator("option")).toHaveCount(3, { timeout: 15_000 });
  await expect(facility).toHaveValue(engineeringFacilityId);
  await expect(ppu).toHaveValue(engineeringPpuId);
  await expect(page.getByLabel("Engineering Site selection")).toContainText(`2 / ${engineeringPpuSites}`);
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2, { timeout: 15_000 });
  expect(sessionBodies.at(-1)?.previous_session_id).toBeTruthy();

  await selectSitesOneAndTwo(page);
  await runTwoSiteProgram(page, 6, counters);
  expect(counters.checks).toBe(3);
  expect(counters.uploads).toBe(2);
});