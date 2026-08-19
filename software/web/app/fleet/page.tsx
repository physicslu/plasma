"use client";

import { useEffect, useMemo, useState } from "react";
import type { FleetPPUView, FleetWebPayload } from "./fleet-contract";
import "./fleet.css";

type LoadState = "loading" | "ready" | "disabled" | "error";

function formatAge(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

function displayName(ppu: FleetPPUView): string {
  return ppu.identity.display_name ?? ppu.identity.ppu_id ?? ppu.alias ?? "Unknown PPU";
}

function stateLabel(ppu: FleetPPUView): string {
  if (ppu.identity_conflict) return "IDENTITY CONFLICT";
  if (ppu.observation.state === "current" && ppu.execution_state === "ready") return "READY";
  if (ppu.observation.state === "stale") return "STALE";
  if (ppu.transport_state === "unreachable") return "OFFLINE";
  if (ppu.execution_state === "unavailable") return "UNAVAILABLE";
  return "UNKNOWN";
}

export default function FleetPage() {
  const [payload, setPayload] = useState<FleetWebPayload | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [message, setMessage] = useState("Loading fleet snapshot…");

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const response = await fetch("/api/fleet", { cache: "no-store" });
        if (stopped) return;
        if (response.status === 404) {
          setState("disabled");
          setMessage("Fleet UI is disabled on this host.");
          setPayload(null);
          return;
        }
        if (!response.ok) {
          throw new Error(`Fleet BFF HTTP ${response.status}`);
        }
        const next = await response.json() as FleetWebPayload;
        if (stopped) return;
        setPayload(next);
        setState("ready");
        setMessage("");
      } catch (error) {
        if (stopped) return;
        setState("error");
        setMessage(error instanceof Error ? error.message : "Fleet data unavailable");
      } finally {
        if (!stopped) timer = window.setTimeout(poll, 2_000);
      }
    }

    void poll();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  const facilities = useMemo(() => {
    const groups = new Map<string, FleetPPUView[]>();
    for (const ppu of payload?.ppus ?? []) {
      const key = ppu.identity.facility_id ?? "Unidentified Facility";
      const group = groups.get(key) ?? [];
      group.push(ppu);
      groups.set(key, group);
    }
    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [payload]);

  return (
    <main className="fleetPage">
      <section className="fleetShell">
        <div className="fleetHeading">
          <div><p>READ-ONLY CONTROL PLANE</p><h1>Facility / PPU Fleet Overview</h1><span>Manager failure never enters the local Site execution path.</span></div>
          <div className={`fleetHealth ${state}`}><i/><div><small>Fleet BFF</small><b>{state === "ready" ? "Online" : state === "loading" ? "Connecting" : state === "disabled" ? "Disabled" : "Unavailable"}</b></div></div>
        </div>

        {payload && <section className="fleetSummary" aria-label="Fleet summary">
          <article><small>Configured PPUs</small><b>{payload.summary.configured_ppus}</b></article>
          <article><small>Ready</small><b>{payload.summary.ready_ppus}</b></article>
          <article><small>Stale</small><b>{payload.summary.stale_ppus}</b></article>
          <article><small>Unknown</small><b>{payload.summary.unknown_ppus}</b></article>
          <article><small>Current Sites</small><b>{payload.summary.enabled_sites}/{payload.summary.reported_sites}</b></article>
          <article><small>Observation Store</small><b>{payload.manager.observation_store.mode.toUpperCase()}</b></article>
        </section>}

        {state !== "ready" && <section className="fleetNotice" role="status">
          <b>{state === "disabled" ? "Fleet demo is opt-in" : "Fleet snapshot unavailable"}</b>
          <p>{message}</p>
          {state === "disabled" && <p>Single-PPU programming remains available because Manager/Fleet is not part of the local execution path.</p>}
        </section>}

        {payload && <div className="fleetMeta">
          <span>Snapshot {payload.degraded ? "DEGRADED" : "HEALTHY"}</span>
          <span>Cache age {formatAge(payload.manager.cache_age_s)}</span>
          <span>Store {payload.manager.observation_store.healthy ? "healthy" : "degraded"}</span>
          <span>Read-only</span>
        </div>}

        {facilities.map(([facilityId, ppus]) => <section className="facilityBlock" key={facilityId}>
          <div className="facilityHead"><div><p>FACILITY</p><h2>{facilityId}</h2></div><span>{ppus.length} PPU{ppus.length === 1 ? "" : "s"}</span></div>
          <div className="ppuGrid">
            {ppus.map((ppu, index) => {
              const label = stateLabel(ppu);
              const stateClass = label.toLowerCase().replace(/\s+/g, "-");
              return <article className="ppuCard" key={`${ppu.identity.ppu_id ?? ppu.alias ?? "unknown"}-${index}`}>
                <div className="ppuCardHead"><div><small>{ppu.alias ?? "PPU"}</small><h3>{displayName(ppu)}</h3></div><span className={`ppuState ${stateClass}`}>{label}</span></div>
                <dl>
                  <div><dt>PPU ID</dt><dd>{ppu.identity.ppu_id ?? "—"}</dd></div>
                  <div><dt>Model</dt><dd>{ppu.identity.model ?? "—"}</dd></div>
                  <div><dt>Transport</dt><dd>{ppu.transport_state}</dd></div>
                  <div><dt>Execution</dt><dd>{ppu.execution_state}</dd></div>
                  <div><dt>Observation</dt><dd>{ppu.observation.state}</dd></div>
                  <div><dt>Last trusted</dt><dd>{ppu.observation.state === "current" ? "now" : formatAge(ppu.observation.stale_age_s)}</dd></div>
                </dl>
                <div className="capacityRow">
                  <div><small>Current capacity</small><b>{ppu.current_capacity.enabled_site_count}/{ppu.current_capacity.site_count}</b></div>
                  <div><small>{ppu.topology.source === "last_known" ? "Last-known topology" : "Topology"}</small><b>{ppu.topology.enabled_site_count}/{ppu.topology.site_count}</b></div>
                </div>
                {ppu.topology.sites.length > 0 && <div className="siteDots" aria-label={`${displayName(ppu)} Sites`}>
                  {ppu.topology.sites.map(site => <span key={site.site_id} className={site.enabled ? "enabled" : "disabled"} title={`SITE ${site.site_id} · ${site.state}`}>{site.site_id}</span>)}
                </div>}
              </article>;
            })}
          </div>
        </section>)}

        <footer className="fleetFooter">Fleet UI exposes sanitized operational state only. PPU endpoints, raw Manager errors and write controls are intentionally not browser-facing.</footer>
      </section>
    </main>
  );
}
