const DEFAULT_MANAGER_API_URL = "http://127.0.0.1:18180";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);
const MAX_MANAGED_REQUEST_BYTES = 24 * 1024 * 1024;
const MANAGER_TIMEOUT_MS = 130_000;

function json(status: number, payload: object): Response {
  return Response.json(payload, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export function managerRoutingRequired(): boolean {
  const mode = (process.env.PLASMA_CONTROL_STATION_MODE ?? "").trim();
  if (!mode) return false;
  if (mode !== "managed") {
    throw new Error("PLASMA_CONTROL_STATION_MODE must be managed when configured");
  }
  return true;
}

export function managerApiBase(): string {
  const configured = process.env.PLASMA_MANAGER_API_URL ?? DEFAULT_MANAGER_API_URL;
  const url = new URL(configured);
  if (url.protocol !== "http:") {
    throw new Error("PLASMA_MANAGER_API_URL must use http:// on the local management host");
  }
  if (!LOOPBACK_HOSTS.has(url.hostname)) {
    throw new Error("PLASMA_MANAGER_API_URL must remain loopback-only");
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error("PLASMA_MANAGER_API_URL must not contain credentials, query, or fragment");
  }
  if (url.pathname !== "/") {
    throw new Error("PLASMA_MANAGER_API_URL must identify the Manager root");
  }
  return url.toString().replace(/\/$/, "");
}

export function managerPpuAlias(): string {
  const alias = (process.env.PLASMA_MANAGER_PPU_ALIAS ?? "").trim();
  if (!alias || alias.length > 128 || alias.includes("/") || alias.includes("\\")) {
    throw new Error("PLASMA_MANAGER_PPU_ALIAS must identify one enrolled PPU alias");
  }
  return alias;
}

function forwardedHeaders(request: Request): Headers {
  const headers = new Headers();
  for (const name of ["Accept", "Authorization", "Content-Type", "Idempotency-Key"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}

function responseHeaders(response: Response): Headers {
  const headers = new Headers({
    "Cache-Control": response.headers.get("Cache-Control") ?? "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  for (const name of ["Content-Type", "Content-Disposition"]) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}

async function relayManagerRequest(
  request: Request,
  target: string,
  bodyAllowed: boolean,
  requireManagedMode = false,
): Promise<Response> {
  let managerBase: string;
  try {
    if (requireManagedMode && !managerRoutingRequired()) {
      return json(503, {
        ok: false,
        error: { code: "manager_not_enabled", message: "Manager mode is not enabled for this Control Station" },
      });
    }
    managerBase = managerApiBase();
  } catch {
    return json(503, {
      ok: false,
      error: { code: "manager_bff_misconfigured", message: "Manager command path is unavailable" },
    });
  }

  let body: ArrayBuffer | undefined;
  if (bodyAllowed) {
    body = await request.arrayBuffer();
    if (body.byteLength <= 0 || body.byteLength > MAX_MANAGED_REQUEST_BYTES) {
      return json(413, {
        ok: false,
        error: { code: "managed_request_too_large", message: "Manager request body exceeds relay limit" },
      });
    }
  }

  try {
    const response = await fetch(`${managerBase}${target}`, {
      method: request.method,
      headers: forwardedHeaders(request),
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(MANAGER_TIMEOUT_MS),
    });
    const payload = await response.arrayBuffer();
    return new Response(payload, {
      status: response.status,
      headers: responseHeaders(response),
    });
  } catch {
    return json(503, {
      ok: false,
      error: { code: "manager_unavailable", message: "Manager command path is unavailable" },
    });
  }
}

export async function relayManagerPpuRequest(request: Request, targetPath: string): Promise<Response> {
  if (!targetPath.startsWith("/api/")) {
    return json(404, {
      ok: false,
      error: { code: "managed_route_not_allowed", message: "Managed PPU path must remain under /api" },
    });
  }

  let ppuAlias: string;
  try {
    ppuAlias = managerPpuAlias();
  } catch {
    return json(503, {
      ok: false,
      error: { code: "manager_bff_misconfigured", message: "Manager PPU selection is unavailable" },
    });
  }

  const incoming = new URL(request.url);
  const target = `/api/ppus/${encodeURIComponent(ppuAlias)}/gateway${targetPath}${incoming.search}`;
  const bodyAllowed = request.method !== "GET" && request.method !== "HEAD";
  return await relayManagerRequest(request, target, bodyAllowed);
}

export async function relayManagerRegistryRequest(request: Request, alias?: string): Promise<Response> {
  if (!["GET", "POST", "PATCH", "DELETE"].includes(request.method)) {
    return json(405, {
      ok: false,
      error: { code: "method_not_allowed", message: "Manager registry BFF method is not allowed" },
    });
  }
  if (alias && (!alias.trim() || alias.length > 128 || alias.includes("/") || alias.includes("\\"))) {
    return json(400, {
      ok: false,
      error: { code: "invalid_alias", message: "PPU registry alias is invalid" },
    });
  }
  const suffix = alias ? `/${encodeURIComponent(alias)}` : "";
  const bodyAllowed = request.method === "POST" || request.method === "PATCH";
  return await relayManagerRequest(request, `/api/registry${suffix}`, bodyAllowed, true);
}
