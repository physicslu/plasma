export type FleetObservationState = "current" | "stale" | "unknown";
export type FleetTransportState = "reachable" | "unreachable" | "unknown";
export type FleetExecutionState = "ready" | "unavailable" | "unknown";
export type FleetTopologySource = "current" | "last_known" | "none";

export type FleetJobSummary = {
  job_id: string;
  operation: "erase" | "program" | "verify" | "read" | "unknown";
  state: string;
  stage: string | null;
  stage_state: string | null;
  progress_percent: number;
  created_at: string | null;
  started_at: string | null;
  updated_at: string | null;
  cancel_requested: boolean;
};

export type FleetSiteView = {
  site_id: number;
  enabled: boolean;
  state: string;
  current_job_id: string | null;
  latest_job: FleetJobSummary | null;
  interface: string | null;
  target: string | null;
};

export type FleetPPUView = {
  alias: string | null;
  identity: {
    ppu_id: string | null;
    facility_id: string | null;
    model: string | null;
    display_name: string | null;
  };
  transport_state: FleetTransportState;
  execution_state: FleetExecutionState;
  observation: {
    state: FleetObservationState;
    last_success_at: string | null;
    stale_age_s: number | null;
  };
  topology: {
    source: FleetTopologySource;
    site_count: number;
    enabled_site_count: number;
    sites: FleetSiteView[];
  };
  current_capacity: {
    site_count: number;
    enabled_site_count: number;
  };
  identity_conflict: boolean;
  degraded: boolean;
};

export type FleetWebPayload = {
  ok: true;
  contract_version: "1";
  observed_at: string | null;
  degraded: boolean;
  summary: {
    configured_ppus: number;
    reachable_ppus: number;
    ready_ppus: number;
    current_ppus: number;
    stale_ppus: number;
    unknown_ppus: number;
    reported_sites: number;
    enabled_sites: number;
    identity_conflicts: number;
  };
  manager: {
    cache_age_s: number | null;
    poll_interval_s: number | null;
    refresh_healthy: boolean;
    observation_store: {
      mode: "memory" | "sqlite" | "unknown";
      healthy: boolean;
      writable: boolean;
    };
  };
  ppus: FleetPPUView[];
};

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function number(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function boolean(value: unknown): boolean {
  return value === true;
}

function observationState(value: unknown): FleetObservationState {
  return value === "current" || value === "stale" || value === "unknown" ? value : "unknown";
}

function transportState(value: unknown): FleetTransportState {
  return value === "reachable" || value === "unreachable" || value === "unknown" ? value : "unknown";
}

function executionState(value: unknown): FleetExecutionState {
  return value === "ready" || value === "unavailable" || value === "unknown" ? value : "unknown";
}

function operation(value: unknown): FleetJobSummary["operation"] {
  return value === "erase" || value === "program" || value === "verify" || value === "read"
    ? value
    : "unknown";
}

function jobSummary(value: unknown): FleetJobSummary | null {
  const job = object(value);
  const jobId = text(job?.job_id);
  if (!job || !jobId) return null;
  return {
    job_id: jobId,
    operation: operation(job.operation),
    state: text(job.state) ?? "unknown",
    stage: text(job.stage),
    stage_state: text(job.stage_state),
    progress_percent: Math.max(0, Math.min(100, number(job.progress_percent))),
    created_at: text(job.created_at),
    started_at: text(job.started_at),
    updated_at: text(job.updated_at),
    cancel_requested: boolean(job.cancel_requested),
  };
}

function siteView(value: unknown): FleetSiteView | null {
  const site = object(value);
  if (!site) return null;
  const siteId = number(site.site_id, -1);
  if (!Number.isInteger(siteId) || siteId < 1) return null;
  return {
    site_id: siteId,
    enabled: boolean(site.enabled),
    state: text(site.state) ?? "unknown",
    current_job_id: text(site.current_job_id),
    latest_job: jobSummary(site.latest_job),
    interface: text(site.interface),
    target: text(site.target),
  };
}

function identityFrom(ppu: JsonObject | null) {
  return {
    ppu_id: text(ppu?.ppu_id),
    facility_id: text(ppu?.facility_id),
    model: text(ppu?.model),
    display_name: text(ppu?.display_name),
  };
}

function topologyFrom(ppu: JsonObject | null, sitesValue: unknown, source: FleetTopologySource) {
  const sites = array(sitesValue).map(siteView).filter((site): site is FleetSiteView => site !== null);
  return {
    source,
    site_count: number(ppu?.site_count, sites.length),
    enabled_site_count: number(ppu?.enabled_site_count, sites.filter(site => site.enabled).length),
    sites,
  };
}

function ppuView(value: unknown): FleetPPUView {
  const item = object(value) ?? {};
  const currentPpu = object(item.ppu);
  const currentSites = array(item.sites);
  const lastKnown = object(item.last_known);
  const lastKnownPpu = object(lastKnown?.ppu);
  const lastKnownSites = array(lastKnown?.sites);
  const observation = object(item.observation) ?? {};
  const state = observationState(observation.state);

  let identitySource = currentPpu;
  let topology = topologyFrom(currentPpu, currentSites, currentPpu ? "current" : "none");
  if (!currentPpu && lastKnownPpu) {
    identitySource = lastKnownPpu;
    topology = topologyFrom(lastKnownPpu, lastKnownSites, "last_known");
  }

  return {
    alias: text(item.alias),
    identity: identityFrom(identitySource),
    transport_state: transportState(item.transport_state),
    execution_state: executionState(item.execution_state),
    observation: {
      state,
      last_success_at: text(observation.last_success_at),
      stale_age_s: typeof observation.stale_age_s === "number" ? observation.stale_age_s : null,
    },
    topology,
    current_capacity: {
      site_count: currentPpu ? number(currentPpu.site_count) : 0,
      enabled_site_count: currentPpu ? number(currentPpu.enabled_site_count) : 0,
    },
    identity_conflict: boolean(item.identity_conflict),
    degraded: array(item.errors).length > 0 || item.execution_ready !== true,
  };
}

export function sanitizeManagerFleet(value: unknown): FleetWebPayload {
  const fleet = object(value);
  if (!fleet || fleet.ok !== true) {
    throw new Error("Manager fleet payload is invalid");
  }

  const summary = object(fleet.summary) ?? {};
  const cache = object(fleet.cache) ?? {};
  const observationStore = object(fleet.observation_store) ?? {};
  const ppus = array(fleet.ppus).map(ppuView);

  return {
    ok: true,
    contract_version: "1",
    observed_at: text(fleet.observed_at),
    degraded: boolean(fleet.degraded),
    summary: {
      configured_ppus: number(summary.configured_ppus, ppus.length),
      reachable_ppus: number(summary.reachable_ppus),
      ready_ppus: number(summary.ready_ppus),
      current_ppus: ppus.filter(ppu => ppu.observation.state === "current").length,
      stale_ppus: number(summary.stale_ppus, ppus.filter(ppu => ppu.observation.state === "stale").length),
      unknown_ppus: number(summary.unknown_ppus, ppus.filter(ppu => ppu.observation.state === "unknown").length),
      reported_sites: number(summary.reported_sites),
      enabled_sites: number(summary.enabled_sites),
      identity_conflicts: number(summary.identity_conflicts),
    },
    manager: {
      cache_age_s: typeof cache.age_s === "number" ? cache.age_s : null,
      poll_interval_s: typeof cache.poll_interval_s === "number" ? cache.poll_interval_s : null,
      refresh_healthy: cache.last_refresh_error == null,
      observation_store: {
        mode: observationStore.mode === "memory" || observationStore.mode === "sqlite"
          ? observationStore.mode
          : "unknown",
        healthy: observationStore.healthy !== false,
        writable: boolean(observationStore.writable),
      },
    },
    ppus,
  };
}
