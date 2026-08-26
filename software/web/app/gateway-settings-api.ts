export type GatewaySettings = {
  revision: number;
  ppu_request_timeout_ms: number;
  ppu_retry_count: number;
  ppu_response_budget_ms?: number;
};

export const DEFAULT_GATEWAY_SETTINGS: GatewaySettings = {
  revision: 1,
  ppu_request_timeout_ms: 10_000,
  ppu_retry_count: 3,
  ppu_response_budget_ms: 47_000,
};

const GATEWAY_STATUS_TRANSPORT_MARGIN_MS = 5_000;

type GatewaySettingsPayload = {
  ok: boolean;
  gateway_settings: GatewaySettings;
  error?: { message?: string; error_code?: string };
};

const cachedSettings = new Map<string, GatewaySettings>();
const inFlightSettings = new Map<string, Promise<GatewaySettings>>();
const settingsListeners = new Set<(apiBase: string, settings: GatewaySettings) => void>();

function publishGatewaySettings(apiBase: string, settings: GatewaySettings): GatewaySettings {
  cachedSettings.set(apiBase, settings);
  settingsListeners.forEach(listener => listener(apiBase, settings));
  return settings;
}

function compatibilityResponseBudgetMs(settings: GatewaySettings): number {
  const attempts = settings.ppu_retry_count + 1;
  let backoffMs = 0;
  for (let retry = 0; retry < settings.ppu_retry_count; retry += 1) {
    backoffMs += Math.min(2 ** retry, 4) * 1000;
  }
  return settings.ppu_request_timeout_ms * attempts + backoffMs;
}

export function gatewayStatusObservationTimeoutMs(settings: GatewaySettings): number {
  const serverBudget = settings.ppu_response_budget_ms;
  const responseBudget = typeof serverBudget === "number" && Number.isFinite(serverBudget) && serverBudget > 0
    ? serverBudget
    : compatibilityResponseBudgetMs(settings);
  return responseBudget + GATEWAY_STATUS_TRANSPORT_MARGIN_MS;
}

export function cachedGatewaySettings(apiBase: string): GatewaySettings {
  return cachedSettings.get(apiBase) ?? DEFAULT_GATEWAY_SETTINGS;
}

export async function ensureGatewaySettings(apiBase: string): Promise<GatewaySettings> {
  return cachedSettings.get(apiBase) ?? await getGatewaySettings(apiBase);
}

export function subscribeGatewaySettings(
  listener: (apiBase: string, settings: GatewaySettings) => void,
): () => void {
  settingsListeners.add(listener);
  return () => settingsListeners.delete(listener);
}

async function requestGatewaySettings(apiBase: string, init?: RequestInit): Promise<GatewaySettings> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch(`${apiBase}/api/settings/gateway`, {
      ...init,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
      },
      signal: controller.signal,
    });
    const payload = (await response.json()) as GatewaySettingsPayload;
    if (!response.ok) {
      const message = payload.error?.error_code
        ? `${payload.error.error_code}: ${payload.error.message ?? "Gateway settings request failed"}`
        : payload.error?.message ?? `Gateway settings HTTP ${response.status}`;
      throw new Error(message);
    }
    return publishGatewaySettings(apiBase, payload.gateway_settings);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Gateway settings request timed out");
    }
    throw error instanceof Error ? error : new Error("Gateway settings request failed");
  } finally {
    window.clearTimeout(timer);
  }
}

export async function getGatewaySettings(apiBase: string): Promise<GatewaySettings> {
  const existing = inFlightSettings.get(apiBase);
  if (existing) return await existing;
  const request = requestGatewaySettings(apiBase);
  inFlightSettings.set(apiBase, request);
  try {
    return await request;
  } finally {
    inFlightSettings.delete(apiBase);
  }
}

export async function updateGatewaySettings(
  apiBase: string,
  settings: Pick<GatewaySettings, "ppu_request_timeout_ms" | "ppu_retry_count">,
): Promise<GatewaySettings> {
  return await requestGatewaySettings(apiBase, {
    method: "POST",
    body: JSON.stringify({
      ppu_request_timeout_ms: settings.ppu_request_timeout_ms,
      ppu_retry_count: settings.ppu_retry_count,
    }),
  });
}
