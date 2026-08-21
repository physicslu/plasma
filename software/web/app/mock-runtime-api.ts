export type MockOperationProfile = {
  error_rate_per_mille: number;
  base_time_ms: number;
  throughput_bytes_per_second: number;
  jitter_ms: number;
};

export type MockRuntimeSettings = {
  profile_id: string;
  revision: number;
  enabled: boolean;
  default_image_size_bytes: number;
  operations: {
    erase: MockOperationProfile;
    program: MockOperationProfile;
    verify: MockOperationProfile;
    read: MockOperationProfile;
  };
  seed: {
    mode: "auto" | "fixed";
    fixed_seed: number | null;
  };
};

export type MockBatchRuntimeSnapshot = {
  profile: Omit<MockRuntimeSettings, "seed">;
  seed_mode: "auto" | "fixed";
  resolved_seed: number;
  batch_id: string;
};

type MockRuntimePayload = {
  ok: boolean;
  mock_runtime: MockRuntimeSettings;
};

type ErrorPayload = {
  error?: { message?: string; error_code?: string; error_type?: string };
};

export class MockRuntimeApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "MockRuntimeApiError";
  }
}

async function requestMockRuntime(
  apiBase: string,
  init?: RequestInit,
): Promise<MockRuntimeSettings> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 15_000);
  try {
    const response = await fetch(`${apiBase}/api/mock/runtime`, {
      ...init,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
      signal: controller.signal,
    });
    const payload = (await response.json()) as MockRuntimePayload & ErrorPayload;
    if (!response.ok) {
      const detail = payload.error?.error_code
        ? `${payload.error.error_code}: ${payload.error.message ?? payload.error.error_type ?? "Mock runtime error"}`
        : payload.error?.message ?? `Mock runtime HTTP ${response.status}`;
      throw new MockRuntimeApiError(detail, response.status);
    }
    return payload.mock_runtime;
  } catch (error) {
    if (error instanceof MockRuntimeApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new MockRuntimeApiError("Mock runtime request timed out");
    }
    throw new MockRuntimeApiError(error instanceof Error ? error.message : "Mock runtime request failed");
  } finally {
    window.clearTimeout(timer);
  }
}

export async function getMockRuntimeSettings(apiBase: string): Promise<MockRuntimeSettings> {
  return await requestMockRuntime(apiBase);
}

export async function updateMockRuntimeSettings(
  apiBase: string,
  settings: MockRuntimeSettings,
): Promise<MockRuntimeSettings> {
  const editable = {
    enabled: settings.enabled,
    default_image_size_bytes: settings.default_image_size_bytes,
    operations: settings.operations,
    seed: settings.seed,
  };
  return await requestMockRuntime(apiBase, {
    method: "POST",
    body: JSON.stringify(editable),
  });
}