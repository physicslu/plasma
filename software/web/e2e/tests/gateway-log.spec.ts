import { expect, test } from "@playwright/test";

const wrongGateway = "https://wrong-gateway.example.invalid";

test("offline Gateway log always includes the attempted endpoint", async ({ page }) => {
  await page.route("**/api/**", async route => {
    await route.abort("failed");
  });

  await page.goto("/");

  const gatewayInput = page.getByLabel("Plasma Web REST Gateway URL");
  await gatewayInput.fill(wrongGateway);
  await page.getByRole("button", { name: "連線" }).click();

  const offlineLine = page.getByLabel("Live job log").locator("span").filter({
    hasText: "Plasma Web REST Gateway offline",
  });
  await expect(offlineLine).toHaveCount(1);
  await expect(offlineLine).toContainText(wrongGateway);
  await expect(offlineLine).toHaveAttribute("data-level", "error");
});

test("rejected Gateway log includes the invalid endpoint text", async ({ page }) => {
  await page.route("**/api/**", async route => {
    await route.abort("failed");
  });

  await page.goto("/");

  const invalidGateway = "ftp://wrong-gateway.local";
  const gatewayInput = page.getByLabel("Plasma Web REST Gateway URL");
  await gatewayInput.fill(invalidGateway);
  await page.getByRole("button", { name: "連線" }).click();

  const rejectedLine = page.getByLabel("Live job log").locator("span").filter({
    hasText: "Plasma Web REST Gateway rejected",
  });
  await expect(rejectedLine).toHaveCount(1);
  await expect(rejectedLine).toContainText(invalidGateway);
  await expect(rejectedLine).toHaveAttribute("data-level", "error");
});
