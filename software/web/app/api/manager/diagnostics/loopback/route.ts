import { relayManagerPpuRequest } from "../../manager-bff";

function json(status: number, payload: object): Response {
  return Response.json(payload, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export async function POST(request: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await request.clone().json();
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
  if ((body as { endpoint?: unknown }).endpoint !== "ps") {
    return json(400, {
      ok: false,
      error: { code: "unsupported_endpoint", message: "PS is the only implemented real-path loopback endpoint" },
    });
  }
  return await relayManagerPpuRequest(request, "/api/engineering/diagnostics/loopback");
}
