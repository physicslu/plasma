import {
  relayManagerNetworkCommissioningRequest,
  relayManagerPpuAliasRequest,
  relayManagerRegistryRequest,
} from "../../manager-bff";

const REGISTRY_BROWSER_PREFIX = "/api/manager/registry";

type RegistryBrowserPath = {
  alias: string;
  resource: "entry" | "network" | "network-commissioning";
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
  if (parts[1] === "network-commissioning") return { alias, resource: "network-commissioning" };
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

async function relayResource(request: Request): Promise<Response> {
  const parsed = registryPath(request);
  if (!parsed || parsed.resource === "entry") {
    return Response.json(
      { ok: false, error: { code: "invalid_registry_resource", message: "PPU registry resource is invalid" } },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }
  if (parsed.resource === "network") {
    return await relayManagerPpuAliasRequest(request, parsed.alias, "/api/settings/ppu-network");
  }
  return await relayManagerNetworkCommissioningRequest(request, parsed.alias);
}

export async function GET(request: Request): Promise<Response> {
  return await relayResource(request);
}

export async function POST(request: Request): Promise<Response> {
  return await relayResource(request);
}

export async function PATCH(request: Request): Promise<Response> {
  return await relayEntry(request);
}

export async function DELETE(request: Request): Promise<Response> {
  return await relayEntry(request);
}
