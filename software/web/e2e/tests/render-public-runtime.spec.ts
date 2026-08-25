import { expect, test, type APIRequestContext } from "@playwright/test";
import {
  commitProductionSites,
  factoryConsoleHeading,
  productionOperation,
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

test.beforeAll(async ({ request }) => {
  await requireExpectedDeployment(request);
});

test("public Render keeps Production Programming Job stable on iPad landscape", async ({ page }) => {
  await page.setViewportSize({ width: 1194, height: 834 });
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();

  const job = programmingJob(page);
  const selection = page.getByRole("region", { name: "PRODUCTION SITE SELECTION" });
  await expect(job).toBeVisible();
  await expect(selection.getByRole("button", { name: /收起|Hide/ })).toBeVisible();

  const geometry = async () => job.evaluate(element => {
    const panel = element.getBoundingClientRect();
    const operations = element.querySelector<HTMLElement>(".factoryOperationChecks")!;
    const actions = element.querySelector<HTMLElement>(".factoryActionBar")!;
    const operationTops = [...operations.querySelectorAll<HTMLElement>("label")].map(label => label.getBoundingClientRect().top);

    return {
      operationWrap: getComputedStyle(operations).flexWrap,
      operationTopSpread: Math.max(...operationTops) - Math.min(...operationTops),
      panelRight: panel.right,
      actionsRight: actions.getBoundingClientRect().right,
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth,
    };
  });

  const expanded = await geometry();
  expect(expanded.operationWrap).toBe("nowrap");
  expect(expanded.operationTopSpread).toBeLessThanOrEqual(1);
  expect(expanded.actionsRight).toBeLessThanOrEqual(expanded.panelRight + 1);
  expect(expanded.scrollWidth).toBeLessThanOrEqual(expanded.clientWidth + 1);

  await selection.getByRole("button", { name: /收起|Hide/ }).click();
  await expect(selection.getByRole("button", { name: /展開|Show/ })).toBeVisible();
  await expect(selection.locator(".operatorPanelBody")).toBeHidden();

  const collapsed = await geometry();
  expect(collapsed.scrollWidth).toBeLessThanOrEqual(collapsed.clientWidth + 1);
});

test("public Render uses Mock Synthetic Image without requiring an uploaded Image", async ({ page }) => {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: factoryConsoleHeading })).toBeVisible();

  await commitProductionSites(page, facilityId, ppuId, [1]);
  await expect(page.locator(`[data-production-ppu="${ppuId}"] [data-production-site="1"]`)).toBeVisible();

  const target = page.getByLabel("Target IC");
  await target.fill("ADUC7019BCPZ62I");
  await expect(page.getByRole("listbox", { name: "Target IC search results" })).toBeVisible();
  await page.getByRole("option", { name: /ADUC7019BCPZ62I/ }).click();

  const job = programmingJob(page);
  const program = productionOperation(page, "P");
  if (!(await program.isChecked())) await program.check();
  await expect(job.locator(".factoryImageControl span")).toHaveText("Mock Synthetic Image");
  const readiness = job.locator(".factoryBatchStatus b");
  const execute = job.locator(".factoryStartButton");
  await expect(readiness).not.toHaveText("IMAGE REQUIRED");

  const readinessText = (await readiness.textContent())?.trim() ?? "";
  if (readinessText === "BATCH READY") {
    await expect(execute).toBeEnabled();
  } else {
    expect(readinessText).toBe("SITE BUSY");
    await expect(execute).toBeDisabled();
  }

  // Acceptance boundary: do not click Execute. This verifies the live Image
  // selection contract without creating a Batch, Job, Programming Image
  // upload, or changing Mock Runtime settings on the shared public demo.
});
