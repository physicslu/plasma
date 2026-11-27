import { expect, test } from "@playwright/test";
import { mockManager } from "./managed-programming-helpers";

// U10: the Engineering session (and its raw provider error) is gone; EMode
// Programming availability now comes from the Manager's Programming Routes.
// The operator contract is kept: a Manager-side capability fault shows a
// Programming-unavailable notice (with the Manager's exact reason) while the
// Manager backend and the PPU stay ONLINE, and Start stays disabled.

test("EMode reports Programming unavailable as a capability notice and keeps the backend and PPU ONLINE", async ({ page }) => {
  await mockManager(page, { routesStatus: 502 });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "Programming", exact: true }).click();

  const workspace = page.locator('[data-programming-backend="manager"]');
  await expect(workspace.getByTestId("managed-backend")).toContainText("ONLINE");
  await expect(page.locator(".engineeringGateway")).toHaveClass(/online/);

  const availability = page.locator(".engineeringBoundaryNote.warning");
  await expect(availability).toBeVisible();
  await expect(availability.locator("b")).toContainText("ROUTES UNAVAILABLE");
  await expect(page.getByRole("button", { name: /START PROGRAMMING/ })).toBeDisabled();

  await expect(availability.locator(":scope > span")).toContainText("ROUTE_ROOT_UNAVAILABLE");
  await expect(workspace.getByLabel("Selected Engineering PPU")).toContainText("PPU ONLINE");
});
