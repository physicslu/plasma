import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

test("Control Station rejects missing or incompatible Manager contract versions", async () => {
  const contract = await fs.readFile(new URL("../app/manager-contract.ts", import.meta.url), "utf8");
  const fleetRoute = await fs.readFile(new URL("../app/api/fleet/route.ts", import.meta.url), "utf8");
  const registryRoute = await fs.readFile(new URL("../app/api/manager/registry/route.ts", import.meta.url), "utf8");
  const registryPathRoute = await fs.readFile(new URL("../app/api/manager/registry/[...path]/route.ts", import.meta.url), "utf8");

  assert.match(contract, /MANAGER_CONTRACT_VERSION\s*=\s*"1"/);
  assert.match(contract, /version !== MANAGER_CONTRACT_VERSION/);
  assert.match(contract, /Unsupported Plasma Manager contract version/);
  assert.match(contract, /requireManagerRegistryContractVersion/);

  assert.match(fleetRoute, /requireManagerContractVersion\(payload\)/);
  assert.match(fleetRoute, /manager_contract_mismatch/);
  assert.ok(
    fleetRoute.indexOf("requireManagerContractVersion(payload)") < fleetRoute.indexOf("sanitizeManagerFleet(payload)"),
    "Manager version must be validated before fleet payload sanitization",
  );

  assert.match(registryRoute, /requireManagerRegistryContractVersion\(payload\)/);
  assert.match(registryRoute, /manager_contract_mismatch/);
  assert.match(registryPathRoute, /requireManagerRegistryContractVersion\(payload\)/);
  assert.match(registryPathRoute, /manager_contract_mismatch/);
});
