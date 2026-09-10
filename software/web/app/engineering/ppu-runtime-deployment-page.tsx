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

  return (
    <section className="ppuSiteConfiguration" aria-label="PPU Runtime Deployment Workspace">
      <header className="ppuSiteHeader">
        <div>
          <small>PPU APPLIANCE MANAGEMENT</small>
          <h2>Runtime Deployment</h2>
          <p>Install or upgrade the Plasma PPU Runtime through the independent factory/recovery Bootstrap path.</p>
        </div>
        <button className="ppuSiteButton" type="button" disabled={loading} onClick={() => void refresh()}>Refresh Registry</button>
      </header>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}

      <section className="ppuSiteCard" aria-label="Deployment target">
        <header className="ppuSiteCardHeader">
          <div>
            <small>TARGET</small>
            <h3>Select PPU</h3>
          </div>
        </header>
        <div className="ppuRegistryAddForm">
          <label>
            <span>Manager Registry Alias</span>
            <select value={selectedAlias} disabled={loading || !registry?.ppus.length} onChange={event => setSelectedAlias(event.target.value)}>
              {(registry?.ppus ?? []).filter(entry => entry.alias).map(entry => (
                <option key={entry.alias!} value={entry.alias!}>{entry.alias} — {entry.lifecycle}</option>
              ))}
            </select>
          </label>
          {selectedEntry && <p>Plasma Gateway registry endpoint: <code>{selectedEntry.endpoint}</code>. Bootstrap is a separate same-host commissioning service and is never tunneled through the Gateway.</p>}
        </div>
      </section>

      {selectedEntry ? (
        <PpuRuntimeDeployment
          key={selectedEntry.alias ?? selectedEntry.endpoint}
          entry={selectedEntry}
          hasActiveExecution={busy}
        />
      ) : (
        <section className="ppuSiteCard ppuEmptyRegistry">
          <h3>{loading ? "Loading Manager registry..." : "No registered PPU"}</h3>
          <p>Add a PPU to the Manager registry before starting factory Bootstrap pairing or Runtime deployment.</p>
        </section>
      )}
    </section>
  );
}
