import { relayManagerPpuAliasRequest, relayManagerRegistryRequest } from "../../manager-bff";

const REGISTRY_BROWSER_PREFIX = "/api/manager/registry";

type RegistryBrowserPath = {
  alias: string;
  resource: "entry" | "network";
};

function registryPath(request: Request): RegistryBrowserPath | null {
  const url = new URL(request.url);
  if (!url.pathname.startsWith(`${REGISTRY_BROWSER_PREFIX}/`)) return null;
  const encoded = url.pathname.slice(REGISTRY_BROWSER_PREFIX.length + 1);
  if (!encoded) return null;
  const parts = encoded.split("/");
  if (parts.length > 2) return null;
  let alias: string;
  try {
    alias = decodeURIComponent(parts[0] ?? "");
  } catch {
    return null;
  }
  if (!alias || alias.includes("/") || alias.includes("\\")) return null;
  if (parts.length === 1) return { alias, resource: "entry" };
  if (parts[1] === "network") return { alias, resource: "network" };
  return null;
}

async function relayEntry(request: Request): Promise<Response> {
  const parsed = registryPath(request);
  if (!parsed || parsed.resource !== "entry") {
    return Response.json(
      { ok: false, error: { code: "invalid_alias", message: "PPU registry alias is invalid" } },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }
  return await relayManagerRegistryRequest(request, parsed.alias);
}

async function relayNetwork(request: Request): Promise<Response> {
  const parsed = registryPath(request);
  if (!parsed || parsed.resource !== "network") {
    return Response.json(
      { ok: false, error: { code: "invalid_network_route", message: "PPU network route is invalid" } },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }
  return await relayManagerPpuAliasRequest(request, parsed.alias, "/api/settings/ppu-network");
}

export async function GET(request: Request): Promise<Response> {
  return await relayNetwork(request);
}

export async function POST(request: Request): Promise<Response> {
  return await relayNetwork(request);
}

export async function PATCH(request: Request): Promise<Response> {
  return await relayEntry(request);
}

export async function DELETE(request: Request): Promise<Response> {
  return await relayEntry(request);
}
