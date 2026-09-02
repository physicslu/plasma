import { relayManagerRegistryRequest } from "../manager-bff";

export async function GET(request: Request): Promise<Response> {
  return await relayManagerRegistryRequest(request);
}

export async function POST(request: Request): Promise<Response> {
  return await relayManagerRegistryRequest(request);
}
