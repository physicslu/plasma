import { expect, test, type APIRequestContext } from "@playwright/test";

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

test("public Render keeps Production batch toolbar stable on iPad landscape", async ({ page }) => {
  await page.setViewportSize({ width: 1194, height: 834 });
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();

  const toolbar = page.getByRole("region", { name: "Batch operation toolbar" });
  await expect(toolbar).toBeVisible();
  await expect(page.getByRole("button", { name: "收起選擇器" })).toBeVisible();

  const expanded = await toolbar.evaluate(element => {
    const toolbarRect = element.getBoundingClientRect();
    const image = element.querySelector<HTMLElement>(".programmingBatchFile")!;
    const operations = element.querySelector<HTMLElement>(".programmingBatchOperations")!;
    const actions = element.querySelector<HTMLElement>(".programmingBatchActions")!;
    const imageRect = image.getBoundingClientRect();
    const operationsRect = operations.getBoundingClientRect();
    const actionsRect = actions.getBoundingClientRect();
    const operationTops = [...operations.querySelectorAll<HTMLElement>("label")].map(label => label.getBoundingClientRect().top);

    return {
      areas: getComputedStyle(element).gridTemplateAreas,
      operationWrap: getComputedStyle(operations).flexWrap,
      operationTopSpread: Math.max(...operationTops) - Math.min(...operationTops),
      toolbarRight: toolbarRect.right,
      actionsRight: actionsRect.right,
      imageBottom: imageRect.bottom,
      operationsBottom: operationsRect.bottom,
      actionsTop: actionsRect.top,
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth,
    };
  });

  expect(expanded.areas).toBe('"image operations" "actions actions"');
  expect(expanded.operationWrap).toBe("nowrap");
  expect(expanded.operationTopSpread).toBeLessThanOrEqual(1);
  expect(expanded.actionsTop).toBeGreaterThanOrEqual(Math.max(expanded.imageBottom, expanded.operationsBottom) - 1);
  expect(expanded.actionsRight).toBeLessThanOrEqual(expanded.toolbarRight + 1);
  expect(expanded.scrollWidth).toBeLessThanOrEqual(expanded.clientWidth + 1);

  await page.getByRole("button", { name: "收起選擇器" }).click();
  await expect(page.getByRole("button", { name: "展開選擇器" })).toBeVisible();
  await page.waitForTimeout(220);

  const collapsed = await toolbar.evaluate(element => ({
    areas: getComputedStyle(element).gridTemplateAreas,
    scrollWidth: element.scrollWidth,
    clientWidth: element.clientWidth,
  }));

  expect(collapsed.areas).toBe('"image operations actions"');
  expect(collapsed.scrollWidth).toBeLessThanOrEqual(collapsed.clientWidth + 1);
});

test("public Render exposes Mock Synthetic Image readiness without submitting a Batch", async ({ page }) => {
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "Factory Production Console" })).toBeVisible();

  const site = page.getByRole("checkbox", { name: `${facilityId} ${ppuId} SITE-01`, exact: true });
  await expect(site).toBeVisible();
  await site.check();
  await page.getByRole("button", { name: "確定選取", exact: true }).click();
  await expect(page.locator(`[data-production-target="${facilityId}::${ppuId}"] [data-production-site="1"]`)).toBeVisible();

  const toolbar = page.locator(".programmingBatchToolbar");
  const operations = toolbar.locator(".programmingBatchOperations input");
  const program = operations.nth(1);
  const fileName = toolbar.locator(".programmingFileName");
  const readiness = toolbar.getByRole("status", { name: "Batch readiness" });
  const execute = toolbar.locator(".executeBatchButton");

  if (!(await program.isChecked())) await program.check();
  await expect(fileName).toHaveText("Mock Synthetic Image");
  await expect(fileName).toHaveAttribute("data-image-source", "mock_synthetic");
  await expect(readiness).toContainText("BATCH READY");
  await expect(execute).toBeEnabled();

  // Acceptance boundary: do not click Execute. This verifies the live UI
  // contract without creating a Batch, Job, Programming Image upload, or
  // changing Mock Runtime settings on the shared public Render demo.
});
