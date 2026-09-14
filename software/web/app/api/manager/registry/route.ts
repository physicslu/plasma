import { requireManagerRegistryContractVersion } from "../../../manager-contract";
import { relayManagerRegistryRequest } from "../manager-bff";

function fixedLifecycleRegistry(): boolean {
  const policy = (process.env.PLASMA_MANAGER_REGISTRY_POLICY ?? "mutable").trim();
  if (policy === "mutable") return false;
  if (policy === "fixed-lifecycle") return true;
  throw new Error("PLASMA_MANAGER_REGISTRY_POLICY is unsupported");
}

function fixedRegistryMutationRejected(): Response {
  return Response.json(
    {
      ok: false,
      error: {
        code: "fixed_registry_policy",
        message: "This Control Station owns a fixed PPU target; registry add/remove/endpoint mutation is disabled",
      },
    },
    { status: 403, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
  );
}

async function relayRegistry(request: Request): Promise<Response> {
  try {
    if (request.method === "POST" && fixedLifecycleRegistry()) {
      return fixedRegistryMutationRejected();
    }
  } catch {
    return Response.json(
      { ok: false, error: { code: "manager_bff_misconfigured", message: "Manager registry policy is invalid" } },
      { status: 503, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  }

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
