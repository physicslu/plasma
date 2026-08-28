import { expect, test, type Page, type Route } from "@playwright/test";
import {
  expectProgrammingJobDesktopActionGeometry,
  programmingJob as sharedProgrammingJob,
  programmingJobField,
  programmingJobFieldOrder,
  programmingJobOperation,
  programmingJobPolicy,
} from "./programming-job-test-helpers";
import { commitProductionSites, factoryConsoleHeading, programmingJob } from "./production-console-helpers";

const facilityId = "mock-facility-01";
const ppu1Id = `${facilityId}-ppu-01`;
const ppu2Id = `${facilityId}-ppu-02`;

function catalog() {
  return {
    ok: true,
    provider: "mock",
    facility_count: 1,
    ppu_count: 2,
    site_count: 6,
    programming_asset_scope: "connection-session-and-ppu",
    facilities: [{
      facility_id: facilityId,
      display_name: "Mock Facility 01",
      ppus: [
        { ppu_id: ppu1Id, display_name: "Mock PPU 01", model: "MOCK-PPU", site_count: 2, provider: "mock" },
        { ppu_id: ppu2Id, display_name: "Mock PPU 02", model: "MOCK-PPU", site_count: 4, provider: "mock" },
      ],
    }],
  };
}

function targetStatus(ppuId: string) {
  const siteCount = ppuId === ppu1Id ? 2 : 4;
  return {
    ok: true,
    ppu: {
      ppu_id: ppuId,
      facility_id: facilityId,
      model: "MOCK-PPU",
      display_name: ppuId === ppu1Id ? "Mock PPU 01" : "Mock PPU 02",
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

async function installMockProvider(page: Page) {
  await page.route("**/api/settings/gateway", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        gateway_settings: {
          revision: 1,
          ppu_request_timeout_ms: 10_000,
          ppu_retry_count: 3,
          ppu_response_budget_ms: 47_000,
        },
      }),
    });
  });
  await page.route("**/api/engineering/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, session: {
          session_id: "0123456789abcdef0123456789abcdef",
          programming_asset_cache_scope: "connection-session-and-ppu",
          previous_session_cleared: false,
        } }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog()) });
      return;
    }
    const targetMatch = /^\/api\/engineering\/targets\/([^/]+)\/([^/]+)\/api\/status$/.exec(url.pathname);
    if (targetMatch && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(targetStatus(decodeURIComponent(targetMatch[2]))) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

async function background(page: Page, selector: string) {
  return page.locator(selector).first().evaluate(element => getComputedStyle(element).backgroundColor);
}

test("Pmod dark theme covers operator surfaces and keeps shared Programming Job field order", async ({ page }) => {
  await installMockProvider(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await commitProductionSites(page, facilityId, ppu1Id, [1]);
  await expect(page.locator(`[data-production-ppu="${ppu1Id}"]`)).toBeVisible();

  const job = programmingJob(page);
  expect(await programmingJobFieldOrder(job)).toEqual(["target", "image", "operations", "policy"]);

  const targetBox = await programmingJobField(job, "target").boundingBox();
  const imageBox = await programmingJobField(job, "image").boundingBox();
  const operationsBox = await programmingJobField(job, "operations").boundingBox();
  const policyBox = await programmingJobField(job, "policy").boundingBox();
  const actionsBox = await job.locator('[data-programming-job-actions="production"]').boundingBox();
  for (const box of [targetBox, imageBox, operationsBox, policyBox, actionsBox]) expect(box).not.toBeNull();
  expect(targetBox!.y).toBeLessThanOrEqual(imageBox!.y);
  expect(imageBox!.y).toBeLessThanOrEqual(operationsBox!.y);
  expect(operationsBox!.y).toBeLessThanOrEqual(policyBox!.y);
  expect(actionsBox!.y).toBeGreaterThanOrEqual(policyBox!.y + policyBox!.height - 1);

  const theme = page.getByRole("group", { name: "Theme" });
  await theme.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect.poll(() => background(page, ".factoryConsoleV2")).toBe("rgb(7, 17, 29)");
  for (const locator of [
    page.locator(".operatorPanel").first(),
    programmingJobField(job, "image").locator(".programmingJobImageControl"),
    page.locator(".factoryPpuRow").first(),
    page.locator(".factorySiteLedCard").first(),
  ]) {
    await expect.poll(() => locator.evaluate(element => getComputedStyle(element).backgroundColor)).toBe("rgb(12, 25, 39)");
  }
  await expect.poll(() => programmingJobField(job, "operations").locator("label").first().evaluate(element => getComputedStyle(element).backgroundColor)).toBe("rgba(0, 0, 0, 0)");
  const headingColor = await page.locator(".factoryConsoleHeader h1").evaluate(element => getComputedStyle(element).color);
  expect(headingColor).toBe("rgb(255, 255, 255)");
});

test("Pmod Facility packs different-width PPU cards without changing Site card dimensions", async ({ page }) => {
  await installMockProvider(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/fleet");
  await page.getByRole("button", { name: /全選|Select All/ }).click();
  await page.getByRole("button", { name: "SET PRODUCTION SITES" }).click();

  const cards = page.locator(".factoryPpuRow");
  await expect(cards).toHaveCount(2);
  await expect(page.locator(".factorySiteLedCard")).toHaveCount(6);
  const boxes = await cards.evaluateAll(elements => elements.map(element => {
    const rect = element.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width };
  }));
  expect(Math.abs(boxes[0].y - boxes[1].y)).toBeLessThanOrEqual(2);
  expect(boxes[1].x).toBeGreaterThan(boxes[0].x + boxes[0].width);
  expect(boxes[1].width).toBeGreaterThan(boxes[0].width);
  const siteSizes = await page.locator(".factorySiteLedCard").evaluateAll(elements => elements.map(element => {
    const rect = element.getBoundingClientRect();
    return `${Math.round(rect.width)}x${Math.round(rect.height)}`;
  }));
  expect(new Set(siteSizes).size).toBe(1);
});

test("Emode Gateway URL, Connect, and EMode label retain readable Light and Dark theme colors", async ({ page }) => {
  await installMockProvider(page);
  await page.goto("/engineering");
  await page.locator(".engineeringWorkspace nav button").nth(2).click();
  const gateway = page.locator(".engineeringProgrammingV2Header .engineeringGateway");
  await expect(gateway).toBeVisible();

  const readGatewayColors = () => gateway.evaluate(element => {
    const input = element.querySelector("input")!;
    const button = element.querySelector("button")!;
    const label = element.querySelector("b")!;
    return {
      input: getComputedStyle(input).color,
      button: getComputedStyle(button).color,
      label: getComputedStyle(label).color,
      inputOpacity: getComputedStyle(input).opacity,
    };
  });

  expect(await readGatewayColors()).toMatchObject({
    input: "rgb(17, 38, 49)",
    button: "rgb(17, 38, 49)",
    label: "rgb(17, 38, 49)",
    inputOpacity: "1",
  });

  await page.getByRole("group", { name: "Theme" }).getByRole("button", { name: "Dark", exact: true }).click();
  expect(await readGatewayColors()).toMatchObject({
    input: "rgb(233, 243, 248)",
    button: "rgb(233, 243, 248)",
    label: "rgb(233, 243, 248)",
    inputOpacity: "1",
  });
});

test("Emode v2 keeps workspace density while Programming Job follows the shared dark presentation", async ({ page }) => {
  await installMockProvider(page);
  await page.goto("/fleet");
  const theme = page.getByRole("group", { name: "Theme" });
  const darkButton = theme.getByRole("button", { name: "Dark", exact: true });
  await darkButton.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(darkButton).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("plasma-theme"))).toBe("dark");

  await page.goto("/engineering");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator(".engineeringSidebar")).toBeVisible();
  await page.locator(".engineeringWorkspace nav button").nth(2).click();
  const ppuSelect = page.getByLabel("Engineering PPU", { exact: true });
  await expect(ppuSelect).toBeVisible();

  const selectStyle = await ppuSelect.evaluate(element => {
    const style = getComputedStyle(element);
    const optionStyle = getComputedStyle((element as HTMLSelectElement).options[0]);
    return {
      background: style.backgroundColor,
      color: style.color,
      colorScheme: style.colorScheme,
      optionBackground: optionStyle.backgroundColor,
      optionColor: optionStyle.color,
    };
  });
  expect(selectStyle.background).toBe("rgb(12, 25, 39)");
  expect(selectStyle.color).toBe("rgb(233, 243, 248)");
  expect(selectStyle.colorScheme).toContain("dark");
  expect(selectStyle.optionBackground).toBe("rgb(12, 25, 39)");
  expect(selectStyle.optionColor).toBe("rgb(233, 243, 248)");

  const job = sharedProgrammingJob(page, "engineering");
  const imageField = programmingJobField(job, "image");
  const browse = imageField.getByRole("button", { name: "Browse...", exact: true });
  const imageText = imageField.locator("[data-image-source]");
  const browseStyle = await browse.evaluate(element => {
    const style = getComputedStyle(element);
    return {
      height: Number.parseFloat(style.height),
      color: style.color,
      background: style.backgroundColor,
    };
  });
  expect(browseStyle.height).toBeGreaterThanOrEqual(30);
  expect(browseStyle.color).toBe("rgb(233, 243, 248)");
  expect(browseStyle.background).not.toBe("rgba(0, 0, 0, 0)");

  const browseBox = await browse.boundingBox();
  const imageTextBox = await imageText.boundingBox();
  expect(browseBox).not.toBeNull();
  expect(imageTextBox).not.toBeNull();
  expect(imageTextBox!.x).toBeLessThan(browseBox!.x);
  expect(Math.abs(browseBox!.x - (imageTextBox!.x + imageTextBox!.width))).toBeLessThanOrEqual(2);

  const repeat = await programmingJobPolicy(job, "repeat").boundingBox();
  const retry = await programmingJobPolicy(job, "retry").boundingBox();
  const stopPolicy = await programmingJobPolicy(job, "stop").boundingBox();
  const operations = await programmingJobField(job, "operations").boundingBox();
  const policy = await programmingJobField(job, "policy").boundingBox();
  for (const box of [repeat, retry, stopPolicy, operations, policy]) expect(box).not.toBeNull();
  const policyControlY = [repeat!.y, retry!.y, stopPolicy!.y];
  expect(Math.max(...policyControlY) - Math.min(...policyControlY)).toBeLessThanOrEqual(2);
  expect(operations!.y).toBeLessThanOrEqual(policy!.y);
  await expectProgrammingJobDesktopActionGeometry(job);

  await programmingJobOperation(job, "read").check();
  await expect(programmingJobOperation(job, "read")).toBeChecked();

  const passKpi = await page.locator('[data-kpi="pass"]').evaluate(element => {
    const style = getComputedStyle(element);
    return { background: style.backgroundColor, edge: style.borderLeftColor };
  });
  const failKpi = await page.locator('[data-kpi="fail"]').evaluate(element => {
    const style = getComputedStyle(element);
    return { background: style.backgroundColor, edge: style.borderLeftColor };
  });
  expect(passKpi.edge).toBe("rgb(21, 128, 61)");
  expect(failKpi.edge).toBe("rgb(220, 38, 38)");
  expect(passKpi.background).not.toBe(failKpi.background);

  const header = await page.locator(".engineeringProgrammingV2Header").boundingBox();
  const kpis = await page.getByRole("region", { name: "Engineering Batch Summary" }).boundingBox();
  const workflow = await page.locator(".productionProgrammingWorkflow").boundingBox();
  const setup = await page.locator(".targetingCard").boundingBox();
  const jobBox = await job.boundingBox();
  const liveStatus = await page.locator(".liveSiteStatus").boundingBox();
  for (const box of [header, kpis, workflow, setup, jobBox, liveStatus]) expect(box).not.toBeNull();
  expect(header!.height).toBeLessThanOrEqual(90);
  expect(kpis!.height).toBeLessThanOrEqual(180);
  expect(jobBox!.height).toBeGreaterThan(250);
  expect(jobBox!.height).toBeLessThan(400);
  expect(setup!.y + setup!.height).toBeLessThanOrEqual(jobBox!.y);
  expect(jobBox!.y + jobBox!.height).toBeLessThanOrEqual(liveStatus!.y);
  await expect(page.locator(".recentEvents")).toHaveCount(0);
});
