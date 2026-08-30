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

function responseHeaders(response: Response, contentLength: number): Headers {
  const headers = new Headers({
    "Cache-Control": response.headers.get("Cache-Control") ?? "no-store",
    "Content-Length": String(contentLength),
    "X-Content-Type-Options": "nosniff",
  });
  for (const name of ["Content-Type", "Content-Disposition"]) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}

export async function relayManagerPpuRequest(request: Request, targetPath: string): Promise<Response> {
  if (!targetPath.startsWith("/api/")) {
    return json(404, {
      ok: false,
      error: { code: "managed_route_not_allowed", message: "Managed PPU path must remain under /api" },
    });
  }

  let managerBase: string;
  let ppuAlias: string;
  try {
    managerBase = managerApiBase();
    ppuAlias = managerPpuAlias();
  } catch {
    return json(503, {
      ok: false,
      error: { code: "manager_bff_misconfigured", message: "Manager command path is unavailable" },
    });
  }

  let body: ArrayBuffer | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = await request.arrayBuffer();
    if (body.byteLength <= 0 || body.byteLength > MAX_MANAGED_REQUEST_BYTES) {
      return json(413, {
        ok: false,
        error: { code: "managed_request_too_large", message: "Managed PPU request body exceeds relay limit" },
      });
    }
  }

  const incoming = new URL(request.url);
  const target = `${managerBase}/api/ppus/${encodeURIComponent(ppuAlias)}/gateway${targetPath}${incoming.search}`;
  try {
    const response = await fetch(target, {
      method: request.method,
      headers: forwardedHeaders(request),
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(MANAGER_TIMEOUT_MS),
    });
    const payload = await response.arrayBuffer();
    return new Response(payload, {
      status: response.status,
      headers: responseHeaders(response, payload.byteLength),
    });
  } catch {
    return json(503, {
      ok: false,
      error: { code: "manager_unavailable", message: "Manager command path is unavailable" },
    });
  }
}
