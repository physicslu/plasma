import { relayManagerRegistryRequest } from "../../manager-bff";

const REGISTRY_BROWSER_PREFIX = "/api/manager/registry";

function registryAlias(request: Request): string {
  const url = new URL(request.url);
  if (!url.pathname.startsWith(`${REGISTRY_BROWSER_PREFIX}/`)) return "";
  const encoded = url.pathname.slice(REGISTRY_BROWSER_PREFIX.length + 1);
  if (!encoded || encoded.includes("/")) return "";
  try {
    return decodeURIComponent(encoded);
  } catch {
    return "";
  }
}

async function relay(request: Request): Promise<Response> {
  const alias = registryAlias(request);
  if (!alias) {
    return Response.json(
      { ok: false, error: { code: "invalid_alias", message: "PPU registry alias is invalid" } },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }
  return await relayManagerRegistryRequest(request, alias);
}

export async function PATCH(request: Request): Promise<Response> {
  return await relay(request);
}

export async function DELETE(request: Request): Promise<Response> {
  return await relay(request);
}
