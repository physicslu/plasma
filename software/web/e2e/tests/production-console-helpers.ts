import { expect, type Page } from "@playwright/test";

export const factoryConsoleHeading = "PMODE · FACTORY CONSOLE";
export const testTargetIc = "STM32F103C8T6";

const testDevice = {
  vendor: "STMicroelectronics",
  family: "STM32F1",
  subfamily: null,
  plasma_series: "STM32",
  identifier: testTargetIc,
  identifier_kind: "manufacturer_part_number",
  icpn: testTargetIc,
  package: "LQFP48",
  cpu_architectures: ["ARM Cortex-M3"],
  backend: {
    type: "openocd",
    distribution: "upstream-openocd",
    target_config: "tcl/target/stm32f1x.cfg",
    mapping_status: "mapping_candidate",
  },
  physical_validation: {
    engineering_status: "not_verified",
    ppu_status: "no_evidence",
    socket_status: "no_evidence",
  },
  catalog_origin: "test",
};

export function programmingJob(page: Page) {
  return page.getByRole("region", { name: "PROGRAMMING JOB" });
}

export function productionOperation(page: Page, code: "E" | "P" | "V" | "R") {
  const index = { E: 0, P: 1, V: 2, R: 3 }[code];
  return programmingJob(page).locator(".factoryOperationChecks label").nth(index).getByRole("checkbox");
}

export async function installTestDeviceCatalog(page: Page) {
  await page.route("**/api/devices/search**", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        query: testTargetIc,
        ok: true,
        rest_contract_version: "3",
        catalog_size: 1,
        count: 1,
        results: [testDevice],
      }),
    });
  });
}

export async function chooseTestTarget(page: Page) {
  const target = page.getByLabel("Target IC");
  await target.fill(testTargetIc);
  await page.getByRole("option", { name: new RegExp(testTargetIc) }).click();
  await expect(target).toHaveValue(testTargetIc);
}

export async function expandProductionTree(page: Page, facilityIndex = 0, ppuIndices = [0]) {
  const facility = page.locator(".productionTreeFacility").nth(facilityIndex);
  await expect(facility).toBeVisible();
  if (!(await facility.evaluate(element => (element as HTMLDetailsElement).open))) {
    await facility.locator(":scope > summary").click();
  }

  const ppus = facility.locator(".productionTreePpu");
  for (const ppuIndex of ppuIndices) {
    const ppu = ppus.nth(ppuIndex);
    await expect(ppu).toBeVisible();
    if (!(await ppu.evaluate(element => (element as HTMLDetailsElement).open))) {
      await ppu.locator(":scope > summary").click();
    }
  }
}

export async function commitProductionSites(
  page: Page,
  facilityId: string,
  ppuId: string,
  siteIds: number[],
) {
  await expandProductionTree(page);
  for (const siteId of siteIds) {
    await page.getByRole("checkbox", {
      name: `Production Set ${facilityId} ${ppuId} SITE-${String(siteId).padStart(2, "0")}`,
    }).check();
  }
  await page.getByRole("button", { name: "SET PRODUCTION SITES" }).click();
}
