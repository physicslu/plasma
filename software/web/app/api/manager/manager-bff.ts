const DEFAULT_MANAGER_API_URL = "http://127.0.0.1:18180";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);
const MAX_MANAGED_REQUEST_BYTES = 24 * 1024 * 1024;
const MANAGER_TIMEOUT_MS = 130_000;
const MANAGER_SELECTION_TIMEOUT_MS = 5_000;
const MANAGED_PPU_SELECTION_COOKIE = "plasma-manager-ppu-alias";
const MANAGED_BINARY_GET_PATHS = [
  /^\/api\/jobs\/[^/]+\/files\/[^/]+$/,
  /^\/api\/engineering\/targets\/[^/]+\/[^/]+\/api\/jobs\/[^/]+\/files\/[^/]+$/,
];

type RelayResponseContract = "passthrough" | "managed-ppu";

type RegistrySelectionPayload = {
  ppus?: Array<{
    alias?: unknown;
    lifecycle?: unknown;
  }>;
};

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

export function validPpuAlias(alias: string): boolean {
  const normalized = alias.trim();
  return Boolean(normalized && normalized.length <= 128 && !normalized.includes("/") && !normalized.includes("\\"));
}

export function managerPpuAlias(): string {
  const alias = (process.env.PLASMA_MANAGER_PPU_ALIAS ?? "").trim();
  if (!validPpuAlias(alias)) {
    throw new Error("PLASMA_MANAGER_PPU_ALIAS must identify one enrolled PPU alias");
  }
  return alias;
}

function requestPpuAlias(request: Request): string | null {
  const cookie = request.headers.get("Cookie") ?? "";
  for (const field of cookie.split(";")) {
    const [name, ...valueParts] = field.trim().split("=");
    if (name !== MANAGED_PPU_SELECTION_COOKIE) continue;
    try {
      const alias = decodeURIComponent(valueParts.join("=")).trim();
      return validPpuAlias(alias) ? alias : null;
    } catch {
      return null;
    }
  }
  return null;
}

async function commissionedManagerPpuAliases(): Promise<string[]> {
  const response = await fetch(`${managerApiBase()}/api/registry`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal: AbortSignal.timeout(MANAGER_SELECTION_TIMEOUT_MS),
  });
  if (!response.ok) throw new Error("Manager registry is unavailable");
  const payload = await response.json() as RegistrySelectionPayload;
  const aliases = (Array.isArray(payload.ppus) ? payload.ppus : [])
    .filter(entry => entry?.lifecycle === "commissioned")
    .map(entry => typeof entry.alias === "string" ? entry.alias.trim() : "")
    .filter(alias => validPpuAlias(alias));
  return Array.from(new Set(aliases));
}

export async function managerPpuAliasIsCommissioned(alias: string): Promise<boolean> {
  const normalized = alias.trim();
  if (!validPpuAlias(normalized)) return false;
  const aliases = await commissionedManagerPpuAliases();
  return aliases.includes(normalized);
}

export async function resolveManagerPpuAlias(request: Request): Promise<string> {
  const browserSelection = requestPpuAlias(request);
  if (browserSelection) return browserSelection;

  try {
    return managerPpuAlias();
  } catch {
    // Legacy deployment selection is optional. A single commissioned Manager
    // registry entry is an unambiguous bootstrap target.
  }

  const commissionedAliases = await commissionedManagerPpuAliases();
  if (commissionedAliases.length === 1) return commissionedAliases[0];
  throw new Error("Managed PPU selection is unavailable");
}

export function managerPpuSelectionCookie(alias: string): string {
  const normalized = alias.trim();
  if (!validPpuAlias(normalized)) throw new Error("PPU registry alias is invalid");
  return `${MANAGED_PPU_SELECTION_COOKIE}=${encodeURIComponent(normalized)}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000`;
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

function responseMediaType(response: Response): string {
  return (response.headers.get("Content-Type") ?? "")
    .split(";", 1)[0]
    .trim()
    .toLowerCase();
}

function isJsonResponse(response: Response): boolean {
  const mediaType = responseMediaType(response);
  return mediaType === "application/json" || mediaType.endsWith("+json");
}

function managedPpuAllowsBinary(request: Request, targetPath: string): boolean {
  return request.method === "GET" && MANAGED_BINARY_GET_PATHS.some(pattern => pattern.test(targetPath));
}

function isManagedBinaryResponse(response: Response): boolean {
  if (response.headers.get("Content-Disposition")) return true;
  return responseMediaType(response) === "application/octet-stream";
}

function managedPpuResponse(response: Response, payload: ArrayBuffer, allowBinary: boolean): Response {
  if (isJsonResponse(response) || (allowBinary && isManagedBinaryResponse(response)) || response.status === 204) {
    return new Response(payload, {
      status: response.status,
      headers: responseHeaders(response),
    });
  }

  const browserStatus = response.status >= 400 ? response.status : 502;
  return json(browserStatus, {
    ok: false,
    error: {
      code: "managed_upstream_non_json",
      message: "Managed PPU returned a non-JSON response for a JSON API route",
      upstream_status: response.status,
    },
  });
}

async function relayManagerRequest(
  request: Request,
  target: string,
  bodyAllowed: boolean,
  requireManagedMode = false,
  responseContract: RelayResponseContract = "passthrough",
  allowBinaryResponse = false,
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
    if (responseContract === "managed-ppu") {
      return managedPpuResponse(response, payload, allowBinaryResponse);
    }
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
    ppuAlias = await resolveManagerPpuAlias(request);
  } catch {
    return json(503, {
      ok: false,
      error: { code: "manager_bff_misconfigured", message: "Manager PPU selection is unavailable" },
    });
  }

  const incoming = new URL(request.url);
  const target = `/api/ppus/${encodeURIComponent(ppuAlias)}/gateway${targetPath}${incoming.search}`;
  const bodyAllowed = request.method !== "GET" && request.method !== "HEAD";
  return await relayManagerRequest(
    request,
    target,
    bodyAllowed,
    false,
    "managed-ppu",
    managedPpuAllowsBinary(request, targetPath),
  );
}

export async function relayManagerPpuAliasRequest(
  request: Request,
  alias: string,
  targetPath: string,
): Promise<Response> {
  const normalizedAlias = alias.trim();
  if (!validPpuAlias(normalizedAlias)) {
    return json(400, {
      ok: false,
      error: { code: "invalid_alias", message: "PPU registry alias is invalid" },
    });
  }
  if (!targetPath.startsWith("/api/")) {
    return json(404, {
      ok: false,
      error: { code: "managed_route_not_allowed", message: "Managed PPU path must remain under /api" },
    });
  }
  const incoming = new URL(request.url);
  const target = `/api/ppus/${encodeURIComponent(normalizedAlias)}/gateway${targetPath}${incoming.search}`;
  const bodyAllowed = request.method !== "GET" && request.method !== "HEAD";
  return await relayManagerRequest(
    request,
    target,
    bodyAllowed,
    true,
    "managed-ppu",
    managedPpuAllowsBinary(request, targetPath),
  );
}

export async function relayManagerRegistryRequest(request: Request, alias?: string): Promise<Response> {
  if (!["GET", "POST", "PATCH", "DELETE"].includes(request.method)) {
    return json(405, {
      ok: false,
      error: { code: "method_not_allowed", message: "Manager registry BFF method is not allowed" },
    });
  }
  if (alias && !validPpuAlias(alias)) {
    return json(400, {
      ok: false,
      error: { code: "invalid_alias", message: "PPU registry alias is invalid" },
    });
  }
  const suffix = alias ? `/${encodeURIComponent(alias)}` : "";
  const bodyAllowed = request.method === "POST" || request.method === "PATCH";
  return await relayManagerRequest(request, `/api/registry${suffix}`, bodyAllowed, true);
}

export async function relayManagerNetworkCommissioningRequest(
  request: Request,
  alias: string,
): Promise<Response> {
  const normalizedAlias = alias.trim();
  if (!validPpuAlias(normalizedAlias)) {
    return json(400, {
      ok: false,
      error: { code: "invalid_alias", message: "PPU registry alias is invalid" },
    });
  }
  if (!["GET", "POST"].includes(request.method)) {
    return json(405, {
      ok: false,
      error: { code: "method_not_allowed", message: "Network commissioning supports GET and POST only" },
    });
  }
  const target = `/api/registry/${encodeURIComponent(normalizedAlias)}/network-commissioning`;
  return await relayManagerRequest(request, target, request.method === "POST", true);
}
