import { relayManagerCatalogManagementRequest } from "../../../manager-bff";

type Context = { params: Promise<{ action: string }> };

export async function GET(request: Request, context: Context): Promise<Response> {
  return relayManagerCatalogManagementRequest(request, (await context.params).action);
}

export async function POST(request: Request, context: Context): Promise<Response> {
  return relayManagerCatalogManagementRequest(request, (await context.params).action);
}
