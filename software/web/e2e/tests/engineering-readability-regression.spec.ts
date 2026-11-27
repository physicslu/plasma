import { expect, test, type Locator, type Page } from "@playwright/test";
import { Z2, mockManager } from "./managed-programming-helpers";
import {
  expectProgrammingJobContract,
  programmingJob,
} from "./programming-job-test-helpers";

// U10: Manager-managed only; the Mock Manager answers at the Browser boundary.
async function installEngineeringApi(page: Page) {
  await mockManager(page, { ppus: [{ ...Z2, enabledSites: [1, 2], siteCount: 2 }] });
}

async function headerSignature(locator: Locator) {
  return locator.evaluate(element => {
    const style = getComputedStyle(element);
    return {
      minHeight: style.minHeight,
      paddingTop: style.paddingTop,
      paddingBottom: style.paddingBottom,
      paddingLeft: style.paddingLeft,
      paddingRight: style.paddingRight,
    };
  });
}

async function titleSignature(locator: Locator) {
  return locator.evaluate(element => {
    const style = getComputedStyle(element);
    return {
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      letterSpacing: style.letterSpacing,
    };
  });
}

test("Engineering first-level Panel titles share one operator header baseline while body typography stays readable", async ({ page }) => {
  await installEngineeringApi(page);
  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single PPU Programming" })).toBeVisible();
  await expect(page.locator(".channelTable tbody tr")).toHaveCount(2);

  const job = programmingJob(page, "engineering");
  await expectProgrammingJobContract(job);

  const headers = [
    page.locator(".batchSummary > .operatorPanelHeader"),
    page.locator(".targetingCard > header"),
    job.locator(":scope > .operatorPanelHeader"),
    page.locator(".liveSiteStatus > header"),
    page.locator(".engineeringOperatorLog > .operatorPanelHeader"),
  ];
  for (const header of headers) await expect(header).toBeVisible();

  const baselineHeader = await headerSignature(headers[0]);
  expect(baselineHeader).toMatchObject({
    minHeight: "30px",
    paddingTop: "5px",
    paddingBottom: "5px",
    paddingLeft: "8px",
    paddingRight: "8px",
  });
  for (const header of headers.slice(1)) {
    expect(await headerSignature(header)).toEqual(baselineHeader);
  }

  const titles = [
    page.locator(".batchSummary .operatorPanelTitle > strong"),
    page.locator(".targetingCard .operatorPanelTitle > strong"),
    job.locator(".operatorPanelTitle > strong"),
    page.locator(".liveSiteStatus .operatorPanelTitle > strong"),
    page.locator(".engineeringOperatorLog .operatorPanelTitle > strong"),
  ];
  const baselineTitle = await titleSignature(titles[0]);
  expect(baselineTitle.fontSize).toBe("11px");
  expect(baselineTitle.fontWeight).toBe("900");
  for (const title of titles.slice(1)) {
    expect(await titleSignature(title)).toEqual(baselineTitle);
  }

  // Section numbers come from the shared header, not from CSS generated content.
  await expect(page.locator(".targetingCard .operatorPanelTitle")).toHaveText(/^1\.\s*SYSTEM SETUP & TARGETING$/);
  await expect(page.locator(".liveSiteStatus .operatorPanelTitle")).toHaveText(/^3\.\s*LIVE SITE STATUS/);
  await expect(job.locator(".operatorPanelTitle")).toHaveText(/^2\.\s*PROGRAMMING JOB$/);
  await expect(page.locator(".engineeringOperatorLog .operatorPanelTitle")).toHaveText(/^4\.\s*ENGINEERING JOB LOG$/);

  const setupLabels = page.locator(".targetingCard .workflowField > span");
  await expect(setupLabels).toHaveCount(2);
  for (let index = 0; index < 2; index += 1) {
    expect(await setupLabels.nth(index).evaluate(element => getComputedStyle(element).fontSize)).toBe("12px");
  }

  const jobLabels = job.locator('[data-programming-job-field] > strong');
  await expect(jobLabels).toHaveCount(4);
  for (let index = 0; index < 4; index += 1) {
    expect(await jobLabels.nth(index).evaluate(element => getComputedStyle(element).fontSize)).toBe("11px");
  }

  const siteNames = page.locator(".channelTable tbody td:nth-child(2) b");
  await expect(siteNames).toHaveCount(2);
  await expect(siteNames.nth(0)).toHaveText("SITE-01");
  await expect(siteNames.nth(1)).toHaveText("SITE-02");
});
