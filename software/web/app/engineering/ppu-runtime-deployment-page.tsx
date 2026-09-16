"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FleetPPUView, FleetWebPayload } from "../fleet/fleet-contract";
import {
  getManagerFleet,
  getManagerRegistry,
  type ManagerRegistryEntry,
  type ManagerRegistryPayload,
} from "./ppu-registry-api";
import PpuRuntimeDeployment from "./ppu-runtime-deployment";

const ACTIVE_SITE_STATES = new Set(["queued", "submitting", "running", "stopping", "erase", "program", "verify", "read"]);

function fleetForEntry(entry: ManagerRegistryEntry, fleet: FleetWebPayload | null): FleetPPUView | null {
  if (!entry.alias || !fleet) return null;
  return fleet.ppus.find(item => item.alias === entry.alias) ?? null;
}

function activeExecution(view: FleetPPUView | null): boolean {
  if (!view) return false;
  return view.topology.sites.some(site => Boolean(site.current_job_id) || ACTIVE_SITE_STATES.has(site.state.toLowerCase()));
}

function trustedIdleObservation(view: FleetPPUView | null): boolean {
  if (!view || activeExecution(view)) return false;
  return (
    view.observation.state === "current"
    && view.transport_state === "reachable"
    && !view.identity_conflict
    && !view.degraded
    && view.topology.source === "current"
  );
}

export default function PpuRuntimeDeploymentPage() {
  const [registry, setRegistry] = useState<ManagerRegistryPayload | null>(null);
  const [fleet, setFleet] = useState<FleetWebPayload | null>(null);
  const [selectedAlias, setSelectedAlias] = useState<string>("");
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
    return () => window.clearTimeout(initial);
  }, [refresh]);

  const selectedEntry = useMemo(
    () => registry?.ppus.find(entry => entry.alias === selectedAlias) ?? null,
    [registry, selectedAlias],
  );
  const selectedFleet = selectedEntry ? fleetForEntry(selectedEntry, fleet) : null;
  const busy = activeExecution(selectedFleet);
  const trustedIdle = trustedIdleObservation(selectedFleet);

  return (
    <section className="ppuSiteConfiguration" aria-label="PPU Platform Firmware Workspace">
      <header className="ppuSiteHeader">
        <div>
          <small>PPU PLATFORM</small>
          <h2>Platform</h2>
          <p>Inspect Bootstrap and Runtime component versions and maintain the PPU platform independently of programming Registration.</p>
        </div>
        <button className="ppuSiteButton" type="button" disabled={loading} onClick={() => void refresh()}>Refresh Platform</button>
      </header>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}

      <section className="ppuSiteCard" aria-label="Platform target">
        <header className="ppuSiteCardHeader">
          <div>
            <small>TARGET</small>
            <h3>Select PPU</h3>
          </div>
        </header>
        <div className="ppuRegistryAddForm">
          <label>
            <span>Known PPU</span>
            <select value={selectedAlias} disabled={loading || !registry?.ppus.length} onChange={event => setSelectedAlias(event.target.value)}>
              {(registry?.ppus ?? []).filter(entry => entry.alias).map(entry => (
                <option key={entry.alias!} value={entry.alias!}>
                  {entry.alias} — {entry.lifecycle === "commissioned" ? "Registered" : entry.lifecycle === "disabled" ? "Registered / Disabled" : "Not Registered"}
                </option>
              ))}
            </select>
          </label>
          {selectedEntry && (
            <p>
              Platform maintenance uses the known PPU connection <code>{selectedEntry.endpoint}</code>. Operational Registration is a separate programming-management admission state.
            </p>
          )}
        </div>
      </section>

      {selectedEntry ? (
        <PpuRuntimeDeployment
          key={selectedEntry.alias ?? selectedEntry.endpoint}
          entry={selectedEntry}
          hasActiveExecution={busy}
          hasTrustedIdleObservation={trustedIdle}
        />
      ) : (
        <section className="ppuSiteCard ppuEmptyRegistry">
          <h3>{loading ? "Loading PPU inventory..." : "No known PPU connection"}</h3>
          <p>Add a PPU connection from Registration before Platform inspection or maintenance. Programming Registration itself is not required.</p>
        </section>
      )}
    </section>
  );
}
