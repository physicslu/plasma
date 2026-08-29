import { PlasmaApiError } from "../plasma-api";

export type LoopbackEndpoint = "ps" | "pl" | "ic";
export type LoopbackPattern = "prbs" | "increment" | "zero" | "ones" | "aa" | "55" | "walking1" | "walking0";

export type LoopbackCaseRequest = {
  endpoint: LoopbackEndpoint;
  test_id: string;
  sequence: number;
  pattern: LoopbackPattern;
  seed: string;
  payload_length: number;
  payload_base64: string;
  tx_crc32: string;
  timeout_ms: number;
};

export type LoopbackCaseResponse = {
  ok: true;
  rest_contract_version?: string;
  diagnostic_protocol_version: string;
  manager: {
    relay: "pass-through";
    ppu_alias: string;
    manager_rtt_ms: number;
  };
  loopback: {
    endpoint: "ps";
    source: "ps";
    test_id: string;
    sequence: number;
    transform: "echo";
    pattern: string;
    seed: string;
    payload_length: number;
    tx_crc32: string;
    rx_crc32: string;
    ppu_rtt_ms: number;
  };
  payload_base64: string;
};

type ErrorPayload = {
  error?: {
    message?: string;
    error_code?: string;
    code?: string;
  };
};

export async function executePsLoopbackCase(
  apiBase: string,
  request: LoopbackCaseRequest,
): Promise<LoopbackCaseResponse> {
  const response = await fetch(`${apiBase}/api/engineering/diagnostics/loopback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const payload = await response.json() as LoopbackCaseResponse | ErrorPayload;
  if (!response.ok || !("ok" in payload) || payload.ok !== true) {
    const error = payload as ErrorPayload;
    throw new PlasmaApiError(
      error.error?.message ?? `Loopback diagnostic failed with HTTP ${response.status}`,
      response.status,
      error.error?.error_code ?? error.error?.code,
      response.status === 503 || response.status === 504,
    );
  }
  const success = payload as LoopbackCaseResponse;
  if (
    success.manager?.relay !== "pass-through"
    || typeof success.manager.ppu_alias !== "string"
    || success.manager.ppu_alias.length === 0
    || typeof success.manager.manager_rtt_ms !== "number"
  ) {
    throw new PlasmaApiError(
      "Loopback response did not prove the Plasma Manager pass-through boundary",
      502,
      "manager_relay_unverified",
      false,
    );
  }
  return success;
}
