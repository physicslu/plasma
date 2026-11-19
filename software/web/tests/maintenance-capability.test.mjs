import assert from "node:assert/strict";
import test from "node:test";

import {
  hasMaintenanceCapability,
  issueMaintenanceCapabilityCookie,
  maintenanceCapabilityActor,
  maintenanceCapabilityConfigured,
  maintenanceCapabilityContract,
} from "../app/api/manager/maintenance-capability.mjs";

const ORIGIN = "https://control-station.example.example";
const INTERNAL_ORIGIN = "https://control-station.example.onrender.com";
const ALIAS = "managed-ppu";
const SECRET = "test-maintenance-capability-secret-0123456789abcdef";
const NOW = 1_800_000_000_000;

function request(cookie, origin = ORIGIN) {
  return new Request(`${INTERNAL_ORIGIN}/api/manager/registry/${ALIAS}`, {
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
  const previousOrigin = process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN;
  process.env.PLASMA_MANAGER_REGISTRY_POLICY = "fixed-lifecycle";
  process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET = SECRET;
  process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN = ORIGIN;
  try {
    return run();
  } finally {
    if (previousPolicy === undefined) delete process.env.PLASMA_MANAGER_REGISTRY_POLICY;
    else process.env.PLASMA_MANAGER_REGISTRY_POLICY = previousPolicy;
    if (previousSecret === undefined) delete process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
    else process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET = previousSecret;
    if (previousOrigin === undefined) delete process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN;
    else process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN = previousOrigin;
  }
}

test("fixed lifecycle capability is short-lived, secure, alias-bound and proxy-safe", () => withFixedPolicy(() => {
  assert.equal(maintenanceCapabilityConfigured(), true);
  assert.equal(maintenanceCapabilityContract.publicOriginEnv, "PLASMA_CONTROL_STATION_PUBLIC_ORIGIN");
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
  const previousOrigin = process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN;
  process.env.PLASMA_MANAGER_REGISTRY_POLICY = "fixed-lifecycle";
  process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN = ORIGIN;
  delete process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
  try {
    assert.throws(() => maintenanceCapabilityConfigured(), /MAINTENANCE_CAPABILITY_SECRET/);
    assert.throws(() => hasMaintenanceCapability(request(null), ALIAS, NOW), /MAINTENANCE_CAPABILITY_SECRET/);
  } finally {
    if (previousPolicy === undefined) delete process.env.PLASMA_MANAGER_REGISTRY_POLICY;
    else process.env.PLASMA_MANAGER_REGISTRY_POLICY = previousPolicy;
    if (previousSecret === undefined) delete process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
    else process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET = previousSecret;
    if (previousOrigin === undefined) delete process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN;
    else process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN = previousOrigin;
  }
});

test("fixed lifecycle policy fails closed when canonical public origin is missing or malformed", () => {
  const previousPolicy = process.env.PLASMA_MANAGER_REGISTRY_POLICY;
  const previousSecret = process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
  const previousOrigin = process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN;
  process.env.PLASMA_MANAGER_REGISTRY_POLICY = "fixed-lifecycle";
  process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET = SECRET;
  try {
    delete process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN;
    assert.throws(() => maintenanceCapabilityConfigured(), /PUBLIC_ORIGIN/);
    process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN = "http://control-station.example.example";
    assert.throws(() => maintenanceCapabilityConfigured(), /origin-only HTTPS URL/);
    process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN = `${ORIGIN}/path`;
    assert.throws(() => maintenanceCapabilityConfigured(), /origin-only HTTPS URL/);
  } finally {
    if (previousPolicy === undefined) delete process.env.PLASMA_MANAGER_REGISTRY_POLICY;
    else process.env.PLASMA_MANAGER_REGISTRY_POLICY = previousPolicy;
    if (previousSecret === undefined) delete process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
    else process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET = previousSecret;
    if (previousOrigin === undefined) delete process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN;
    else process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN = previousOrigin;
  }
});

test("mutable non-public registry policy does not require browser capability", () => {
  const previousPolicy = process.env.PLASMA_MANAGER_REGISTRY_POLICY;
  const previousSecret = process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
  const previousOrigin = process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN;
  process.env.PLASMA_MANAGER_REGISTRY_POLICY = "mutable";
  delete process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
  delete process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN;
  try {
    assert.equal(hasMaintenanceCapability(request(null, "https://attacker.example"), ALIAS, NOW), true);
  } finally {
    if (previousPolicy === undefined) delete process.env.PLASMA_MANAGER_REGISTRY_POLICY;
    else process.env.PLASMA_MANAGER_REGISTRY_POLICY = previousPolicy;
    if (previousSecret === undefined) delete process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET;
    else process.env.PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET = previousSecret;
    if (previousOrigin === undefined) delete process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN;
    else process.env.PLASMA_CONTROL_STATION_PUBLIC_ORIGIN = previousOrigin;
  }
});


test("Manual Repeat Continue actor is derived from the verified capability, never the token", () => {
  withFixedPolicy(() => {
    const cookie = cookieHeader(issueMaintenanceCapabilityCookie(ALIAS, NOW));
    const actor = maintenanceCapabilityActor(request(cookie), ALIAS);
    assert.match(actor, /^maintenance-capability:[0-9a-f]{24}$/);
    // Stable for one capability session, distinct per PPU and per capability.
    assert.equal(maintenanceCapabilityActor(request(cookie), ALIAS), actor);
    assert.notEqual(maintenanceCapabilityActor(request(cookie), "other-ppu"), actor);
    const other = cookieHeader(issueMaintenanceCapabilityCookie(ALIAS, NOW));
    assert.notEqual(maintenanceCapabilityActor(request(other), ALIAS), actor);
    // The secret token never appears in the audit identity.
    assert.equal(actor.includes(decodeURIComponent(cookie.split("=")[1])), false);
    assert.equal(maintenanceCapabilityActor(request(null), ALIAS), null);
  });
});
