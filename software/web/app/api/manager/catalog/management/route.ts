import { relayManagerCatalogManagementRequest } from "../../manager-bff";

export const GET = (request: Request) => relayManagerCatalogManagementRequest(request, "");
