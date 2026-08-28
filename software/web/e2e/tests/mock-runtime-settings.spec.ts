import { expect, test } from "@playwright/test";

const initialSettings = {
  profile_id: "default",
  revision: 1,
  enabled: true,
  default_image_size_bytes: 262144,
  seed: { mode: "auto", fixed_seed: null },
  operations: {
    erase: { error_rate_per_mille: 1, base_time_ms: 1000, throughput_bytes_per_second: 2097152, jitter_ms: 200 },
    program: { error_rate_per_mille: 50, base_time_ms: 500, throughput_bytes_per_second: 524288, jitter_ms: 200 },
    verify: { error_rate_per_mille: 20, base_time_ms: 300, throughput_bytes_per_second: 1048576, jitter_ms: 100 },
    read: { error_rate_per_mille: 5, base_time_ms: 200, throughput_bytes_per_second: 1048576, jitter_ms: 100 },
  },
};

test("Engineering Mock settings apply per-mille error, timing, seed and show server-applied summary", async ({ page }) => {
  let posted: Record<string, unknown> | null = null;
  await page.route("**/api/mock/runtime", async route => {
    const request = route.request();
    if (request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, rest_contract_version: "3", mock_runtime: initialSettings }),
      });
      return;
    }
    if (request.method() === "POST") {
      posted = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          rest_contract_version: "3",
          mock_runtime: {
            ...initialSettings,
            ...(posted ?? {}),
            revision: 2,
          },
        }),
      });
      return;
    }
    await route.fulfill({ status: 405, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Mock", exact: true }).click();

  await expect(page.getByRole("heading", { name: /^Mock (設定|Settings)$/ })).toBeVisible();
  await expect(page.getByText("REV 1", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Program error rate percent")).toHaveValue("5");
  await expect(page.getByLabel("Program throughput KiB per second")).toHaveValue("512");

  const guide = page.getByRole("region", { name: "Mock Settings Guide" });
  await expect(guide).toBeVisible();
  await expect(guide).toContainText("Mock 設定說明");
  await expect(guide).toContainText("基本 PASS 測試");
  await expect(guide).toContainText("Program Error Rate 設為 100.0%");
  await expect(guide).toContainText("不能宣稱 Z2、FPGA、socket、OpenOCD 或真實 IC programming 已驗證");

  await page.getByLabel("Program error rate percent").fill("7.5");
  await page.getByLabel("Default Image Size (KiB)").fill("4096");
  await page.getByLabel("Seed Mode").selectOption("fixed");
  await page.getByLabel("Fixed Seed").fill("12345");
  await page.getByRole("button", { name: "Apply Settings", exact: true }).click();

  await expect.poll(() => posted).not.toBeNull();
  const body = posted as {
    enabled: boolean;
    default_image_size_bytes: number;
    seed: { mode: string; fixed_seed: number };
    operations: { program: { error_rate_per_mille: number } };
    profile_id?: string;
    revision?: number;
  };
  expect(body.profile_id).toBeUndefined();
  expect(body.revision).toBeUndefined();
  expect(body.default_image_size_bytes).toBe(4 * 1024 * 1024);
  expect(body.seed).toEqual({ mode: "fixed", fixed_seed: 12345 });
  expect(body.operations.program.error_rate_per_mille).toBe(75);

  await expect(page.getByText("REV 2", { exact: true })).toBeVisible();
  const applied = page.getByRole("region", { name: "Applied Configuration" });
  await expect(applied).toContainText("7.5%");
  await expect(applied).toContainText("fixed · 12345");
  await expect(applied).toContainText("4096 KiB");
});
