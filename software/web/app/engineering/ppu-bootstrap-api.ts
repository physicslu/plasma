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
  state: "queued" | "running" | "succeeded" | "failed" | string;
  upload_id: string;
  started_at_epoch_s: number;
  updated_at_epoch_s: number;
  error: string | null;
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

type ErrorPayload = {
  error?: { code?: string; message?: string } | string;
  message?: string;
};

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
    throw new Error(code ? `${code}: ${message}` : message);
  }
  return payload;
}

function root(alias: string): string {
  return `/api/manager/registry/${encodeURIComponent(alias)}/bootstrap`;
}

export function getManagerPpuBootstrap(alias: string): Promise<ManagerBootstrapStatus> {
  return jsonRequest<ManagerBootstrapStatus>(root(alias));
}

export function pairManagerPpuBootstrap(alias: string, token: string): Promise<ManagerBootstrapStatus> {
  return jsonRequest<ManagerBootstrapStatus>(`${root(alias)}/pair`, {
    method: "POST",
    body: JSON.stringify({ token }),
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

export function startManagerPpuBootstrapDeployment(
  alias: string,
  input: { upload_id: string; gateway_host: string; ppu_id: string; facility_id: string; display_name: string },
): Promise<DeploymentPayload> {
  return jsonRequest<DeploymentPayload>(`${root(alias)}/deployments`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}

export function bytesToBase64(data: ArrayBuffer): string {
  const bytes = new Uint8Array(data);
  let binary = "";
  const stride = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += stride) {
    binary += String.fromCharCode(...bytes.subarray(offset, Math.min(bytes.length, offset + stride)));
  }
  return btoa(binary);
}

export function parseSha256Sidecar(text: string, expectedFileName: string): string {
  const fields = text.trim().split(/\s+/);
  if (fields.length !== 2) throw new Error("Release SHA-256 sidecar must contain one digest and file name");
  const digest = fields[0]?.toLowerCase() ?? "";
  const fileName = (fields[1] ?? "").replace(/^\*/, "");
  if (!/^[0-9a-f]{64}$/.test(digest)) throw new Error("Release SHA-256 sidecar digest is invalid");
  if (fileName !== expectedFileName) throw new Error("Release SHA-256 sidecar does not identify the selected kit");
  return digest;
}
