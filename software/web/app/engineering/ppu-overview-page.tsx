"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FleetPPUView, FleetWebPayload } from "../fleet/fleet-contract";
import {
  getManagerFleet,
  getManagerRegistry,
  type ManagerRegistryEntry,
  type ManagerRegistryPayload,
} from "./ppu-registry-api";
import {
  getManagerPpuBootstrap,
  type ManagerBootstrapStatus,
} from "./ppu-bootstrap-api";
import {
  connectivityState,
  healthState,
  lifecycleState,
} from "./ppu-ui-state";
import "./ppu-site-configuration.css";

const ACTIVE_SITE_STATES = new Set(["queued", "submitting", "running", "stopping", "erase", "program", "verify", "read"]);
const FAULT_SITE_STATES = new Set(["error", "fault", "failed"]);

type PpuDestination = "platform" | "registration" | "sites";

type Props = {
  onNavigate: (destination: PpuDestination) => void;
};

function fleetForEntry(entry: ManagerRegistryEntry, fleet: FleetWebPayload | null): FleetPPUView | null {
  if (!entry.alias || !fleet) return null;
  return fleet.ppus.find(item => item.alias === entry.alias) ?? null;
}

function registrationLabel(entry: ManagerRegistryEntry | null): string {
  if (!entry) return "Not known";
  if (entry.lifecycle === "commissioned") return "Registered";
  if (entry.lifecycle === "disabled") return "Registered / Disabled";
  return "Not Registered";
}

function platformReleaseLabel(status: ManagerBootstrapStatus | null): string {
  const runtime = status?.bootstrap.runtime;
  if (runtime?.release_id) return runtime.release_id;
  if (status?.bootstrap.bootstrap.state === "bootstrap_ready") return "Bootstrap only";
  return "Unavailable";
}

export default function PpuOverviewPage({ onNavigate }: Props) {
  const [registry, setRegistry] = useState<ManagerRegistryPayload | null>(null);
  const [fleet, setFleet] = useState<FleetWebPayload | null>(null);
  const [selectedAlias, setSelectedAlias] = useState("");
  const [bootstrap, setBootstrap] = useState<ManagerBootstrapStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    const [registryResult, fleetResult] = await Promise.allSettled([
      getManagerRegistry(),
      getManagerFleet(),
    ]);
    if (registryResult.status === "fulfilled") {
      setRegistry(registryResult.value);
      setSelectedAlias(current => {
        const aliases = registryResult.value.ppus
          .map(entry => entry.alias)
          .filter((value): value is string => Boolean(value));
        return current && aliases.includes(current) ? current : aliases[0] ?? "";
      });
      setError(null);
    } else {
      setError(registryResult.reason instanceof Error ? registryResult.reason.message : "Manager registry unavailable");
    }
    setFleet(fleetResult.status === "fulfilled" ? fleetResult.value : null);
    setLoading(false);
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const timer = window.setInterval(() => { void refresh(); }, 5000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedAlias) {
      setBootstrap(null);
      return () => { cancelled = true; };
    }
    void getManagerPpuBootstrap(selectedAlias)
      .then(status => { if (!cancelled) setBootstrap(status); })
      .catch(() => { if (!cancelled) setBootstrap(null); });
    return () => { cancelled = true; };
  }, [selectedAlias, registry, fleet]);

  const selectedEntry = useMemo(
    () => registry?.ppus.find(entry => entry.alias === selectedAlias) ?? null,
    [registry, selectedAlias],
  );
  const selectedFleet = selectedEntry ? fleetForEntry(selectedEntry, fleet) : null;
  const lifecycle = selectedEntry ? lifecycleState(selectedEntry) : null;
  const connectivity = connectivityState(selectedFleet);
  const health = healthState(selectedFleet);

  const siteSummary = useMemo(() => {
    const sites = selectedFleet?.topology.sites ?? [];
    let busy = 0;
    let fault = 0;
    let ready = 0;
    for (const site of sites) {
      const state = site.state.toLowerCase();
      if (site.current_job_id || ACTIVE_SITE_STATES.has(state)) busy += 1;
      else if (FAULT_SITE_STATES.has(state)) fault += 1;
      else if (site.enabled) ready += 1;
    }
    return { total: selectedFleet?.topology.site_count ?? 0, ready, busy, fault };
  }, [selectedFleet]);

  const alerts = useMemo(() => {
    const values: string[] = [];
    if (selectedFleet?.identity_conflict) values.push("PPU identity conflict");
    if (selectedFleet?.degraded) values.push("Fleet observation degraded");
    if (bootstrap?.bootstrap.runtime.state === "recovery_required") values.push("Runtime recovery required");
    if (bootstrap?.bootstrap.deployment?.state === "recovery_required") values.push("Platform deployment recovery required");
    return values;
  }, [selectedFleet, bootstrap]);

  return (
    <section className="ppuSiteConfiguration" aria-label="PPU Overview">
      <header className="ppuSiteHeader">
        <div>
          <small>PPU</small>
          <h2>Overview</h2>
          <p>Read-only summary of appliance reachability, platform state, Registration, and Site health.</p>
        </div>
        <button className="ppuSiteButton" type="button" disabled={loading} onClick={() => void refresh()}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </header>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}

      <section className="ppuSiteCard" aria-label="PPU overview target">
        <header className="ppuSiteCardHeader">
          <div>
            <small>DEVICE</small>
            <h3>{selectedFleet?.identity.display_name ?? selectedEntry?.alias ?? "No PPU selected"}</h3>
          </div>
          {lifecycle && <span className="ppuDimensionPill" data-tone={lifecycle.tone}>{lifecycle.label}</span>}
        </header>
        <div className="ppuRegistryAddForm">
          <label>
            <span>Known PPU</span>
            <select value={selectedAlias} disabled={loading || !registry?.ppus.length} onChange={event => setSelectedAlias(event.target.value)}>
              {(registry?.ppus ?? []).filter(entry => entry.alias).map(entry => (
                <option key={entry.alias!} value={entry.alias!}>{entry.alias}</option>
              ))}
            </select>
          </label>
          {!loading && registry?.ppus.length === 0 && <p>No known PPU connection exists yet. Add one from Registration.</p>}
        </div>
      </section>

      {selectedEntry ? (
        <>
          <div className="ppuStateDimensionGrid" aria-label="PPU overview state">
            <article className="ppuStateDimensionCard" data-tone={connectivity.tone}>
              <small>Connectivity</small>
              <strong>{connectivity.label}</strong>
              <p>{selectedEntry.endpoint}</p>
            </article>
            <article className="ppuStateDimensionCard" data-tone={health.tone}>
              <small>Platform Health</small>
              <strong>{health.label}</strong>
              <p>{health.reason}</p>
            </article>
            <article className="ppuStateDimensionCard" data-tone={selectedEntry.lifecycle === "commissioned" ? "healthy" : "warning"}>
              <small>Registration</small>
              <strong>{registrationLabel(selectedEntry)}</strong>
              <p>Programming management admission is separate from Platform maintenance.</p>
            </article>
          </div>

          <section className="ppuSiteCard" aria-label="PPU platform summary">
            <header className="ppuSiteCardHeader">
              <div>
                <small>PLATFORM</small>
                <h3>PPU Platform Release</h3>
              </div>
              <button className="ppuSiteButton" type="button" onClick={() => onNavigate("platform")}>View Platform</button>
            </header>
            <div className="ppuInfoBody">
              <dl className="ppuInfoGrid">
                <div className="wide"><dt>Platform Release</dt><dd>{platformReleaseLabel(bootstrap)}</dd></div>
                <div><dt>Bootstrap Version</dt><dd>{bootstrap?.bootstrap.bootstrap.version ?? "Unavailable"}</dd></div>
                <div><dt>Runtime Version</dt><dd>{bootstrap?.bootstrap.runtime.product_version ?? "Not installed"}</dd></div>
                <div className="wide"><dt>Runtime Commit</dt><dd>{bootstrap?.bootstrap.runtime.git_sha ?? "—"}</dd></div>
              </dl>
            </div>
          </section>

          <section className="ppuSiteCard" aria-label="PPU registration summary">
            <header className="ppuSiteCardHeader">
              <div>
                <small>REGISTRATION</small>
                <h3>{registrationLabel(selectedEntry)}</h3>
              </div>
              <button className="ppuSiteButton" type="button" onClick={() => onNavigate("registration")}>View Registration</button>
            </header>
            <p className="ppuSiteNote">Registration controls whether this Console may use the PPU for managed programming. It is not required to inspect or maintain the Platform Release.</p>
          </section>

          <section className="ppuSiteCard" aria-label="PPU Site summary">
            <header className="ppuSiteCardHeader">
              <div>
                <small>SITES</small>
                <h3>{siteSummary.total} reported</h3>
              </div>
              <button className="ppuSiteButton" type="button" onClick={() => onNavigate("sites")}>View Sites</button>
            </header>
            <div className="ppuStateSummaryGrid">
              <div className="ppuStateSummaryGroup"><small>Ready</small><strong>{siteSummary.ready}</strong></div>
              <div className="ppuStateSummaryGroup"><small>Busy</small><strong>{siteSummary.busy}</strong></div>
              <div className="ppuStateSummaryGroup"><small>Fault</small><strong>{siteSummary.fault}</strong></div>
            </div>
          </section>

          <section className="ppuSiteCard" aria-label="PPU active alerts">
            <header className="ppuSiteCardHeader"><h3>Alerts</h3></header>
            {alerts.length ? (
              <ul>{alerts.map(alert => <li key={alert}>{alert}</li>)}</ul>
            ) : (
              <p className="ppuSiteNote">No active alert is visible from current Manager and Bootstrap observations.</p>
            )}
          </section>
        </>
      ) : (
        <section className="ppuSiteCard ppuEmptyRegistry"><h3>No PPU selected</h3><p>Add a known PPU connection from Registration.</p></section>
      )}
    </section>
  );
}
