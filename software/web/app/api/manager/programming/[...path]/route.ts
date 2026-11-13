import { relayManagerProgrammingRequest } from "../../bootstrap-bff";

const PROGRAMMING_BROWSER_PREFIX = "/api/manager/programming";

/** The resource under the canonical prefix, or null when the path is not one. */
function programmingResource(request: Request): string | null {
  const url = new URL(request.url);
  if (!url.pathname.startsWith(`${PROGRAMMING_BROWSER_PREFIX}/`)) return null;
  const encoded = url.pathname.slice(PROGRAMMING_BROWSER_PREFIX.length + 1);
  if (!encoded) return null;
  const parts = encoded.split("/");
  // batches | batches/<id> | batches/<id>/stop | starts | starts/<id> | starts/<id>/void
  if (parts.length > 3 || parts.some(part => !part)) return null;
  try {
    return parts.map(part => decodeURIComponent(part)).join("/");
  } catch {
    return null;
  }
}

async function relay(request: Request): Promise<Response> {
  const resource = programmingResource(request);
  if (resource === null) {
    return Response.json(
      {
        ok: false,
        error: {
          code: "programming_route_not_allowed",
          message: "Manager programming browser route is not allowlisted",
        },
      },
      { status: 404, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  }
  return await relayManagerProgrammingRequest(request, resource);
}

export async function GET(request: Request): Promise<Response> {
  return await relay(request);
}

export async function POST(request: Request): Promise<Response> {
  return await relay(request);
}
