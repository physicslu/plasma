import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";

const token = process.env.PPU_BOOTSTRAP_TOKEN ?? "";

test("pending PPU installs Runtime through BFF -> Manager -> independent Bootstrap", async ({ page }) => {
  expect(token.length).toBeGreaterThanOrEqual(32);

  let directManagerRequests = 0;
  let directBootstrapRequests = 0;
  page.on("request", request => {
    const url = new URL(request.url());
    if (url.port === "19881") directManagerRequests += 1;
    if (url.port === "18081") directBootstrapRequests += 1;
  });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "PPU / Sites", exact: true }).click();
  await page.getByRole("button", { name: "Runtime 部署", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Runtime Deployment", level: 2, exact: true })).toBeVisible();
  const targetSelect = page.getByLabel("Manager Registry Alias", { exact: true });
  await expect(targetSelect).toHaveValue("ppu-bootstrap");
  await expect(targetSelect.locator("option:checked")).toHaveText(/ppu-bootstrap — pending/);
  await expect(page.getByText("bootstrap ready", { exact: true })).toBeVisible();
  await expect(page.getByText("runtime absent", { exact: true })).toBeVisible();
  await expect(page.getByText("Reserved / Disabled", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /FPGA|bitstream/i })).toHaveCount(0);

  const tokenInput = page.getByLabel("Bootstrap Pairing Token", { exact: true });
  await tokenInput.fill(token);
  await page.getByRole("button", { name: "Pair Bootstrap", exact: true }).click();
  await expect(page.getByText("Paired", { exact: true })).toBeVisible();
  await expect(tokenInput).toHaveValue("");

  const kitName = "plasma-z2-ps-kit.tar.gz";
  const kitBytes = Buffer.from("full-stack-bootstrap-kit\n");
  const digest = createHash("sha256").update(kitBytes).digest("hex");
  await page.getByLabel("Z2 PS Kit", { exact: true }).setInputFiles({
    name: kitName,
    mimeType: "application/gzip",
    buffer: kitBytes,
  });
  await page.getByLabel("SHA256 Sidecar", { exact: true }).setInputFiles({
    name: `${kitName}.sha256`,
    mimeType: "text/plain",
    buffer: Buffer.from(`${digest}  ${kitName}\n`),
  });

  const deploy = page.getByRole("button", { name: "Deploy Runtime", exact: true });
  await expect(deploy).toBeEnabled();
  await deploy.click();
  await expect(page.getByText(/Runtime deployment accepted by PPU Bootstrap/)).toBeVisible();

  await expect(page.getByRole("heading", { name: "succeeded", exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("runtime active", { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("mock-bootstrap-1.0.0", { exact: true })).toBeVisible();

  expect(directManagerRequests).toBe(0);
  expect(directBootstrapRequests).toBe(0);
});
