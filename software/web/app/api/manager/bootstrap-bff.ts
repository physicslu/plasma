import { managerApiBase, managerRoutingRequired, validPpuAlias } from "./manager-bff";
import {
  hasMaintenanceCapability,
  issueMaintenanceCapabilityCookie,
  maintenanceCapabilityConfigured,
  maintenanceCapabilityRequired,
  maintenanceMutationOriginAllowed,
} from "./maintenance-capability.mjs";

const MAX_BOOTSTRAP_BROWSER_REQUEST_BYTES = 2 * 1024 * 1024;
const BOOTSTRAP_TIMEOUT_MS = 45_000;
const UPLOAD_ID = "[0-9a-f]{32}";
const RUN_ID = "[0-9a-f]{32}";
const BOOTSTRAP_POST_ACTIONS = [
  // LOM-P2A-2: local enrollment (button or engineering/SD ticket) replaces
  // the retired manual pairing token; explicit recovery actions need the
  // maintenance capability like every other mutation.
  /^enrollment$/,
  /^recovery$/,
  /^ps-loopback$/,
  /^uploads$/,
  /^deployments$/,
  new RegExp(`^uploads/${UPLOAD_ID}/chunks$`),
  new RegExp(`^uploads/${UPLOAD_ID}/commit$`),
  // Console-driven Bundle programming (Gate 1, 2026-11-09). The Manager builds
  // the Bundle and owns B1/B2/B3 + flash_cycle; the Browser only plans,
  // confirms, starts once and reads the run.
  /^programming\/plans$/,
  /^programming\/runs$/,
  new RegExp(`^programming/runs/${RUN_ID}/acknowledge$`),
  // The EMode Batch and its start are NOT here: a Batch is owned by the
  // Manager, not by a PPU, and lives at /api/manager/programming (PR-C,
  // ADR 5.8). A PPU-scoped run, plan and acknowledgement still belong here.
];
// Read Memory binary of a PASS read run. The Manager re-hashes the bytes
// against the run receipt; the Browser never reads from a PPU.
const READ_OUTPUT_ACTION = new RegExp(`^programming/runs/${RUN_ID}/output$`);
const BOOTSTRAP_GET_ACTIONS = [
  /^$/,
  /^programming\/routes$/,
  new RegExp(`^programming/runs/${RUN_ID}$`),
  READ_OUTPUT_ACTION,
];

// The canonical Manager-owned programming resources. They are not under a
// PPU alias, and they stay under /api/manager so the maintenance capability
// cookie (Path=/api/manager) is still presented with them.
const PROGRAMMING_POST_RESOURCES = [
  /^batches$/,
  new RegExp(`^batches/${RUN_ID}/stop$`),
  /^starts$/,
  new RegExp(`^starts/${RUN_ID}/void$`),
];
const PROGRAMMING_GET_RESOURCES = [
  new RegExp(`^batches/${RUN_ID}$`),
  new RegExp(`^starts/${RUN_ID}$`),
];

function json(status: number, payload: object): Response {
  return Response.json(payload, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function bootstrapActionAllowed(method: string, action: string): boolean {
  if (method === "GET") return BOOTSTRAP_GET_ACTIONS.some(pattern => pattern.test(action));
  if (method !== "POST") return false;
  return BOOTSTRAP_POST_ACTIONS.some(pattern => pattern.test(action));
}

function programmingResourceAllowed(method: string, resource: string): boolean {
  if (method === "GET") return PROGRAMMING_GET_RESOURCES.some(pattern => pattern.test(resource));
  if (method !== "POST") return false;
  return PROGRAMMING_POST_RESOURCES.some(pattern => pattern.test(resource));
}

/** The PPUs a Batch request would operate, or null when it names none. */
function targetAliases(body: ArrayBuffer): string[] | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder().decode(body));
  } catch {
    return null;
  }
  if (parsed == null || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const targets = (parsed as { targets?: unknown }).targets;
  if (!Array.isArray(targets) || targets.length === 0) return null;
  const aliases: string[] = [];
  for (const target of targets) {
    if (target == null || typeof target !== "object" || Array.isArray(target)) return null;
    const alias = (target as { ppu_alias?: unknown }).ppu_alias;
    if (typeof alias !== "string" || !validPpuAlias(alias.trim())) return null;
    aliases.push(alias.trim());
  }
  return aliases;
}

function responseHeaders(response: Response): Headers {
  return new Headers({
    "Cache-Control": response.headers.get("Cache-Control") ?? "no-store",
    "Content-Type": response.headers.get("Content-Type") ?? "application/json",
    "X-Content-Type-Options": "nosniff",
  });
}

function maintenanceCapabilityMisconfigured(): Response {
  return json(503, {
    ok: false,
    error: {
      code: "maintenance_authorization_unavailable",
      message: "Browser maintenance authorization is not configured",
    },
  });
}

export async function relayManagerBootstrapRequest(
  request: Request,
  alias: string,
  action: string,
): Promise<Response> {
  const normalizedAlias = alias.trim();
  const normalizedAction = action.replace(/^\/+|\/+$/g, "");
  if (!validPpuAlias(normalizedAlias)) {
    return json(400, {
      ok: false,
      error: { code: "invalid_alias", message: "PPU registry alias is invalid" },
    });
  }
  if (!bootstrapActionAllowed(request.method, normalizedAction)) {
    return json(404, {
      ok: false,
      error: { code: "bootstrap_route_not_allowed", message: "Bootstrap browser route is not allowlisted" },
    });
  }

  if (request.method === "POST") {
    try {
      maintenanceCapabilityConfigured();
      if (!maintenanceMutationOriginAllowed(request)) return maintenanceCapabilityRequired();
      if (normalizedAction !== "enrollment" && !hasMaintenanceCapability(request, normalizedAlias)) {
        return maintenanceCapabilityRequired();
      }
    } catch {
      return maintenanceCapabilityMisconfigured();
    }
  }

  try {
    if (!managerRoutingRequired()) {
      return json(503, {
        ok: false,
        error: { code: "manager_not_enabled", message: "Manager mode is not enabled for this Control Station" },
      });
    }
    const suffix = normalizedAction ? `/${normalizedAction}` : "";
    const target = `${managerApiBase()}/api/registry/${encodeURIComponent(normalizedAlias)}/bootstrap${suffix}`;
    let body: ArrayBuffer | undefined;
    if (request.method === "POST") {
      body = await request.arrayBuffer();
      if (body.byteLength <= 0 || body.byteLength > MAX_BOOTSTRAP_BROWSER_REQUEST_BYTES) {
        return json(413, {
          ok: false,
          error: { code: "bootstrap_request_too_large", message: "Bootstrap browser request exceeds BFF limit" },
        });
      }
    }
    const response = await fetch(target, {
      method: request.method,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(BOOTSTRAP_TIMEOUT_MS),
    });
    const payload = await response.arrayBuffer();
    const mediaType = (response.headers.get("Content-Type") ?? "").toLowerCase();
    if (request.method === "GET" && READ_OUTPUT_ACTION.test(normalizedAction)
      && response.status === 200 && mediaType.includes("application/octet-stream")) {
      // Only this one route relays a binary, always as a download.
      const digest = response.headers.get("X-Plasma-Read-Sha256") ?? "";
      const disposition = response.headers.get("Content-Disposition") ?? "";
      return new Response(payload, {
        status: 200,
        headers: {
          "Cache-Control": "no-store",
          "Content-Type": "application/octet-stream",
          "Content-Disposition": /^attachment; filename="[A-Za-z0-9._+-]{1,160}"$/.test(disposition)
            ? disposition : 'attachment; filename="read-memory.bin"',
          "X-Content-Type-Options": "nosniff",
          ...(/^[0-9a-f]{64}$/.test(digest) ? { "X-Plasma-Read-Sha256": digest } : {}),
        },
      });
    }
    if (!mediaType.includes("application/json")) {
      return json(response.status >= 400 ? response.status : 502, {
        ok: false,
        error: {
          code: "bootstrap_upstream_non_json",
          message: "Manager Bootstrap route returned a non-JSON response",
          upstream_status: response.status,
        },
      });
    }
    const headers = responseHeaders(response);
    if (request.method === "POST" && normalizedAction === "enrollment" && response.ok) {
      const cookie = issueMaintenanceCapabilityCookie(normalizedAlias);
      if (cookie) headers.set("Set-Cookie", cookie);
    }
    return new Response(payload, { status: response.status, headers });
  } catch {
    return json(503, {
      ok: false,
      error: { code: "manager_unavailable", message: "Manager Bootstrap path is unavailable" },
    });
  }
}

/**
 * The canonical Manager-owned programming resources: the Batch and the start
 * it is admitted with (ADR 5.8). Neither sits under a PPU alias, because
 * neither is owned by a PPU.
 *
 * Authorisation follows what the request actually operates. Starting a Batch
 * submits Jobs to every PPU in its Target Set, so the browser must hold the
 * maintenance capability for EVERY one of them: one Target's enrollment never
 * speaks for another's. Issuing a start, voiding one and stopping the queue
 * reach no PPU at all - they are still refused unless they come from the
 * Control Station's own origin, which is what keeps them off a foreign page.
 */
export async function relayManagerProgrammingRequest(
  request: Request,
  resource: string,
): Promise<Response> {
  const normalizedResource = resource.replace(/^\/+|\/+$/g, "");
  if (!programmingResourceAllowed(request.method, normalizedResource)) {
    return json(404, {
      ok: false,
      error: {
        code: "programming_route_not_allowed",
        message: "Manager programming browser route is not allowlisted",
      },
    });
  }

  let body: ArrayBuffer | undefined;
  if (request.method === "POST") {
    body = await request.arrayBuffer();
    if (body.byteLength <= 0 || body.byteLength > MAX_BOOTSTRAP_BROWSER_REQUEST_BYTES) {
      return json(413, {
        ok: false,
        error: {
          code: "bootstrap_request_too_large",
          message: "Bootstrap browser request exceeds BFF limit",
        },
      });
    }
    try {
      maintenanceCapabilityConfigured();
      if (!maintenanceMutationOriginAllowed(request)) return maintenanceCapabilityRequired();
      if (normalizedResource === "batches") {
        const aliases = targetAliases(body);
        if (aliases === null) {
          return json(400, {
            ok: false,
            error: {
              code: "invalid_request",
              message: "a Batch requires a Target Set naming each PPU it would operate",
            },
          });
        }
        for (const alias of aliases) {
          if (!hasMaintenanceCapability(request, alias)) return maintenanceCapabilityRequired();
        }
      }
    } catch {
      return maintenanceCapabilityMisconfigured();
    }
  }

  try {
    if (!managerRoutingRequired()) {
      return json(503, {
        ok: false,
        error: {
          code: "manager_not_enabled",
          message: "Manager mode is not enabled for this Control Station",
        },
      });
    }
    const response = await fetch(`${managerApiBase()}/api/programming/${normalizedResource}`, {
      method: request.method,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(BOOTSTRAP_TIMEOUT_MS),
    });
    const payload = await response.arrayBuffer();
    const mediaType = (response.headers.get("Content-Type") ?? "").toLowerCase();
    if (!mediaType.includes("application/json")) {
      return json(response.status >= 400 ? response.status : 502, {
        ok: false,
        error: {
          code: "bootstrap_upstream_non_json",
          message: "Manager programming route returned a non-JSON response",
          upstream_status: response.status,
        },
      });
    }
    return new Response(payload, { status: response.status, headers: responseHeaders(response) });
  } catch {
    return json(503, {
      ok: false,
      error: { code: "manager_unavailable", message: "Manager programming path is unavailable" },
    });
  }
}
