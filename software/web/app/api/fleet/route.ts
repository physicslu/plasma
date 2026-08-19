import { sanitizeManagerFleet } from "../../fleet/fleet-contract";

const FLEET_UI_ENABLED = process.env.PLASMA_FLEET_UI_ENABLED === "1";
const DEFAULT_MANAGER_API_URL = "http://127.0.0.1:18180";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);

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

function json(status: number, payload: object): Response {
  return Response.json(payload, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export async function GET(): Promise<Response> {
  if (!FLEET_UI_ENABLED) {
    return json(404, {
      ok: false,
      error: { code: "fleet_ui_disabled", message: "Fleet UI is not enabled on this host" },
    });
  }

  let managerBase: string;
  try {
    managerBase = managerApiBase();
  } catch {
    return json(503, {
      ok: false,
      error: { code: "fleet_bff_misconfigured", message: "Fleet data source is unavailable" },
    });
  }

  try {
    const response = await fetch(`${managerBase}/api/fleet`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) {
      return json(503, {
        ok: false,
        error: { code: "manager_unavailable", message: "Fleet data source is unavailable" },
      });
    }
    const payload: unknown = await response.json();
    return json(200, sanitizeManagerFleet(payload));
  } catch {
    return json(503, {
      ok: false,
      error: { code: "manager_unavailable", message: "Fleet data source is unavailable" },
    });
  }
}
