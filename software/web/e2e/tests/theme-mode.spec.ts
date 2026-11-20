import { expect, test } from "@playwright/test";
import {
  programmingJob,
  programmingJobField,
  programmingJobFieldOrder,
} from "./programming-job-test-helpers";

async function installEmptyEngineeringCatalog(page: import("@playwright/test").Page) {
  await page.route("**/api/engineering/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/engineering/session" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: "0123456789abcdef0123456789abcdef",
            programming_asset_cache_scope: "connection-session-and-ppu",
            previous_session_cleared: false,
          },
        }),
      });
      return;
    }
    if (url.pathname === "/api/engineering/targets" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          provider: "mock",
          facility_count: 0,
          ppu_count: 0,
          site_count: 0,
          programming_asset_scope: "connection-session-and-ppu",
          facilities: [],
        }),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false }) });
  });
}

test("Pmod image controls precede EPVR and Pmod Emode share persistent Light Dark preference", async ({ page }) => {
  await installEmptyEngineeringCatalog(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: "PMODE · FACTORY CONSOLE" })).toBeVisible();

  const panel = programmingJob(page, "production");
  await expect(panel).toBeVisible();
  expect(await programmingJobFieldOrder(panel)).toEqual([
    "target",
    "image",
    "operations",
    "policy",
  ]);
  const imageBox = await programmingJobField(panel, "image").boundingBox();
  const operationsBox = await programmingJobField(panel, "operations").boundingBox();
  expect(imageBox).not.toBeNull();
  expect(operationsBox).not.toBeNull();
  expect(imageBox!.y + imageBox!.height).toBeLessThanOrEqual(operationsBox!.y);

  const theme = page.getByRole("group", { name: "Theme" });
  await expect(theme.getByRole("button", { name: "Light", exact: true })).toHaveAttribute("aria-pressed", "true");
  await theme.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(theme.getByRole("button", { name: "Dark", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("plasma-theme"))).toBe("dark");
  await expect.poll(() => page.locator(".factoryConsoleV2").evaluate(element => getComputedStyle(element).backgroundColor)).toBe("rgb(7, 17, 29)");

  await page.goto("/engineering");
  await expect(page.getByRole("heading", { name: /Engineering/i })).toBeVisible();
  const engineeringTheme = page.getByRole("group", { name: "Theme" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(engineeringTheme.getByRole("button", { name: "Dark", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => page.locator(".engineeringPage").evaluate(element => getComputedStyle(element).backgroundColor)).toBe("rgb(9, 22, 34)");
  await expect(page.locator(".engineeringSidebar")).toBeVisible();

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("group", { name: "Theme" }).getByRole("button", { name: "Dark", exact: true })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("group", { name: "Theme" }).getByRole("button", { name: "Light", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("plasma-theme"))).toBe("light");
});

test("IC Management input fields retain readable Light and Dark text, placeholders, and caret", async ({ page }) => {
  // Mock only catalog reads: the test does not publish records or contact a PPU.
  await page.route("**/api/manager/catalog/management**", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      ok: true, local: [], evidence: [],
      history: { active_revision: null, revisions: [], audit: [] },
    }),
  }));
  await page.goto("/ic-management");
  await expect(page.getByRole("heading", { name: "IC Management" })).toBeVisible();

  const localSearch = page.getByRole("textbox", { name: "Search local ICs" });
  const officialSearch = page.getByRole("textbox", { name: "Search official ICs" });
  const manufacturer = page.getByRole("textbox", { name: "Manufacturer" });
  const icpn = page.getByRole("textbox", { name: "Exact ICPN" });
  const theme = page.locator(".icManagement").getByRole("group", { name: "Theme" });

  const assertPalette = async (background: string, foreground: string, placeholder: string) => {
    for (const input of [localSearch, officialSearch, manufacturer, icpn]) {
      await expect(input).toBeVisible();
      const colors = await input.evaluate(element => {
        const style = getComputedStyle(element);
        return { background: style.backgroundColor, text: style.color, caret: style.caretColor };
      });
      expect(colors).toEqual({ background, text: foreground, caret: foreground });
      // Regression: the old hard-coded dark fallback must never reappear.
      expect(colors.background).not.toBe("rgb(16, 28, 36)");
    }
    for (const input of [localSearch, officialSearch]) {
      expect(await input.evaluate(element => getComputedStyle(element, "::placeholder").color)).toBe(placeholder);
    }
  };

  await theme.getByRole("button", { name: "Light", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await assertPalette("rgb(247, 250, 251)", "rgb(17, 38, 49)", "rgb(95, 116, 130)");

  await manufacturer.fill("STM32");
  await theme.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await assertPalette("rgb(10, 23, 35)", "rgb(233, 243, 248)", "rgb(120, 144, 165)");
  await expect(manufacturer).toHaveValue("STM32");

  await theme.getByRole("button", { name: "Light", exact: true }).click();
  await assertPalette("rgb(247, 250, 251)", "rgb(17, 38, 49)", "rgb(95, 116, 130)");
});


test("IC Management explains Official versus Local ICPN conflicts without deleting customer data", async ({ page }) => {
  const mutatingRequests: string[] = [];
  const local = {
    record: { vendor: "LocalVendor", identifier: "CUSTOM-A", family: "Demo", package: "QFN", flash_size: "64 KB" },
    profile: { profile_id: "custom-v3", operations: ["program"] },
    revision: 3, origin: "LOCAL", verification: "UNVERIFIED",
  };
  await page.route("**/api/manager/catalog/management**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const action = url.pathname.split("/").at(-1);
    const response = (status: number, body: object) => route.fulfill({
      status, contentType: "application/json", body: JSON.stringify(body),
    });
    if (request.method() === "GET" && action === "management") {
      return response(200, {
        ok: true, local: [local], evidence: [],
        history: { active_revision: "previous-revision", revisions: [], audit: [] },
      });
    }
    if (request.method() === "GET" && action === "official") {
      return response(200, {
        ok: true, record: { vendor: "LocalVendor", identifier: "CUSTOM-A" },
        qualification: { catalog_level: 1 }, revision: "previous-revision",
      });
    }
    if (request.method() === "POST" && action === "validate-official") {
      return response(409, {
        ok: false, error: {
          code: "CATALOG_LOCAL_IDENTITY_CONFLICT",
          message: "Official Catalog update blocked: 1 customer-owned local exact ICPN conflict(s); resolve the local identities explicitly before retrying",
          conflict_count: 1, truncated: false,
          conflicts: [{
            manufacturer: "LocalVendor", exact_icpn: "CUSTOM-A",
            local_revision: 3, local_profile_id: "custom-v3",
          }],
        },
      });
    }
    if (request.method() === "POST") mutatingRequests.push(url.pathname);
    return response(500, { ok: false, error: { message: "Unexpected test request" } });
  });

  await page.goto("/ic-management");
  await expect(page.getByRole("heading", { name: "IC Management" })).toBeVisible();
  const official = page.locator(".icManagement section").filter({
    has: page.getByRole("heading", { name: "Official Catalog · Validate / Stage / Publish" }),
  });
  await official.getByRole("textbox", { name: "Manufacturer" }).fill("LocalVendor");
  await official.getByRole("textbox", { name: "Exact ICPN" }).fill("CUSTOM-A");
  await official.getByRole("button", { name: "Load official record" }).click();
  await expect(official.getByText("Editing candidate from revision")).toBeVisible();
  await official.getByRole("button", { name: "Validate", exact: true }).click();

  const alert = page.getByRole("alert", { name: "Catalog identity conflict" });
  await expect(alert).toBeVisible();
  await expect(alert).toContainText("1 customer part number conflict(s)");
  await expect(alert).toContainText("LocalVendor · CUSTOM-A");
  await expect(alert).toContainText("LOCAL r3 · Profile custom-v3");
  await expect(alert).toContainText("Nothing is automatically renamed, deleted, or promoted.");
  await expect(alert.getByRole("button", { name: "Export Local Catalog JSON" })).toBeVisible();
  await alert.getByRole("button", { name: "View customer IC" }).click();
  const editor = page.locator("#local-ic-editor");
  await expect(editor.getByRole("textbox", { name: "identifier" })).toHaveValue("CUSTOM-A");
  await expect(editor.getByRole("textbox", { name: "Profile ID" })).toHaveValue("custom-v3");
  await expect(official.getByRole("button", { name: "Stage" })).toBeDisabled();
  expect(mutatingRequests).toEqual([]);
});
