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


test("IC Management retains independent CUSTOMER and OFFICIAL records with same ICPN", async ({ page }) => {
  const local = {
    record: { vendor: "LocalVendor", identifier: "CUSTOM-A", family: "Demo", package: "QFN", flash_size: "64 KB" },
    profile: { profile_id: "custom-v3", operations: ["program"] },
    revision: 3, origin: "LOCAL", verification: "UNVERIFIED",
  };
  const writes: string[] = [];
  await page.route("**/api/manager/catalog/management**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const action = path.split("/").at(-1);
    const respond = (status: number, body: object) => route.fulfill({
      status, contentType: "application/json", body: JSON.stringify(body),
    });
    if (request.method() === "GET" && action === "management") {
      return respond(200, {
        ok: true, local: [local], linked_profiles: [], evidence: [],
        history: { active_revision: "official-rev", revisions: [], audit: [] },
      });
    }
    if (request.method() === "GET" && action === "official") {
      return respond(200, {
        ok: true, record: { vendor: "LocalVendor", identifier: "CUSTOM-A" },
        qualification: { catalog_level: 1 }, revision: "official-rev",
      });
    }
    if (request.method() === "POST" && action === "validate-official") {
      writes.push(action);
      return respond(200, { ok: true, changes: [{ vendor: "LocalVendor", identifier: "CUSTOM-A", status: "MODIFIED" }] });
    }
    return respond(500, { ok: false, error: { message: "Unexpected request" } });
  });
  await page.goto("/ic-management");
  await expect(page.getByText("CUSTOMER IC / UNVERIFIED · r3")).toBeVisible();
  const official = page.locator(".icManagement section").filter({
    has: page.getByRole("heading", { name: "Official Catalog · Validate / Stage / Publish" }),
  });
  await official.getByRole("textbox", { name: "Manufacturer" }).fill("LocalVendor");
  await official.getByRole("textbox", { name: "Exact ICPN" }).fill("CUSTOM-A");
  await official.getByRole("button", { name: "Load official record" }).click();
  await official.getByRole("button", { name: "Validate", exact: true }).click();
  await expect(official.getByRole("button", { name: "Stage" })).toBeEnabled();
  await expect(page.getByText("CUSTOMER IC / UNVERIFIED · r3")).toBeVisible();
  expect(writes).toEqual(["validate-official"]);
});

test("IC Management clearly labels Customer IC, Official IC and linked Customer Profile", async ({ page }) => {
  let linked = false;
  const writes: Array<{ url: string; body: Record<string, unknown> }> = [];
  const local = {
    record: { vendor: "STMicroelectronics", identifier: "STM32F103C8T6",
              family: "Customer F1", package: "LQFP48", flash_size: "64 KiB" },
    profile: { profile_id: "customer-f1", provider_id: "customer", operations: ["program"] },
    origin: "LOCAL", revision: 2, verification: "UNVERIFIED",
  };
  await page.route("**/api/manager/catalog/management**", async route => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    const action = pathname.split("/").at(-1);
    const reply = (status: number, value: object) => route.fulfill({
      status, contentType: "application/json", body: JSON.stringify(value),
    });
    if (request.method() === "GET" && action === "management") {
      return reply(200, {
        ok: true, local: linked ? [] : [local],
        linked_profiles: linked ? [{
          ...local, origin: "CUSTOMER", ic_origin: "OFFICIAL", profile_origin: "CUSTOMER",
          link_status: "ACTIVE",
        }] : [],
        history: { active_revision: "official-rev", revisions: [], audit: [] },
        evidence: [],
      });
    }
    if (request.method() === "GET" && action === "search") {
      return reply(200, { ok: true, total_count: 1, official: [{
        vendor: "STMicroelectronics", identifier: "STM32F103C8T6",
        family: "STM32F1", source: "ST official", level: 3,
      }] });
    }
    if (request.method() === "POST" && action === "link-local-official") {
      writes.push({ url: pathname, body: request.postDataJSON() as Record<string, unknown> });
      linked = true;
      return reply(200, { ok: true, link: {
        profile_id: "customer-f1", ic_origin: "OFFICIAL", profile_origin: "CUSTOMER",
      } });
    }
    return reply(500, { ok: false, error: { message: "Unexpected test request" } });
  });
  await page.goto("/ic-management");
  await expect(page.getByRole("heading", { name: "IC Management" })).toBeVisible();
  await expect(page.getByText("CUSTOMER IC / UNVERIFIED · r2")).toBeVisible();
  await page.locator(".managementList").first().getByRole("button").first().click();
  const link = page.getByRole("button", { name: "Link to Official IC (preserve Customer Profile)" });
  await expect(link).toBeDisabled();
  expect(writes).toHaveLength(0);
  await page.getByRole("checkbox", { name: /I verified that this CUSTOMER IC/ }).check();
  await expect(link).toBeEnabled();
  await link.click();
  await expect(page.getByRole("heading", { name: "Official IC with Customer Profile" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Customer Profiles linked to Official ICs" })).toContainText("OFFICIAL IC");
  await expect(page.getByRole("list", { name: "Customer Profiles linked to Official ICs" })).toContainText("CUSTOMER PROFILE");
  await expect(page.getByRole("list", { name: "Customer Profiles linked to Official ICs" })).toContainText("UNVERIFIED");
  expect(writes).toEqual([{
    url: "/api/manager/catalog/management/link-local-official",
    body: {
      vendor: "STMicroelectronics", icpn: "STM32F103C8T6",
      expected_local_revision: 2, confirmed_same_ic: true,
    },
  }]);
  await page.getByRole("textbox", { name: "Search official ICs" }).fill("STM32F103C8T6");
  await page.getByRole("button", { name: "Search official" }).click();
  await expect(page.getByText(/OFFICIAL IC · CUSTOMER PROFILE · ST official/)).toBeVisible();
});
