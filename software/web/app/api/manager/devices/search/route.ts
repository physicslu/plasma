import { relayManagerDeviceSearchRequest } from "../../manager-bff";

// Device Selector is owned by Plasma Manager (PR-C2); read-only GET only.
export async function GET(request: Request): Promise<Response> {
  return await relayManagerDeviceSearchRequest(request);
}
