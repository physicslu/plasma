import { managerApiBase, managerRoutingRequired, validPpuAlias } from "./manager-bff";

const MAX_BOOTSTRAP_BROWSER_REQUEST_BYTES = 2 * 1024 * 1024;
const BOOTSTRAP_TIMEOUT_MS = 45_000;
const UPLOAD_ID = "[0-9a-f]{32}";
const BOOTSTRAP_POST_ACTIONS = [
  /^pair$/,
  /^uploads$/,
  /^deployments$/,
  new RegExp(`^uploads/${UPLOAD_ID}/chunks$`),
  new RegExp(`^uploads/${UPLOAD_ID}/commit$`),
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
  if (method === "GET") return action === "";
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
    return new Response(payload, { status: response.status, headers: responseHeaders(response) });
  } catch {
    return json(503, {
      ok: false,
      error: { code: "manager_unavailable", message: "Manager Bootstrap path is unavailable" },
    });
  }
}
