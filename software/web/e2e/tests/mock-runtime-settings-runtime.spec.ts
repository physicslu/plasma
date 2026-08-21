import { expect, test } from "@playwright/test";

const gateway = process.env.MOCK_CD_GATEWAY_URL ?? "http://127.0.0.1:19801";

type RuntimeOperation = {
  error_rate_per_mille: number;
  base_time_ms: number;
  throughput_bytes_per_second: number;
  jitter_ms: number;
};

type RuntimeSettings = {
  profile_id: string;
  revision: number;
  enabled: boolean;
  default_image_size_bytes: number;
  operations: Record<"erase" | "program" | "verify" | "read", RuntimeOperation>;
  seed: { mode: "auto" | "fixed"; fixed_seed: number | null };
};

function editable(settings: RuntimeSettings) {
  return {
    enabled: settings.enabled,
    default_image_size_bytes: settings.default_image_size_bytes,
    operations: settings.operations,
    seed: settings.seed,
  };
}

test("real Gateway persists Mock settings and Engineering UI shows the applied revision", async ({ page, request }) => {
  const initialResponse = await request.get(`${gateway}/api/mock/runtime`);
  expect(initialResponse.ok()).toBeTruthy();
  const initialPayload = await initialResponse.json();
  const original = initialPayload.mock_runtime as RuntimeSettings;

  try {
    const changed = {
      ...editable(original),
      default_image_size_bytes: 4 * 1024 * 1024,
      seed: { mode: "fixed" as const, fixed_seed: 4242 },
      operations: {
        ...original.operations,
        program: {
          ...original.operations.program,
          error_rate_per_mille: 0,
        },
      },
    };
    const updateResponse = await request.post(`${gateway}/api/mock/runtime`, { data: changed });
    expect(updateResponse.ok()).toBeTruthy();
    const updatePayload = await updateResponse.json();
    const applied = updatePayload.mock_runtime as RuntimeSettings;
    expect(applied.revision).toBe(original.revision + 1);
    expect(applied.default_image_size_bytes).toBe(4 * 1024 * 1024);
    expect(applied.seed).toEqual({ mode: "fixed", fixed_seed: 4242 });

    await page.goto("/engineering");
    await page.getByRole("button", { name: "Mock", exact: true }).click();
    await expect(page.getByText(`REV ${applied.revision}`, { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Applied Configuration" })).toContainText("fixed · 4242");
    await expect(page.getByRole("region", { name: "Applied Configuration" })).toContainText("4096 KiB");
  } finally {
    const restoreResponse = await request.post(`${gateway}/api/mock/runtime`, { data: editable(original) });
    expect(restoreResponse.ok()).toBeTruthy();
  }
});