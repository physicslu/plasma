export type BootstrapRuntimeStatus = {
  state: string;
  release_id: string | null;
  product_version: string | null;
  git_sha: string | null;
  target: string | null;
  reason: string | null;
};

export type BootstrapDeploymentRecord = {
  transaction_id: string;
  state: "queued" | "running" | "succeeded" | "failed" | "recovery_required" | "reconciled" | string;
  upload_id: string;
  started_at_epoch_s: number;
  updated_at_epoch_s: number;
  error: string | null;
  error_code?: string | null;
  result: Record<string, unknown> | null;
};

export type ManagerBootstrapStatus = {
  ok: true;
  ppu_alias: string;
  bootstrap_endpoint_policy: string;
  pairing: {
    paired: boolean;
    device_id: string | null;
    device_match: boolean;
    credential_persistence: string;
    updated_at: string | null;
    controller_generation?: number | null;
    controller_id?: string | null;
    controller_replaced?: boolean;
  };
  bootstrap: {
    schema_version: number;
    bootstrap: {
      api_version: string;
      version: string;
      state: string;
    };
    identity: {
      device_id: string;
      ppu_id: string | null;
      facility_id: string | null;
      hardware_revision: string | null;
    };
    runtime: BootstrapRuntimeStatus;
    fpga: {
      pl_version: string | null;
      pl_compatibility: string;
      pl_qualification: string;
    };
    capabilities: {
      runtime_deployment: boolean;
      identity_update: boolean;
      fpga_update: boolean;
    };
    security?: {
      control_token_provisioned?: boolean;
      transport_confidentiality?: string;
      publisher_authenticity?: string;
    };
    deployment: BootstrapDeploymentRecord | null;
  };
};

export type PlatformPsLoopbackPayload = {
  ok: true;
  diagnostic_protocol_version?: string;
  loopback: {
    endpoint: string;
    source: string;
    test_id: string;
    sequence: number;
    transform?: string;
    pattern?: string;
    seed?: string;
    payload_length?: number;
    tx_crc32?: string;
    rx_crc32?: string;
    ppu_rtt_ms?: number;
  };
  payload_base64?: string;
  manager: {
    relay: "platform-maintenance";
    context: "platform";
    ppu_alias: string;
    manager_rtt_ms: number;
  };
};

type ErrorPayload = {
  error?: { code?: string; message?: string } | string;
  message?: string;
};

export class BootstrapApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly detail: string;

  constructor(status: number, code: string | null, message: string) {
    super(code ? `${code}: ${message}` : message);
    this.name = "BootstrapApiError";
    this.status = status;
    this.code = code;
    this.detail = message;
  }
}

export function isMissingBootstrapCapabilityRoute(error: unknown): boolean {
  return error instanceof BootstrapApiError
    && error.status === 404
    && error.code === null
    && error.detail === "not found";
}

type UploadPayload = {
  ok: true;
  upload: {
    upload_id: string;
    state: string;
    size: number;
    sha256: string;
    received_bytes: number;
  };
};

type DeploymentPayload = {
  ok: true;
  deployment: BootstrapDeploymentRecord;
};

type BinaryData = ArrayBuffer | Uint8Array;

async function jsonRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  const payload = await response.json().catch(() => null) as (T & ErrorPayload) | null;
  if (!response.ok || payload == null) {
    const error = payload?.error;
    const message = typeof error === "object" && error?.message
      ? error.message
      : payload?.message ?? `Bootstrap request failed with HTTP ${response.status}`;
    const code = typeof error === "object" ? error?.code : typeof error === "string" ? error : null;
    throw new BootstrapApiError(response.status, code ?? null, message);
  }
  return payload;
}

function root(alias: string): string {
  return `/api/manager/registry/${encodeURIComponent(alias)}/bootstrap`;
}

export function getManagerPpuBootstrap(alias: string): Promise<ManagerBootstrapStatus> {
  return jsonRequest<ManagerBootstrapStatus>(root(alias));
}

export type ManagerPpuEnrollmentResult = {
  ok: boolean;
  ppu_alias: string;
  state: string | null;
  controller_generation?: number;
  controller_mode?: "NORMAL" | "RECOVERY_ONLY";
  recovery_blockers?: string[];
  enrollment_source?: string;
  expires_in_s?: number;
  instruction?: string;
  detail?: unknown;
};

/** LOM-P2A-2 local enrollment: no token is ever typed for normal use. */
export function enrollManagerPpuBootstrap(
  alias: string,
  request: { entry: "button"; step: "start" | "claim" } | { entry: "ticket"; ticket: string },
): Promise<ManagerPpuEnrollmentResult> {
  return jsonRequest<ManagerPpuEnrollmentResult>(`${root(alias)}/enrollment`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function runManagerPpuPlatformPsLoopback(alias: string): Promise<PlatformPsLoopbackPayload> {
  const sequence = Date.now();
  return jsonRequest<PlatformPsLoopbackPayload>(`${root(alias)}/ps-loopback`, {
    method: "POST",
    body: JSON.stringify({
      endpoint: "ps",
      test_id: `platform-ps-${sequence}`,
      sequence,
      pattern: "zero",
      seed: "",
      payload_length: 1,
      payload_base64: "AA==",
      tx_crc32: "d202ef8d",
      timeout_ms: 5000,
    }),
  });
}

export function createManagerPpuBootstrapUpload(
  alias: string,
  size: number,
  sha256: string,
): Promise<UploadPayload> {
  return jsonRequest<UploadPayload>(`${root(alias)}/uploads`, {
    method: "POST",
    body: JSON.stringify({ size, sha256 }),
  });
}

export function appendManagerPpuBootstrapChunk(
  alias: string,
  uploadId: string,
  offset: number,
  dataBase64: string,
  sha256: string,
): Promise<UploadPayload> {
  return jsonRequest<UploadPayload>(`${root(alias)}/uploads/${encodeURIComponent(uploadId)}/chunks`, {
    method: "POST",
    body: JSON.stringify({ offset, data_base64: dataBase64, sha256 }),
  });
}

export function commitManagerPpuBootstrapUpload(alias: string, uploadId: string): Promise<UploadPayload> {
  return jsonRequest<UploadPayload>(`${root(alias)}/uploads/${encodeURIComponent(uploadId)}/commit`, {
    method: "POST",
    body: JSON.stringify({ action: "commit" }),
  });
}

export function admitManagerPpuBundle(
  alias: string,
  uploadId: string,
  archiveSha256: string,
): Promise<DeploymentPayload> {
  if (!/^[0-9a-f]{32}$/.test(uploadId)) {
    return Promise.reject(new Error("Invalid Bundle upload ID"));
  }
  if (!/^[0-9a-f]{64}$/.test(archiveSha256)) {
    return Promise.reject(new Error("Invalid Bundle SHA-256"));
  }
  // Browser -> existing BFF -> Manager -> the same PPU Bootstrap API. The
  // explicit owner choice is the exact SHA-256 of the selected file; the
  // paired Manager turns it into a device-bound Owner Operation Authorization.
  // No device credential, per-Bundle allowlist or install/activate flag.
  return jsonRequest<DeploymentPayload>(`${root(alias)}/deployments`, {
    method: "POST",
    body: JSON.stringify({ kind: "bundle", upload_id: uploadId, archive_sha256: archiveSha256 }),
  }).then(receipt => {
    const deployment = receipt.deployment;
    const result = deployment?.result;
    const plan = result && typeof result === "object"
      ? (result.plan as Record<string, unknown> | undefined) : undefined;
    const owner = plan?.owner_authorization && typeof plan.owner_authorization === "object"
      ? (plan.owner_authorization as Record<string, unknown>) : undefined;
    if (deployment?.state !== "admitted" ||
        result?.stage !== "package_admission_only" ||
        result?.install_qualified !== false ||
        result?.owner_authorized !== true ||
        plan?.kind !== "bundle" ||
        plan?.execution_permitted !== false ||
        plan?.archive_sha256 !== archiveSha256 ||
        owner?.status !== "OWNER_AUTHORIZED" ||
        owner?.action !== "bundle.admit" ||
        owner?.subject_sha256 !== archiveSha256) {
      throw new Error("Bundle B2 receipt lacks owner authorization for this exact file or non-execution guarantee");
    }
    return receipt;
  });
}

export interface AdmittedBundle {
  uploadId: string;
  archiveSha256: string;
  admissionTransactionId: string;
}

export function installManagerPpuBundle(
  alias: string,
  admitted: AdmittedBundle,
  fpgaLoad: boolean,
): Promise<DeploymentPayload> {
  if (!/^[0-9a-f]{32}$/.test(admitted.uploadId) ||
      !/^[0-9a-f]{32}$/.test(admitted.admissionTransactionId)) {
    return Promise.reject(new Error("Invalid Bundle upload or admission ID"));
  }
  if (!/^[0-9a-f]{64}$/.test(admitted.archiveSha256)) {
    return Promise.reject(new Error("Invalid Bundle SHA-256"));
  }
  // B3 of the PPU's CURRENT B2-admitted Bundle. The owner choices are the
  // exact admitted SHA-256/transaction and whether to also load its FPGA
  // Image; never a path, idle claim or token. Both Console choices activate
  // the Bundle as the Active Set (the Manager requires an explicit mode);
  // the Console never requests a stage-only install.
  return jsonRequest<DeploymentPayload>(`${root(alias)}/deployments`, {
    method: "POST",
    body: JSON.stringify({
      kind: "bundle", upload_id: admitted.uploadId,
      archive_sha256: admitted.archiveSha256,
      admission_transaction_id: admitted.admissionTransactionId,
      mode: "activate",
      fpga_load: fpgaLoad,
    }),
  }).then(receipt => {
    const state = receipt.deployment?.state;
    if (receipt.deployment?.upload_id !== admitted.uploadId || (state !== "queued" && state !== "running")) {
      throw new Error("Bundle B3 submission was not queued");
    }
    return receipt;
  });
}

export function startManagerPpuBootstrapDeployment(
  alias: string,
  input: { upload_id: string; ppu_id: string; facility_id: string; display_name: string },
): Promise<DeploymentPayload> {
  return jsonRequest<DeploymentPayload>(`${root(alias)}/deployments`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

function binaryBytes(data: BinaryData): Uint8Array {
  return data instanceof Uint8Array ? data : new Uint8Array(data);
}

export async function sha256Hex(data: BinaryData): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", binaryBytes(data));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}

export function bytesToBase64(data: BinaryData): string {
  const bytes = binaryBytes(data);
  let binary = "";
  const stride = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += stride) {
    binary += String.fromCharCode(...bytes.subarray(offset, Math.min(bytes.length, offset + stride)));
  }
  return btoa(binary);
}

export function parseSha256Sidecar(text: string, expectedFileName: string): string {
  const fields = text.trim().split(/\s+/);
  if (fields.length !== 2) throw new Error("Z2 PS Kit SHA-256 sidecar must contain one digest and file name");
  const digest = fields[0]?.toLowerCase() ?? "";
  const fileName = (fields[1] ?? "").replace(/^\*/, "");
  if (!/^[0-9a-f]{64}$/.test(digest)) throw new Error("Z2 PS Kit SHA-256 sidecar digest is invalid");
  if (fileName !== expectedFileName) throw new Error("Z2 PS Kit SHA-256 sidecar does not identify the selected kit");
  return digest;
}
