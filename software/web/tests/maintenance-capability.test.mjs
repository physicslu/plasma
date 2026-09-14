import assert from "node:assert/strict";
import test from "node:test";

import {
  hasMaintenanceCapability,
  issueMaintenanceCapabilityCookie,
  maintenanceCapabilityConfigured,
  maintenanceCapabilityContract,
} from "../app/api/manager/maintenance-capability.mjs";

const ORIGIN = "https://plasma-control-station-lab.example";
const ALIAS = "z2like-qemu";
const SECRET = "test-maintenance-capability-secret-0123456789abcdef";
const NOW = 1_800_000_000_000;

function request(cookie, origin = ORIGIN) {
  return new Request(`${ORIGIN}/api/manager/registry/${ALIAS}`, {
    method: "PATCH",
    headers: {
      Origin: origin,
      ...(cookie ? { Cookie: cookie } : {}),
    },
  });
}

function cookieHeader(setCookie) {
  return setCookie.split(";", 1)[0];
}

function withFixedPolicy(run) {
  const previousPolicy = process.env.PLASMA_MANAGER_REGISTRY_POLICY;
  const previousSecret = process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
  process.env.PLASMA_MANAGER_REGISTRY_POLICY = "fixed-lifecycle";
  process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET = SECRET;
  try {
    return run();
  } finally {
    if (previousPolicy === undefined) delete process.env.PLASMA_MANAGER_REGISTRY_POLICY;
    else process.env.PLASMA_MANAGER_REGISTRY_POLICY = previousPolicy;
    if (previousSecret === undefined) delete process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
    else process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET = previousSecret;
  }
}

test("fixed lifecycle capability is short-lived, secure and alias-bound", () => withFixedPolicy(() => {
  assert.equal(maintenanceCapabilityConfigured(), true);
  const setCookie = issueMaintenanceCapabilityCookie(ALIAS, NOW);
  assert.ok(setCookie);
  assert.match(setCookie, /HttpOnly/);
  assert.match(setCookie, /Secure/);
  assert.match(setCookie, /SameSite=Strict/);
  assert.match(setCookie, /Path=\/api\/manager/);
  assert.match(setCookie, new RegExp(`Max-Age=${maintenanceCapabilityContract.ttlSeconds}`));
  assert.doesNotMatch(setCookie, new RegExp(SECRET));
  assert.doesNotMatch(setCookie, new RegExp(ALIAS));

  const cookie = cookieHeader(setCookie);
  assert.equal(hasMaintenanceCapability(request(cookie), ALIAS, NOW + 1_000), true);
  assert.equal(hasMaintenanceCapability(request(cookie), "other-ppu", NOW + 1_000), false);
  assert.equal(
    hasMaintenanceCapability(request(cookie, "https://attacker.example"), ALIAS, NOW + 1_000),
    false,
  );
  assert.equal(
    hasMaintenanceCapability(request(cookie), ALIAS, NOW + maintenanceCapabilityContract.ttlSeconds * 1000 + 1),
    false,
  );
}));

test("tampered capability fails closed", () => withFixedPolicy(() => {
  const setCookie = issueMaintenanceCapabilityCookie(ALIAS, NOW);
  assert.ok(setCookie);
  const cookie = cookieHeader(setCookie);
  const [name, value] = cookie.split("=", 2);
  const decoded = decodeURIComponent(value);
  const tampered = `${name}=${encodeURIComponent(decoded.slice(0, -1) + (decoded.endsWith("A") ? "B" : "A"))}`;
  assert.equal(hasMaintenanceCapability(request(tampered), ALIAS, NOW + 1_000), false);
}));

test("fixed lifecycle policy fails closed when signing secret is missing", () => {
  const previousPolicy = process.env.PLASMA_MANAGER_REGISTRY_POLICY;
  const previousSecret = process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
  process.env.PLASMA_MANAGER_REGISTRY_POLICY = "fixed-lifecycle";
  delete process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
  try {
    assert.throws(() => maintenanceCapabilityConfigured(), /MAINTENANCE_CAPABILITY_SECRET/);
    assert.throws(() => hasMaintenanceCapability(request(null), ALIAS, NOW), /MAINTENANCE_CAPABILITY_SECRET/);
  } finally {
    if (previousPolicy === undefined) delete process.env.PLASMA_MANAGER_REGISTRY_POLICY;
    else process.env.PLASMA_MANAGER_REGISTRY_POLICY = previousPolicy;
    if (previousSecret === undefined) delete process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
    else process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET = previousSecret;
  }
});

test("mutable non-public registry policy does not require browser capability", () => {
  const previousPolicy = process.env.PLASMA_MANAGER_REGISTRY_POLICY;
  const previousSecret = process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
  process.env.PLASMA_MANAGER_REGISTRY_POLICY = "mutable";
  delete process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
  try {
    assert.equal(hasMaintenanceCapability(request(null, "https://attacker.example"), ALIAS, NOW), true);
  } finally {
    if (previousPolicy === undefined) delete process.env.PLASMA_MANAGER_REGISTRY_POLICY;
    else process.env.PLASMA_MANAGER_REGISTRY_POLICY = previousPolicy;
    if (previousSecret === undefined) delete process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
    else process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET = previousSecret;
  }
});
