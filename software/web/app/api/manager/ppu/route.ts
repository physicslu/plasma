import {
  managerApiBase,
  managerPpuAliasIsCommissioned,
  managerPpuSelectionCookie,
  managerRoutingRequired,
  resolveManagerPpuAlias,
  validPpuAlias,
} from "../manager-bff";

function responseHeaders(extra?: Record<string, string>): HeadersInit {
  return {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    ...(extra ?? {}),
  };
}

export async function GET(request: Request): Promise<Response> {
  let managedRequired = false;
  try {
    managedRequired = managerRoutingRequired();
  } catch {
    return Response.json(
      {
        ok: false,
        managed: true,
        configured: false,
        error: { code: "manager_bff_misconfigured", message: "Managed PPU routing mode is invalid" },
      },
      { status: 503, headers: responseHeaders() },
    );
  }

  if (!managedRequired) {
    return Response.json(
      { ok: true, managed: false, configured: false, ppu_alias: null },
      { status: 200, headers: responseHeaders() },
    );
  }

  try {
    managerApiBase();
    const ppuAlias = await resolveManagerPpuAlias(request);
    return Response.json(
      { ok: true, managed: true, configured: true, ppu_alias: ppuAlias },
      { status: 200, headers: responseHeaders() },
    );
  } catch {
    return Response.json(
      {
        ok: false,
        managed: true,
        configured: false,
        error: { code: "manager_bff_misconfigured", message: "Managed PPU routing is awaiting a PPU selection" },
      },
      { status: 503, headers: responseHeaders() },
    );
  }
}

export async function POST(request: Request): Promise<Response> {
  try {
    if (!managerRoutingRequired()) {
      return Response.json(
        { ok: false, error: { code: "manager_not_enabled", message: "Manager mode is not enabled for this Control Station" } },
        { status: 503, headers: responseHeaders() },
      );
    }
    managerApiBase();
  } catch {
    return Response.json(
      { ok: false, error: { code: "manager_bff_misconfigured", message: "Manager command path is unavailable" } },
      { status: 503, headers: responseHeaders() },
    );
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json(
      { ok: false, error: { code: "invalid_request", message: "Managed PPU selection requires a JSON object" } },
      { status: 400, headers: responseHeaders() },
    );
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return Response.json(
      { ok: false, error: { code: "invalid_request", message: "Managed PPU selection requires a JSON object" } },
      { status: 400, headers: responseHeaders() },
    );
  }
  const record = payload as Record<string, unknown>;
  if (Object.keys(record).length !== 1 || typeof record.ppu_alias !== "string" || !validPpuAlias(record.ppu_alias)) {
    return Response.json(
      { ok: false, error: { code: "invalid_alias", message: "Managed PPU selection requires one valid ppu_alias" } },
      { status: 400, headers: responseHeaders() },
    );
  }
  const alias = record.ppu_alias.trim();

  try {
    if (!await managerPpuAliasIsCommissioned(alias)) {
      return Response.json(
        { ok: false, error: { code: "ppu_not_enabled", message: "PPU must complete Validate & Enable before it can be selected" } },
        { status: 409, headers: responseHeaders() },
      );
    }
  } catch {
    return Response.json(
      { ok: false, error: { code: "manager_unavailable", message: "Manager registry is unavailable" } },
      { status: 503, headers: responseHeaders() },
    );
  }

  return Response.json(
    { ok: true, managed: true, configured: true, ppu_alias: alias },
    {
      status: 200,
      headers: responseHeaders({ "Set-Cookie": managerPpuSelectionCookie(alias) }),
    },
  );
}
