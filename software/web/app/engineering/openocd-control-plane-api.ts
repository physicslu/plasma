import { PlasmaApiError } from "../plasma-api";

export type OpenOcdControlPlaneRequest = {
  site_id: number;
  timeout_ms: number;
};

export type OpenOcdControlPlaneResponse = {
  ok: true;
  result: "PASS";
  rest_contract_version?: string;
  site_id: number;
  openocd_version: string;
  openocd_version_banner: string;
  runtime_id: string;
  process_state: "stopped";
  probe_process_state: "running";
  tcl_rpc_state: "pass";
  rpc_scope: "loopback";
  architecture: string;
  host_architecture: string;
  worker_generation: number;
  latency_ms: number;
  execution_capability: "openocd-control-plane-only";
  hardware_runtime_ready: false;
  manager: {
    relay: "pass-through";
    ppu_alias: string;
    manager_rtt_ms: number;
  };
  not_claimed: string[];
};

type ErrorPayload = {
  error?: {
    message?: string;
    error_code?: string;
    code?: string;
  };
};

export async function executeOpenOcdControlPlane(
  apiBase: string,
  request: OpenOcdControlPlaneRequest,
): Promise<OpenOcdControlPlaneResponse> {
  const response = await fetch(`${apiBase}/api/engineering/diagnostics/openocd-control-plane`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const payload = await response.json() as OpenOcdControlPlaneResponse | ErrorPayload;
  if (!response.ok || !("ok" in payload) || payload.ok !== true) {
    const error = payload as ErrorPayload;
    throw new PlasmaApiError(
      error.error?.message ?? `OpenOCD control-plane diagnostic failed with HTTP ${response.status}`,
      response.status,
      error.error?.error_code ?? error.error?.code,
      response.status === 503 || response.status === 504,
    );
  }

  const success = payload as OpenOcdControlPlaneResponse;
  if (
    success.result !== "PASS"
    || success.execution_capability !== "openocd-control-plane-only"
    || success.hardware_runtime_ready !== false
    || success.tcl_rpc_state !== "pass"
    || success.rpc_scope !== "loopback"
    || success.manager?.relay !== "pass-through"
  ) {
    throw new PlasmaApiError(
      "OpenOCD response did not prove the managed control-plane boundary",
      502,
      "openocd_control_plane_unverified",
      false,
    );
  }
  return success;
}
