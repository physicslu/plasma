import { relayManagerPpuRequest } from "../../manager-bff";

const MANAGED_BROWSER_PREFIX = "/api/manager/ppu";

function targetPath(request: Request): string {
  const url = new URL(request.url);
  if (!url.pathname.startsWith(`${MANAGED_BROWSER_PREFIX}/`)) return "";
  return url.pathname.slice(MANAGED_BROWSER_PREFIX.length);
}

async function relay(request: Request): Promise<Response> {
  const path = targetPath(request);
  if (!path) {
    return Response.json(
      { ok: false, error: { code: "managed_route_not_allowed", message: "Managed PPU path is invalid" } },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  return await relayManagerPpuRequest(request, path);
}

export async function GET(request: Request): Promise<Response> {
  return await relay(request);
}

export async function POST(request: Request): Promise<Response> {
  return await relay(request);
}
