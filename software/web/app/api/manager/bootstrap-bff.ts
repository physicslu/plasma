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
  // EMode Batch (Manager-owned Retry / Stop Policy). Stop is "stop queuing".
  /^programming\/batches$/,
  new RegExp(`^programming/batches/${RUN_ID}/stop$`),
];
// Read Memory binary of a PASS read run. The Manager re-hashes the bytes
// against the run receipt; the Browser never reads from a PPU.
const READ_OUTPUT_ACTION = new RegExp(`^programming/runs/${RUN_ID}/output$`);
const BOOTSTRAP_GET_ACTIONS = [
  /^$/,
  /^programming\/routes$/,
  new RegExp(`^programming/runs/${RUN_ID}$`),
  new RegExp(`^programming/batches/${RUN_ID}$`),
  READ_OUTPUT_ACTION,
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
