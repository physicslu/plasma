import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

const CAPABILITY_COOKIE = "plasma-manager-maintenance";
const CAPABILITY_VERSION = "v1";
const CAPABILITY_TTL_SECONDS = 15 * 60;
const CAPABILITY_SECRET_ENV = "PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET";
const PUBLIC_ORIGIN_ENV = "PLASMA_CONTROL_STATION_PUBLIC_ORIGIN";

function fixedLifecycleRegistry() {
  const policy = (process.env.PLASMA_MANAGER_REGISTRY_POLICY ?? "mutable").trim();
  if (policy === "mutable") return false;
  if (policy === "fixed-lifecycle") return true;
  throw new Error("PLASMA_MANAGER_REGISTRY_POLICY is unsupported");
}

function capabilitySecret() {
  const secret = process.env[CAPABILITY_SECRET_ENV] ?? "";
  if (secret.length < 32 || secret.trim() !== secret) {
    throw new Error(`${CAPABILITY_SECRET_ENV} must contain at least 32 non-whitespace-surrounded characters`);
  }
  return secret;
}

function configuredPublicOrigin() {
  const raw = process.env[PUBLIC_ORIGIN_ENV] ?? "";
  if (!raw || raw.trim() !== raw) {
    throw new Error(`${PUBLIC_ORIGIN_ENV} must contain the canonical HTTPS Control Station origin`);
  }
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error(`${PUBLIC_ORIGIN_ENV} must be a valid absolute HTTPS origin`);
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash ||
    parsed.origin !== raw
  ) {
    throw new Error(`${PUBLIC_ORIGIN_ENV} must be an origin-only HTTPS URL without credentials, path, query, fragment, or trailing slash`);
  }
  return parsed.origin;
}

function signature(alias, expires, nonce) {
  return createHmac("sha256", capabilitySecret())
    .update(`${CAPABILITY_VERSION}\n${alias}\n${expires}\n${nonce}`, "utf8")
    .digest("base64url");
}

function cookieValue(request) {
  const raw = request.headers.get("Cookie") ?? "";
  for (const field of raw.split(";")) {
    const [name, ...parts] = field.trim().split("=");
    if (name !== CAPABILITY_COOKIE) continue;
    try {
      return decodeURIComponent(parts.join("="));
    } catch {
      return null;
    }
  }
  return null;
}

function sameOriginMutation(request) {
  const origin = request.headers.get("Origin");
  if (!origin) return false;
  try {
    return new URL(origin).origin === configuredPublicOrigin();
  } catch {
    return false;
  }
}

export function maintenanceCapabilityRequired() {
  return Response.json(
    {
      ok: false,
      error: {
        code: "maintenance_authorization_required",
        message: "Verify the PPU Bootstrap pairing token before lifecycle or Runtime maintenance",
      },
    },
    {
      status: 403,
      headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
    },
  );
}

export function maintenanceCapabilityConfigured() {
  if (!fixedLifecycleRegistry()) return true;
  capabilitySecret();
  configuredPublicOrigin();
  return true;
}

export function maintenanceMutationOriginAllowed(request) {
  if (!fixedLifecycleRegistry()) return true;
  capabilitySecret();
  configuredPublicOrigin();
  return sameOriginMutation(request);
}

export function issueMaintenanceCapabilityCookie(alias, nowMs = Date.now()) {
  if (!fixedLifecycleRegistry()) return null;
  capabilitySecret();
  const expires = Math.floor(nowMs / 1000) + CAPABILITY_TTL_SECONDS;
  const nonce = randomBytes(24).toString("base64url");
  const token = [CAPABILITY_VERSION, String(expires), nonce, signature(alias, expires, nonce)].join(".");
  return `${CAPABILITY_COOKIE}=${encodeURIComponent(token)}; Path=/api/manager; Max-Age=${CAPABILITY_TTL_SECONDS}; HttpOnly; Secure; SameSite=Strict`;
}

export function hasMaintenanceCapability(request, alias, nowMs = Date.now()) {
  if (!fixedLifecycleRegistry()) return true;
  capabilitySecret();
  configuredPublicOrigin();
  if (!sameOriginMutation(request)) return false;
  const token = cookieValue(request);
  if (!token) return false;
  const parts = token.split(".");
  if (parts.length !== 4 || parts[0] !== CAPABILITY_VERSION) return false;
  const expires = Number(parts[1]);
  const nonce = parts[2];
  const supplied = parts[3];
  if (!Number.isSafeInteger(expires) || !nonce || !supplied || expires <= Math.floor(nowMs / 1000)) return false;
  if (expires > Math.floor(nowMs / 1000) + CAPABILITY_TTL_SECONDS) return false;
  const expected = signature(alias, expires, nonce);
  const actualBuffer = Buffer.from(supplied, "utf8");
  const expectedBuffer = Buffer.from(expected, "utf8");
  return actualBuffer.length === expectedBuffer.length && timingSafeEqual(actualBuffer, expectedBuffer);
}

export const maintenanceCapabilityContract = Object.freeze({
  cookie: CAPABILITY_COOKIE,
  ttlSeconds: CAPABILITY_TTL_SECONDS,
  secretEnv: CAPABILITY_SECRET_ENV,
  publicOriginEnv: PUBLIC_ORIGIN_ENV,
});
