const DEFAULT_MANAGER_API_URL = "http://127.0.0.1:18180";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);

function json(status: number, payload: object): Response {
  return Response.json(payload, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function managerApiBase(): string {
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

function managerPpuAlias(): string {
  const alias = (process.env.PLASMA_MANAGER_PPU_ALIAS ?? "").trim();
  if (!alias || alias.length > 128 || alias.includes("/") || alias.includes("\\")) {
    throw new Error("PLASMA_MANAGER_PPU_ALIAS must identify one enrolled PPU alias");
  }
  return alias;
}

export async function POST(request: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json(400, {
      ok: false,
      error: { code: "invalid_request", message: "Loopback request body must be valid JSON" },
    });
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json(400, {
      ok: false,
      error: { code: "invalid_request", message: "Loopback request body must be a JSON object" },
    });
  }
  const endpoint = (body as { endpoint?: unknown }).endpoint;
  if (endpoint !== "ps") {
    return json(400, {
      ok: false,
      error: { code: "unsupported_endpoint", message: "Manager Phase 0 relays PS loopback only" },
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

  try {
    const response = await fetch(
      `${managerBase}/api/ppus/${encodeURIComponent(ppuAlias)}/diagnostics/loopback`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
        cache: "no-store",
        signal: AbortSignal.timeout(125_000),
      },
    );
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      return json(502, {
        ok: false,
        error: { code: "manager_protocol_error", message: "Manager returned an invalid response" },
      });
    }
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return json(502, {
        ok: false,
        error: { code: "manager_protocol_error", message: "Manager returned an invalid response" },
      });
    }
    return json(response.status, payload as object);
  } catch {
    return json(503, {
      ok: false,
      error: { code: "manager_unavailable", message: "Manager command path is unavailable" },
    });
  }
}
