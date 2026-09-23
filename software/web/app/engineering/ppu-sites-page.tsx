"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FleetPPUView, FleetWebPayload } from "../fleet/fleet-contract";
import {
  getManagerFleet,
  getManagerRegistry,
  type ManagerRegistryEntry,
  type ManagerRegistryPayload,
} from "./ppu-registry-api";
import PpuSiteDesiredConfiguration from "./ppu-site-desired-configuration";
import "./ppu-site-configuration.css";

const ACTIVE_SITE_STATES = new Set(["queued", "submitting", "running", "stopping", "erase", "program", "verify", "read"]);
const FAULT_SITE_STATES = new Set(["error", "fault", "failed"]);

function fleetForEntry(entry: ManagerRegistryEntry, fleet: FleetWebPayload | null): FleetPPUView | null {
  if (!entry.alias || !fleet) return null;
  return fleet.ppus.find(ppu => ppu.alias === entry.alias) ?? null;
}

function hasActiveExecution(view: FleetPPUView | null): boolean {
  return Boolean(view?.topology.sites.some(site => Boolean(site.current_job_id) || ACTIVE_SITE_STATES.has(site.state.toLowerCase())));
}

export default function PpuSitesPage() {
  const [registry, setRegistry] = useState<ManagerRegistryPayload | null>(null);
  const [fleet, setFleet] = useState<FleetWebPayload | null>(null);
  const [selectedAlias, setSelectedAlias] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [nextRegistry, nextFleet] = await Promise.all([
        getManagerRegistry(),
        getManagerFleet().catch(() => null),
      ]);
      setRegistry(nextRegistry);
      setFleet(nextFleet);
      setSelectedAlias(current => {
        const aliases = nextRegistry.ppus.map(entry => entry.alias).filter((value): value is string => Boolean(value));
        return current && aliases.includes(current) ? current : aliases[0] ?? "";
      });
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Manager registry unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const timer = window.setInterval(() => { void refresh(); }, 3000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const selectedEntry = useMemo(
    () => registry?.ppus.find(entry => entry.alias === selectedAlias) ?? null,
    [registry, selectedAlias],
  );
  const selectedFleet = selectedEntry ? fleetForEntry(selectedEntry, fleet) : null;
  const activeExecution = hasActiveExecution(selectedFleet);
  const registered = selectedEntry?.lifecycle === "commissioned";

  const siteSummary = useMemo(() => {
    const sites = selectedFleet?.topology.sites ?? [];
    let ready = 0;
    let busy = 0;
    let fault = 0;
    for (const site of sites) {
      const state = site.state.toLowerCase();
      if (site.current_job_id || ACTIVE_SITE_STATES.has(state)) busy += 1;
      else if (FAULT_SITE_STATES.has(state)) fault += 1;
      else if (site.enabled) ready += 1;
    }
    return { total: selectedFleet?.topology.site_count ?? 0, ready, busy, fault };
  }, [selectedFleet]);

  return (
    <section className="ppuSiteConfiguration" aria-label="PPU Sites">
      <header className="ppuSiteHeader">
        <div>
          <small>PPU</small>
          <h2>Sites</h2>
          <p>Programming Sites are child resources of a PPU. Operational configuration is available only after Registration completes.</p>
        </div>
        <button className="ppuSiteButton" type="button" disabled={loading} onClick={() => void refresh()}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </header>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}

      <section className="ppuSiteCard ppuSitesTargetSummary" aria-label="Sites target and status">
        <header className="ppuSiteCardHeader">
          <div>
            <small>SELECTED PPU</small>
            <h3>{selectedEntry?.alias ?? "No PPU selected"}</h3>
          </div>
          {selectedEntry && <span className="ppuSiteFilter">{siteSummary.total} reported</span>}
        </header>
        <div className="ppuSitesTargetBody">
          <label className="operatorField">
            <span>Known PPU</span>
            <select value={selectedAlias} disabled={loading || !registry?.ppus.length} onChange={event => setSelectedAlias(event.target.value)}>
              {(registry?.ppus ?? []).filter(entry => entry.alias).map(entry => (
                <option key={entry.alias!} value={entry.alias!}>{entry.alias} — {entry.lifecycle === "commissioned" ? "Registered" : "Not Registered"}</option>
              ))}
            </select>
          </label>
          {selectedEntry && (
            <div className="ppuSitesSummaryGrid" aria-label="Site status summary">
              <article data-tone={siteSummary.fault > 0 ? "danger" : "healthy"}><small>Ready</small><strong>{siteSummary.ready}</strong></article>
              <article data-tone={siteSummary.busy > 0 ? "info" : "neutral"}><small>Busy</small><strong>{siteSummary.busy}</strong></article>
              <article data-tone={siteSummary.fault > 0 ? "danger" : "neutral"}><small>Fault</small><strong>{siteSummary.fault}</strong></article>
              <article><small>Registration</small><strong>{registered ? "Registered" : "Required"}</strong></article>
              <article><small>Enabled Sites</small><strong>{selectedFleet?.topology.enabled_site_count ?? 0}</strong></article>
              <article><small>Topology Source</small><strong>{selectedFleet?.topology.source ?? "none"}</strong></article>
              <article data-tone={activeExecution ? "warning" : "healthy"}><small>Active Execution</small><strong>{activeExecution ? "Yes" : "No"}</strong></article>
            </div>
          )}
        </div>
      </section>

      {selectedEntry ? (
        registered ? (
          <div className="ppuSitesWorkflow">
            <PpuSiteDesiredConfiguration entry={selectedEntry} hasActiveExecution={activeExecution} />
          </div>
        ) : (
          <section className="ppuSiteCard" aria-label="Sites locked until Registration">
            <header className="ppuSiteCardHeader"><div><small>LOCKED</small><h3>Registration required</h3></div></header>
            <p className="ppuRegistryMessage warning" role="status">This PPU is known to Console, but it is not registered for managed programming. Complete Registration before changing Site desired configuration or activating programming runtime state.</p>
            <p className="ppuSiteNote">PPU Platform Release inspection and maintenance remain available from Platform while Sites are locked.</p>
          </section>
        )
      ) : (
        <section className="ppuSiteCard ppuEmptyRegistry"><h3>{loading ? "Loading PPU inventory..." : "No known PPU"}</h3><p>Add a PPU connection from Registration first.</p></section>
      )}
    </section>
  );
}
