import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const bff = new URL("../app/api/manager/bootstrap-bff.ts", import.meta.url);
const capability = new URL("../app/api/manager/maintenance-capability.mjs", import.meta.url);
const api = new URL("../app/engineering/ppu-bootstrap-api.ts", import.meta.url);

test("z2like Browser Bootstrap surface remains Manager-owned and maintenance-gated", async () => {
  const [bffSource, capabilitySource, apiSource] = await Promise.all([
    readFile(bff, "utf8"),
    readFile(capability, "utf8"),
    readFile(api, "utf8"),
  ]);

  assert.match(bffSource, /managerApiBase\(\)/);
  assert.match(bffSource, /bootstrapActionAllowed/);
  assert.match(bffSource, /normalizedAction !== "pair" && !hasMaintenanceCapability/);
  assert.match(bffSource, /issueMaintenanceCapabilityCookie/);
  assert.match(bffSource, /maintenanceMutationOriginAllowed/);
  assert.match(capabilitySource, /Origin/);
  assert.match(capabilitySource, /timingSafeEqual/);
  assert.doesNotMatch(bffSource, /CF-Access-Client-Secret/);
  assert.doesNotMatch(bffSource, /Authorization/);
  assert.doesNotMatch(apiSource, /172\.30\.77\.2/);
  assert.doesNotMatch(apiSource, /:18081/);
  assert.match(apiSource, /\/api\/manager\/registry\/\$\{encodeURIComponent\(alias\)\}\/bootstrap/);
});
