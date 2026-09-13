import { requireManagerRegistryContractVersion } from "../../../manager-contract";
import { relayManagerRegistryRequest } from "../manager-bff";

async function relayRegistry(request: Request): Promise<Response> {
  const response = await relayManagerRegistryRequest(request);
  if (!response.ok) return response;

  const payload: unknown = await response.json().catch(() => null);
  try {
    requireManagerRegistryContractVersion(payload);
  } catch {
    return Response.json(
      {
        ok: false,
        error: {
          code: "manager_contract_mismatch",
          message: "Manager contract version is unsupported by this Control Station",
        },
      },
      { status: 502, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  }
  return Response.json(payload, {
    status: response.status,
    headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
  });
}

export async function GET(request: Request): Promise<Response> {
  return await relayRegistry(request);
}

export async function POST(request: Request): Promise<Response> {
  return await relayRegistry(request);
}
