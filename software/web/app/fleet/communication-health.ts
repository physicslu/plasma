import { PlasmaApiError } from "../plasma-api";

export type GatewayHealthState = "connecting" | "online" | "unreachable";
export type PPUHealthTone = "idle" | "loading" | "online" | "degraded" | "unknown" | "unavailable";

export type PPUObservation = {
  loading: boolean;
  error?: string;
  expectedSiteIds: number[];
  observedSiteIds: number[];
};

export type PPUHealthSummary = {
  tone: PPUHealthTone;
  label: string;
  ready: number;
  total: number;
};

export function gatewayHealthFromError(error: unknown): GatewayHealthState {
  return error instanceof PlasmaApiError && error.status !== undefined ? "online" : "unreachable";
}

export function gatewayHealthFromSettled(results: PromiseSettledResult<unknown>[]): GatewayHealthState {
  if (results.some(result => result.status === "fulfilled")) return "online";
  if (results.some(result => result.status === "rejected" && gatewayHealthFromError(result.reason) === "online")) {
    return "online";
  }
  return "unreachable";
}

export function summarizePPUHealth(
  gatewayHealth: GatewayHealthState,
  catalogAvailable: boolean,
  providerUnavailable: boolean,
  observations: PPUObservation[],
): PPUHealthSummary {
  const total = observations.length;
  if (gatewayHealth === "unreachable") {
    return { tone: "unknown", label: "PPU UNKNOWN", ready: 0, total };
  }
  if (!catalogAvailable) {
    return providerUnavailable
      ? { tone: "unavailable", label: "PPU UNAVAILABLE", ready: 0, total: 0 }
      : { tone: "loading", label: "PPU WAITING", ready: 0, total: 0 };
  }
  if (!total) return { tone: "idle", label: "PPU —", ready: 0, total: 0 };

  let ready = 0;
  let loading = 0;
  let degraded = 0;
  for (const observation of observations) {
    if (observation.loading) {
      loading += 1;
      continue;
    }
    if (observation.error) {
      degraded += 1;
      continue;
    }
    const observed = new Set(observation.observedSiteIds);
    if (observation.expectedSiteIds.every(siteId => observed.has(siteId))) ready += 1;
    else degraded += 1;
  }

  if (degraded > 0) {
    return { tone: "degraded", label: `PPU ${ready}/${total} READY · DEGRADED`, ready, total };
  }
  if (loading > 0) {
    return { tone: "loading", label: `PPU ${ready}/${total} READY · LOADING`, ready, total };
  }
  return { tone: "online", label: `PPU ${ready}/${total} READY`, ready, total };
}
