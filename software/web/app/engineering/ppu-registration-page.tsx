"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FleetPPUView, FleetWebPayload } from "../fleet/fleet-contract";
import {
  addManagerPpu,
  getManagerFleet,
  getManagerRegistry,
  removeManagerPpu,
  selectManagerPpuForManagedOperations,
  setManagerPpuLifecycle,
  type ManagerRegistryEntry,
  type ManagerRegistryPayload,
} from "./ppu-registry-api";
import PpuNetworkConfiguration from "./ppu-network-configuration";
import {
  canValidateAndEnable,
  connectivityState,
  healthState,
  lifecycleState,
  validationBlockSummary,
  validationPrerequisites,
} from "./ppu-ui-state";
import "./ppu-site-configuration.css";

const ACTIVE_SITE_STATES = new Set(["queued", "submitting", "running", "stopping", "erase", "program", "verify", "read"]);

function fleetForEntry(entry: ManagerRegistryEntry, fleet: FleetWebPayload | null): FleetPPUView | null {
  if (!entry.alias || !fleet) return null;
  return fleet.ppus.find(ppu => ppu.alias === entry.alias) ?? null;
}

function hasActiveExecution(fleetView: FleetPPUView | null): boolean {
  if (!fleetView) return false;
  return fleetView.topology.sites.some(site => Boolean(site.current_job_id) || ACTIVE_SITE_STATES.has(site.state.toLowerCase()));
}

export default function PpuRegistrationPage() {
  const [registry, setRegistry] = useState<ManagerRegistryPayload | null>(null);
  const [fleet, setFleet] = useState<FleetWebPayload | null>(null);
  const [selectedAlias, setSelectedAlias] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newAlias, setNewAlias] = useState("");
  const [newGateway, setNewGateway] = useState("");
  const [removeCandidate, setRemoveCandidate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fleetError, setFleetError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    const [registryResult, fleetResult] = await Promise.allSettled([getManagerRegistry(), getManagerFleet()]);
    if (registryResult.status === "fulfilled") {
      setRegistry(registryResult.value);
      setError(null);
    } else {
      setError(registryResult.reason instanceof Error ? registryResult.reason.message : "Manager registry unavailable");
    }
    if (fleetResult.status === "fulfilled") {
      setFleet(fleetResult.value);
      setFleetError(null);
    } else {
      setFleetError(fleetResult.reason instanceof Error ? fleetResult.reason.message : "Fleet snapshot unavailable");
    }
    if (!quiet) setLoading(false);
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const timer = window.setInterval(() => { void refresh(true); }, 2500);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const aliases = useMemo(
    () => (registry?.ppus ?? []).map(entry => entry.alias).filter((alias): alias is string => Boolean(alias)),
    [registry],
  );
  const effectiveAlias = selectedAlias && aliases.includes(selectedAlias) ? selectedAlias : aliases[0] ?? null;
  const selectedEntry = registry?.ppus.find(entry => entry.alias === effectiveAlias) ?? null;
  const selectedFleet = selectedEntry ? fleetForEntry(selectedEntry, fleet) : null;
  const selectedLifecycle = selectedEntry ? lifecycleState(selectedEntry) : null;
  const selectedConnectivity = connectivityState(selectedFleet);
  const selectedHealth = healthState(selectedFleet);
  const selectedPrerequisites = validationPrerequisites(selectedFleet);
  const selectedCanValidate = canValidateAndEnable(selectedFleet);
  const selectedHasActiveExecution = hasActiveExecution(selectedFleet);
  const registryMutable = registry?.mutable === true;
  const validationBlockedReason = !registryMutable
    ? "Manager registry is read-only on this deployment."
    : selectedCanValidate
      ? null
      : `Failing prerequisites: ${validationBlockSummary(selectedFleet)}.`;

  async function runMutation(label: string, action: () => Promise<unknown>, success: string) {
    setBusyAction(label);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      await refresh(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${label} failed`);
    } finally {
      setBusyAction(null);
    }
  }

  async function addPpu() {
    const alias = newAlias.trim();
    const endpoint = newGateway.trim();
    if (!alias || !endpoint) return;
    await runMutation("add", () => addManagerPpu(alias, endpoint), `${alias} added as a known PPU connection. Programming Registration is still pending.`);
    setSelectedAlias(alias);
    setNewAlias("");
    setNewGateway("");
    setShowAddForm(false);
  }

  async function registerPpu() {
    if (!selectedEntry?.alias) return;
    await runMutation("register", () => setManagerPpuLifecycle(selectedEntry.alias!, "commissioned"), `${selectedEntry.alias} validated and registered for managed programming.`);
  }

  async function disableRegistration() {
    if (!selectedEntry?.alias) return;
    await runMutation("disable", () => setManagerPpuLifecycle(selectedEntry.alias!, "disabled"), `${selectedEntry.alias} programming Registration disabled.`);
  }

  async function selectForManagedOperations() {
    if (!selectedEntry?.alias || selectedEntry.lifecycle !== "commissioned") return;
    const alias = selectedEntry.alias;
    await runMutation("select", () => selectManagerPpuForManagedOperations(alias), `${alias} selected for managed programming operations.`);
  }

  async function removePpu() {
    if (!selectedEntry?.alias) return;
    const alias = selectedEntry.alias;
    await runMutation("remove", () => removeManagerPpu(alias), `${alias} removed from this Console's known PPU inventory.`);
    setRemoveCandidate(null);
  }

  return (
    <section className="ppuSiteConfiguration" aria-label="PPU Registration">
      <header className="ppuSiteHeader">
        <div><small>PPU</small><h2>Registration</h2><p>Manage which known PPU connections are admitted to this Console for programming operations. Platform maintenance remains a separate lifecycle.</p></div>
        <span className={`ppuSiteManagerState ${registry ? "" : "offline"}`}>{registry ? "Manager Online" : "Manager Unavailable"}</span>
      </header>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}
      {notice && <p className="ppuRegistryMessage success" role="status">{notice}</p>}
      {fleetError && registry && <p className="ppuRegistryMessage warning" role="status">Registry is available, but live Fleet status is unavailable: {fleetError}</p>}

      <section className="ppuSiteCard" aria-label="Known PPU inventory">
        <header className="ppuSiteCardHeader">
          <div><small>INVENTORY</small><h3>Known PPU Connections</h3></div>
          <div className="ppuSiteCardHeaderActions">
            <button className="ppuSiteButton" type="button" disabled={loading || busyAction !== null} onClick={() => void refresh()}>Refresh</button>
            <button className="ppuSiteButton primary" type="button" disabled={!registryMutable || busyAction !== null} onClick={() => setShowAddForm(value => !value)}>+ Add PPU Connection</button>
          </div>
        </header>
        {showAddForm && (
          <div className="ppuRegistryAddForm" aria-label="Add known PPU connection">
            <label><span>Console Alias</span><input value={newAlias} placeholder="line1-ppu-c" disabled={busyAction !== null} onChange={event => setNewAlias(event.target.value)} /></label>
            <label><span>Plasma Gateway Endpoint</span><input value={newGateway} placeholder="http://192.168.10.27:18080" disabled={busyAction !== null} onChange={event => setNewGateway(event.target.value)} /></label>
            <div className="ppuSiteCardHeaderActions">
              <button className="ppuSiteButton primary" type="button" disabled={!newAlias.trim() || !newGateway.trim() || busyAction !== null} onClick={() => void addPpu()}>{busyAction === "add" ? "Adding..." : "Add Connection"}</button>
              <button className="ppuSiteButton" type="button" disabled={busyAction !== null} onClick={() => setShowAddForm(false)}>Cancel</button>
            </div>
            <p>Adding an endpoint makes the appliance known to Console and Platform maintenance. It does not register the PPU for programming.</p>
          </div>
        )}
        <div className="ppuTableWrap">
          <table className="ppuTable">
            <thead><tr><th>Alias</th><th>PPU ID</th><th>Registration</th><th>Connectivity</th><th>Health</th><th>Plasma Gateway</th></tr></thead>
            <tbody>
              {(registry?.ppus ?? []).map(entry => {
                const fleetView = fleetForEntry(entry, fleet);
                const lifecycle = lifecycleState(entry);
                const connectivity = connectivityState(fleetView);
                const health = healthState(fleetView);
                return <tr key={entry.alias ?? entry.endpoint} className={entry.alias === effectiveAlias ? "selected" : ""} onClick={() => { if (entry.alias) setSelectedAlias(entry.alias); }}><td><span className="ppuIdLink">{entry.alias ?? "Unaliased"}</span></td><td>{fleetView?.identity.ppu_id ?? "Awaiting probe"}</td><td><span className="ppuDimensionPill" data-tone={lifecycle.tone}>{entry.lifecycle === "commissioned" ? "Registered" : entry.lifecycle === "disabled" ? "Registered / Disabled" : "Not Registered"}</span></td><td><span className="ppuDimensionPill" data-tone={connectivity.tone}>{connectivity.label}</span></td><td><span className="ppuDimensionPill" data-tone={health.tone}>{health.label}</span></td><td>{entry.endpoint}</td></tr>;
              })}
              {!loading && registry?.ppus.length === 0 && <tr><td colSpan={6}>No known PPU connection exists.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {selectedEntry && selectedLifecycle ? (
        <>
          <section className="ppuSiteCard" aria-label="Selected PPU Registration">
            <header className="ppuSiteCardHeader">
              <div className="ppuSiteCardHeaderActions"><h3>{selectedEntry.alias}</h3><span className="ppuDimensionPill" data-tone={selectedLifecycle.tone}>{selectedEntry.lifecycle === "commissioned" ? "Registered" : selectedEntry.lifecycle === "disabled" ? "Registered / Disabled" : "Not Registered"}</span></div>
              <div className="ppuSiteCardHeaderActions">
                {selectedEntry.lifecycle === "commissioned" && <button className="ppuSiteButton primary" type="button" disabled={busyAction !== null} onClick={() => void selectForManagedOperations()}>{busyAction === "select" ? "Selecting..." : "Use for Managed Operations"}</button>}
                {selectedEntry.lifecycle === "commissioned" && <button className="ppuSiteButton" type="button" disabled={!registryMutable || selectedHasActiveExecution || busyAction !== null} onClick={() => void disableRegistration()}>{busyAction === "disable" ? "Disabling..." : "Disable Registration"}</button>}
                <button className="ppuSiteButton danger" type="button" disabled={!registryMutable || selectedHasActiveExecution || busyAction !== null} onClick={() => setRemoveCandidate(selectedEntry.alias)}>Remove Connection</button>
              </div>
            </header>
            {removeCandidate === selectedEntry.alias && <div className="ppuRemoveConfirm" role="alert"><div><strong>Remove {selectedEntry.alias}?</strong><span>This removes Console inventory/Registration state only. It does not erase or reconfigure the physical PPU.</span></div><div className="ppuSiteCardHeaderActions"><button className="ppuSiteButton danger" type="button" disabled={busyAction !== null} onClick={() => void removePpu()}>{busyAction === "remove" ? "Removing..." : "Confirm Remove"}</button><button className="ppuSiteButton" type="button" disabled={busyAction !== null} onClick={() => setRemoveCandidate(null)}>Cancel</button></div></div>}
            <div className="ppuStateDimensionGrid" aria-label="PPU Registration observations">
              <article className="ppuStateDimensionCard" data-tone={selectedConnectivity.tone}><small>Connectivity</small><strong>{selectedConnectivity.label}</strong><p>{selectedConnectivity.reason}</p></article>
              <article className="ppuStateDimensionCard" data-tone={selectedHealth.tone}><small>Health</small><strong>{selectedHealth.label}</strong><p>{selectedHealth.reason}</p></article>
              <article className="ppuStateDimensionCard" data-tone={selectedLifecycle.tone}><small>Registration Lifecycle</small><strong>{selectedLifecycle.label}</strong><p>{selectedLifecycle.reason}</p></article>
            </div>
            {selectedEntry.lifecycle !== "commissioned" && (
              <div className="ppuReadinessPanel" aria-label="Registration prerequisites">
                <header><div><small>REGISTRATION READINESS</small><h4>Validate PPU before programming admission</h4></div><span>Platform maintenance is allowed independently of this admission.</span></header>
                <ul>{selectedPrerequisites.map(item => <li key={item.key} data-state={item.passed ? "pass" : "fail"}><span className="ppuReadinessIcon" aria-hidden="true">{item.passed ? "✓" : "×"}</span><strong>{item.label}</strong><span>{item.detail}</span><b>{item.passed ? "OK" : "FAIL"}</b></li>)}</ul>
                <footer>{validationBlockedReason ? <div className="ppuReadinessBlocked"><strong>Blocked</strong><span>{validationBlockedReason}</span></div> : <div className="ppuReadinessReady"><strong>Ready</strong><span>Current observation satisfies programming Registration prerequisites.</span></div>}<button className="ppuSiteButton primary" type="button" disabled={!registryMutable || !selectedCanValidate || busyAction !== null} onClick={() => void registerPpu()}>{busyAction === "register" ? "Registering..." : "Validate & Register for Programming"}</button></footer>
              </div>
            )}
            <div className="ppuInfoBody"><dl className="ppuInfoGrid"><div><dt>Console Alias</dt><dd>{selectedEntry.alias}</dd></div><div><dt>PPU ID</dt><dd>{selectedFleet?.identity.ppu_id ?? "Awaiting probe"}</dd></div><div><dt>Facility</dt><dd>{selectedFleet?.identity.facility_id ?? "—"}</dd></div><div><dt>Display Name</dt><dd>{selectedFleet?.identity.display_name ?? "—"}</dd></div><div className="wide"><dt>Plasma Gateway Endpoint</dt><dd>{selectedEntry.endpoint}</dd></div><div><dt>Reported Sites</dt><dd>{selectedFleet?.topology.site_count ?? "—"}</dd></div><div><dt>Active Execution</dt><dd>{selectedHasActiveExecution ? "Yes" : "No"}</dd></div></dl></div>
          </section>
          {selectedEntry.lifecycle === "commissioned" ? <PpuNetworkConfiguration entry={selectedEntry} hasActiveExecution={selectedHasActiveExecution} /> : <section className="ppuSiteCard" aria-label="Network commissioning registration gate"><p className="ppuSiteNote">Operational network commissioning remains locked until programming Registration is complete. The current endpoint remains sufficient for Bootstrap-based Platform maintenance.</p></section>}
        </>
      ) : <section className="ppuSiteCard ppuEmptyRegistry"><h3>{loading ? "Loading PPU inventory..." : "No PPU selected"}</h3></section>}

      <p className="ppuRegistryBoundary">Registration controls managed programming admission. Bootstrap maintenance authorization used by Platform Release update is a separate Platform security boundary.</p>
    </section>
  );
}
