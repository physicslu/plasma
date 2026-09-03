import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import {
  programmingJobAction,
  programmingJobField,
  programmingJobOperation,
  programmingJobStatusValue,
} from "./programming-job-test-helpers";
import {
  commitProductionSites,
  factoryConsoleHeading,
  programmingJob,
} from "./production-console-helpers";

const expectedCommit = process.env.EXPECTED_RENDER_COMMIT ?? "";
const facilityId = "mock-facility-01";
const ppuId = `${facilityId}-ppu-01`;

async function requireExpectedDeployment(request: APIRequestContext) {
  if (!expectedCommit) throw new Error("EXPECTED_RENDER_COMMIT is required");

  await expect.poll(
    async () => {
      const response = await request.get("/deployment.json", { timeout: 15_000 });
      if (!response.ok()) return null;
      const payload = await response.json();
      return typeof payload?.git_commit === "string" ? payload.git_commit : null;
    },
    {
      message: `waiting for Render deployment ${expectedCommit}`,
      timeout: 150_000,
      intervals: [1_000, 2_000, 5_000, 5_000, 5_000],
    },
  ).toBe(expectedCommit);

  const ready = await request.get("/api/health/ready", { timeout: 15_000 });
  expect(ready.ok()).toBeTruthy();
  const payload = await ready.json();
  expect(payload).toMatchObject({
    ok: true,
    gateway: "alive",
    execution: "ready",
    ppu_id: "render-demo-ppu",
  });
}

async function expectConstrainedProductionJob(page: Page) {
  const job = programmingJob(page);
  await expect(job).toBeVisible();

  const layout = await job.evaluate(element => {
    const panel = element.getBoundingClientRect();
    const grid = element.querySelector<HTMLElement>("[data-programming-job-fields]")!;
    const operations = element.querySelector<HTMLElement>(
      '[data-programming-job-field="operations"] [role="group"]',
    )!;
    const actionBar = element.querySelector<HTMLElement>("[data-programming-job-actions]")!;
    const operationTops = [...operations.querySelectorAll<HTMLElement>("label")].map(label =>
      label.getBoundingClientRect().top,
    );
    const actions = [...actionBar.querySelectorAll<HTMLElement>("button")].map(button =>
      button.getBoundingClientRect(),
    );

    return {
      gridColumns: getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean).length,
      operationWrap: getComputedStyle(operations).flexWrap,
      operationTopSpread: Math.max(...operationTops) - Math.min(...operationTops),
      panelLeft: panel.left,
      panelRight: panel.right,
      actionLefts: actions.map(rect => rect.left),
      actionRights: actions.map(rect => rect.right),
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth,
    };
  });

  expect(layout.gridColumns).toBeGreaterThanOrEqual(1);
  expect(layout.operationWrap).toBe("nowrap");
  expect(layout.operationTopSpread).toBeLessThanOrEqual(1);
  expect(Math.min(...layout.actionLefts)).toBeGreaterThanOrEqual(layout.panelLeft - 1);
  expect(Math.max(...layout.actionRights)).toBeLessThanOrEqual(layout.panelRight + 1);
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth + 1);
}

test.beforeAll(async ({ request }) => {
  await requireExpectedDeployment(request);
});

test("public Render keeps Production Programming Job contained on iPad landscape", async ({ page }) => {
  await page.setViewportSize({ width: 1194, height: 834 });
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();
  await expectConstrainedProductionJob(page);

  const selection = page.getByRole("region", { name: "PRODUCTION SITE SELECTION" });
  await selection.getByRole("button", { name: /收起|Hide/ }).click();
  await expect(selection.locator(".operatorPanelBody")).toBeHidden();
  await expectConstrainedProductionJob(page);
});

test("public Render uses Mock Synthetic Image without requiring an uploaded Image", async ({ page }) => {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();

  await commitProductionSites(page, facilityId, ppuId, [1]);
  const live = page.getByRole("region", { name: "LIVE SITE STATUS" });
  await expect(live.locator(".factorySiteLedCard")).toHaveCount(1);

  const job = programmingJob(page);
  const program = programmingJobOperation(job, "program");
  const fileName = programmingJobField(job, "image").locator("[data-image-source]");
  const readiness = programmingJobStatusValue(job);
  const execute = programmingJobAction(job, "start");

  if (!(await program.isChecked())) await program.check();
  await expect(fileName).toHaveText("Mock Synthetic Image");
  await expect(fileName).toHaveAttribute("data-image-source", "mock_synthetic");
  await expect(readiness).not.toContainText("IMAGE REQUIRED");

  const readinessText = (await readiness.textContent())?.replace(/\s+/g, " ").trim() ?? "";
  if (readinessText.includes("BATCH READY")) {
    await expect(execute).toBeEnabled();
  } else {
    expect(readinessText).toContain("SITE BUSY");
    await expect(execute).toBeDisabled();
  }

  // Acceptance boundary: do not click START. This verifies the live Image
  // selection contract without creating a Batch, Job, Programming Image
  // upload, or changing Mock Runtime settings on the shared public demo.
});
