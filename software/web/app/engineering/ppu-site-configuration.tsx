"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FleetPPUView, FleetSiteView, FleetWebPayload } from "../fleet/fleet-contract";
import {
  addManagerPpu,
  getManagerFleet,
  getManagerRegistry,
  removeManagerPpu,
  setManagerPpuLifecycle,
  type ManagerRegistryEntry,
  type ManagerRegistryPayload,
} from "./ppu-registry-api";
import "./ppu-site-configuration.css";

type PpuStatus = "Online" | "Pending" | "Offline" | "Disabled" | "Error" | "Unknown";

const ACTIVE_SITE_STATES = new Set(["queued", "submitting", "running", "stopping", "erase", "program", "verify", "read"]);

function statusClass(status: PpuStatus | string): string {
  return status.toLowerCase();
}

function lifecycleLabel(entry: ManagerRegistryEntry): string {
  if (entry.lifecycle === "commissioned") return "Validated / Enabled";
  if (entry.lifecycle === "disabled") return "Disabled";
  return "Pending";
}

function fleetForEntry(entry: ManagerRegistryEntry, fleet: FleetWebPayload | null): FleetPPUView | null {
  if (!entry.alias || !fleet) return null;
  return fleet.ppus.find(ppu => ppu.alias === entry.alias) ?? null;
}

function ppuStatus(entry: ManagerRegistryEntry, fleetView: FleetPPUView | null): PpuStatus {
  if (entry.lifecycle === "disabled") return "Disabled";
  if (entry.lifecycle === "pending") return "Pending";
  if (!fleetView) return "Unknown";
  if (fleetView.identity_conflict) return "Error";
  if (fleetView.transport_state === "unreachable") return "Offline";
  if (fleetView.execution_state !== "ready" || fleetView.degraded) return "Error";
  return "Online";
}

function canValidateAndEnable(fleetView: FleetPPUView | null): boolean {
  return Boolean(
    fleetView
    && fleetView.observation.state === "current"
    && fleetView.transport_state === "reachable"
    && fleetView.execution_state === "ready"
    && !fleetView.identity_conflict
    && !fleetView.degraded,
  );
}

function hasActiveExecution(fleetView: FleetPPUView | null): boolean {
  if (!fleetView) return false;
  return fleetView.topology.sites.some(site => (
    Boolean(site.current_job_id)
    || ACTIVE_SITE_STATES.has(site.state.toLowerCase())
  ));
}

function interfaceSummary(fleetView: FleetPPUView | null): string[] {
  if (!fleetView) return [];
  return Array.from(new Set(
    fleetView.topology.sites
      .map(site => site.interface)
      .filter((value): value is string => Boolean(value)),
  ));
}

function siteState(site: FleetSiteView): string {
  if (!site.enabled) return "Disabled";
  if (site.current_job_id || ACTIVE_SITE_STATES.has(site.state.toLowerCase())) return "Running";
  if (site.state.toLowerCase() === "error") return "Error";
  return site.state && site.state !== "unknown" ? site.state : "Ready";
}

export default function PpuSiteConfiguration() {
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
    const [registryResult, fleetResult] = await Promise.allSettled([
      getManagerRegistry(),
      getManagerFleet(),
    ]);

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
    const initialRefresh = window.setTimeout(() => { void refresh(); }, 0);
    const timer = window.setInterval(() => { void refresh(true); }, 2500);
    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const registryAliases = useMemo(
    () => (registry?.ppus ?? []).map(entry => entry.alias).filter((alias): alias is string => Boolean(alias)),
    [registry],
  );
  const effectiveSelectedAlias = selectedAlias && registryAliases.includes(selectedAlias)
    ? selectedAlias
    : registryAliases[0] ?? null;

  const selectedEntry = registry?.ppus.find(entry => entry.alias === effectiveSelectedAlias) ?? null;
  const selectedFleet = selectedEntry ? fleetForEntry(selectedEntry, fleet) : null;
  const selectedStatus = selectedEntry ? ppuStatus(selectedEntry, selectedFleet) : "Unknown";
  const selectedHasActiveExecution = hasActiveExecution(selectedFleet);
  const selectedInterfaces = interfaceSummary(selectedFleet);

  const statusCounts = useMemo(() => {
    const entries = registry?.ppus ?? [];
    const counts = { online: 0, pending: 0, offline: 0, disabled: 0, error: 0, unknown: 0 };
    for (const entry of entries) {
      const status = ppuStatus(entry, fleetForEntry(entry, fleet));
      if (status === "Online") counts.online += 1;
      else if (status === "Pending") counts.pending += 1;
      else if (status === "Offline") counts.offline += 1;
      else if (status === "Disabled") counts.disabled += 1;
      else if (status === "Error") counts.error += 1;
      else counts.unknown += 1;
    }
    return counts;
  }, [registry, fleet]);

  async function runMutation(label: string, action: () => Promise<unknown>, successMessage: string) {
    setBusyAction(label);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(successMessage);
      await refresh(true);
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : `${label} failed`);
    } finally {
      setBusyAction(null);
    }
  }

  async function addPpu() {
    const alias = newAlias.trim();
    const endpoint = newGateway.trim();
    if (!alias || !endpoint) return;
    await runMutation(
      "add",
      () => addManagerPpu(alias, endpoint),
      `${alias} added to the Manager registry as Pending.`,
    );
    setSelectedAlias(alias);
    setNewAlias("");
    setNewGateway("");
    setShowAddForm(false);
  }

  async function validateAndEnable() {
    if (!selectedEntry?.alias) return;
    await runMutation(
      "validate",
      () => setManagerPpuLifecycle(selectedEntry.alias!, "commissioned"),
      `${selectedEntry.alias} validated and enabled.`,
    );
  }

  async function disablePpu() {
    if (!selectedEntry?.alias) return;
    await runMutation(
      "disable",
      () => setManagerPpuLifecycle(selectedEntry.alias!, "disabled"),
      `${selectedEntry.alias} disabled.`,
    );
  }

  async function removePpu() {
    if (!selectedEntry?.alias) return;
    const alias = selectedEntry.alias;
    await runMutation(
      "remove",
      () => removeManagerPpu(alias),
      `${alias} removed from the Manager registry.`,
    );
    setRemoveCandidate(null);
  }

  const managerOnline = Boolean(registry);
  const registryMutable = registry?.mutable === true;

  return (
    <section className="ppuSiteConfiguration" aria-label="PPU and Site Configuration">
      <header className="ppuSiteHeader">
        <div>
          <small>PPU / SITE MANAGEMENT</small>
          <h2>PPU / Site Configuration</h2>
          <p>Add and remove Manager registry entries, validate new PPUs before use, and inspect the PPU-reported physical Site topology.</p>
        </div>
        <span className={`ppuSiteManagerState ${managerOnline ? "" : "offline"}`}>
          {managerOnline ? "Manager Online" : "Manager Unavailable"}
        </span>
      </header>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}
      {notice && <p className="ppuRegistryMessage success" role="status">{notice}</p>}
      {fleetError && managerOnline && <p className="ppuRegistryMessage warning" role="status">Registry is available, but live Fleet status is unavailable: {fleetError}</p>}

      <div className="ppuSiteLayout">
        <div className="ppuSiteColumn">
          <section className="ppuSiteCard" aria-label="PPU Registry">
            <header className="ppuSiteCardHeader">
              <div className="ppuSiteCardHeaderActions">
                <h3>PPU Registry</h3>
                {registry && <span className="ppuSiteFilter">{registry.storage === "file" ? "Runtime State" : "Config Seed"}</span>}
              </div>
              <div className="ppuSiteCardHeaderActions">
                <button className="ppuSiteButton" type="button" disabled={loading || busyAction !== null} onClick={() => void refresh()}>Refresh</button>
                <button
                  className="ppuSiteButton primary"
                  type="button"
                  disabled={!registryMutable || busyAction !== null}
                  title={registryMutable ? "Add a PPU Gateway to the Manager registry" : "Configure manager.registry_state_path to enable registry mutation"}
                  onClick={() => setShowAddForm(value => !value)}
                >
                  + Add PPU
                </button>
              </div>
            </header>

            {showAddForm && (
              <div className="ppuRegistryAddForm" aria-label="Add PPU to Manager registry">
                <label>
                  <span>Registry Alias</span>
                  <input value={newAlias} placeholder="line1-ppu-c" disabled={busyAction !== null} onChange={event => setNewAlias(event.target.value)} />
                </label>
                <label>
                  <span>Gateway Endpoint</span>
                  <input value={newGateway} placeholder="http://192.168.10.27:18080" disabled={busyAction !== null} onChange={event => setNewGateway(event.target.value)} />
                </label>
                <div className="ppuSiteCardHeaderActions">
                  <button className="ppuSiteButton primary" type="button" disabled={!newAlias.trim() || !newGateway.trim() || busyAction !== null} onClick={() => void addPpu()}>
                    {busyAction === "add" ? "Adding..." : "Add to Registry"}
                  </button>
                  <button className="ppuSiteButton" type="button" disabled={busyAction !== null} onClick={() => setShowAddForm(false)}>Cancel</button>
                </div>
                <p>Only Alias and Gateway Endpoint are entered manually. Canonical PPU identity, model and Site topology must be observed from the PPU before Validate &amp; Enable succeeds.</p>
              </div>
            )}

            <div className="ppuSiteFilters" aria-label="PPU status summary">
              <span className="ppuSiteFilter">All {registry?.ppus.length ?? 0}</span>
              <span className="ppuSiteFilter" data-tone="online">Online {statusCounts.online}</span>
              <span className="ppuSiteFilter" data-tone="pending">Pending {statusCounts.pending}</span>
              <span className="ppuSiteFilter">Offline {statusCounts.offline}</span>
              <span className="ppuSiteFilter">Disabled {statusCounts.disabled}</span>
              {statusCounts.error > 0 && <span className="ppuSiteFilter" data-tone="error">Error {statusCounts.error}</span>}
            </div>

            <div className="ppuTableWrap">
              <table className="ppuTable">
                <thead>
                  <tr>
                    <th>Alias</th>
                    <th>PPU ID</th>
                    <th>Lifecycle</th>
                    <th>Status</th>
                    <th>Sites</th>
                    <th>Gateway</th>
                  </tr>
                </thead>
                <tbody>
                  {(registry?.ppus ?? []).map(entry => {
                    const fleetView = fleetForEntry(entry, fleet);
                    const status = ppuStatus(entry, fleetView);
                    const key = entry.alias ?? entry.endpoint;
                    return (
                      <tr
                        key={key}
                        className={entry.alias && entry.alias === effectiveSelectedAlias ? "selected" : ""}
                        onClick={() => { if (entry.alias) { setSelectedAlias(entry.alias); setRemoveCandidate(null); } }}
                      >
                        <td><span className="ppuIdLink">{entry.alias ?? "Unaliased"}</span></td>
                        <td>{fleetView?.identity.ppu_id ?? "Awaiting probe"}</td>
                        <td><span className={`ppuLifecycle ${entry.lifecycle}`}>{lifecycleLabel(entry)}</span></td>
                        <td><span className={`ppuSiteStatus ${statusClass(status)}`}>{status}</span></td>
                        <td>{fleetView?.topology.site_count || "—"}</td>
                        <td>{entry.endpoint}</td>
                      </tr>
                    );
                  })}
                  {!loading && registry?.ppus.length === 0 && (
                    <tr><td colSpan={6}>No PPU is registered.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="ppuSiteCard" aria-label="New or discovered PPU">
            <header className="ppuSiteCardHeader">
              <h3>New / Discovered PPU</h3>
              <span className="ppuSiteFilter">0</span>
            </header>
            <div className="ppuDiscoveredBody">
              <p className="ppuSiteNote">
                <strong>Discovery boundary:</strong> automatic LAN discovery is not enabled in this phase. Add a known PPU by Gateway Endpoint; discovery can be added later without changing the registry admission flow.
              </p>
            </div>
          </section>
        </div>

        <div className="ppuSiteColumn">
          {selectedEntry ? (
            <>
              <section className="ppuSiteCard" aria-label="PPU Information">
                <header className="ppuSiteCardHeader">
                  <div className="ppuSiteCardHeaderActions">
                    <h3 className="ppuSelectedPpuTitle">
                      <span>Selected PPU</span>
                      <span className="ppuSelectedPpuDivider">·</span>
                      <strong>{selectedEntry.alias ?? "Unaliased PPU"}</strong>
                    </h3>
                    <span className={`ppuSiteStatus ${statusClass(selectedStatus)}`}>{selectedStatus}</span>
                  </div>
                  <div className="ppuSiteCardHeaderActions">
                    {(selectedEntry.lifecycle === "pending" || selectedEntry.lifecycle === "disabled") && (
                      <button
                        className="ppuSiteButton primary"
                        type="button"
                        disabled={!registryMutable || !canValidateAndEnable(selectedFleet) || busyAction !== null}
                        title={canValidateAndEnable(selectedFleet) ? "Validate the current PPU identity/topology and enable it" : "Wait for a current trusted PPU observation"}
                        onClick={() => void validateAndEnable()}
                      >
                        {busyAction === "validate" ? "Validating..." : "Validate & Enable"}
                      </button>
                    )}
                    {selectedEntry.lifecycle === "commissioned" && (
                      <button className="ppuSiteButton" type="button" disabled={!registryMutable || selectedHasActiveExecution || busyAction !== null} onClick={() => void disablePpu()}>
                        {busyAction === "disable" ? "Disabling..." : "Disable"}
                      </button>
                    )}
                    <button className="ppuSiteButton" type="button" disabled={busyAction !== null} onClick={() => void refresh()}>Health Check</button>
                    <button
                      className="ppuSiteButton danger"
                      type="button"
                      disabled={!registryMutable || selectedHasActiveExecution || busyAction !== null}
                      title={selectedHasActiveExecution ? "Stop active Jobs before removing this PPU" : "Remove this PPU from the Manager registry"}
                      onClick={() => setRemoveCandidate(selectedEntry.alias)}
                    >
                      Remove PPU
                    </button>
                  </div>
                </header>

                {removeCandidate === selectedEntry.alias && (
                  <div className="ppuRemoveConfirm" role="alert">
                    <div>
                      <strong>Remove {selectedEntry.alias} from Manager registry?</strong>
                      <span>This removes Manager inventory state only. It does not erase, reset, power off, or reconfigure the physical PPU.</span>
                    </div>
                    <div className="ppuSiteCardHeaderActions">
                      <button className="ppuSiteButton danger" type="button" disabled={busyAction !== null} onClick={() => void removePpu()}>
                        {busyAction === "remove" ? "Removing..." : "Confirm Remove"}
                      </button>
                      <button className="ppuSiteButton" type="button" disabled={busyAction !== null} onClick={() => setRemoveCandidate(null)}>Cancel</button>
                    </div>
                  </div>
                )}

                <div className="ppuInfoBody">
                  <dl className="ppuInfoGrid">
                    <div><dt>Registry Alias</dt><dd>{selectedEntry.alias ?? "—"}</dd></div>
                    <div><dt>Lifecycle</dt><dd>{lifecycleLabel(selectedEntry)}</dd></div>
                    <div><dt>PPU ID</dt><dd>{selectedFleet?.identity.ppu_id ?? "Awaiting probe"}</dd></div>
                    <div><dt>Status</dt><dd><span className={`ppuSiteStatus ${statusClass(selectedStatus)}`}>{selectedStatus}</span></dd></div>
                    <div><dt>Gateway Endpoint</dt><dd>{selectedEntry.endpoint}</dd></div>
                    <div><dt>Observation</dt><dd>{selectedFleet?.observation.state ?? "unknown"}</dd></div>
                    <div><dt>Execution</dt><dd>{selectedFleet?.execution_state ?? "unknown"}</dd></div>
                    <div><dt>Facility</dt><dd>{selectedFleet?.identity.facility_id ?? "—"}</dd></div>
                    <div><dt>Display Name</dt><dd>{selectedFleet?.identity.display_name ?? "—"}</dd></div>
                    <div><dt>HW Model</dt><dd>{selectedFleet?.identity.model ?? "—"}</dd></div>
                    <div><dt>Manager Registered At</dt><dd>{selectedEntry.registered_at}</dd></div>
                    <div><dt>Registry Updated At</dt><dd>{selectedEntry.updated_at}</dd></div>
                    <div className="full">
                      <dt>Reported Interfaces</dt>
                      <dd className="ppuCapabilityList">
                        {selectedInterfaces.length
                          ? selectedInterfaces.map(value => <span className="ppuCapabilityTag" key={value}>{value}</span>)
                          : <span className="ppuCapabilityTag">Awaiting topology</span>}
                      </dd>
                    </div>
                  </dl>
                </div>
              </section>

              <section className="ppuSiteCard" aria-label="Site Configuration">
                <header className="ppuSiteCardHeader">
                  <div>
                    <h3>Site Configuration</h3>
                  </div>
                  <span className="ppuSiteFilter">PPU-reported topology</span>
                </header>

                <div className="ppuSiteSummary" aria-label="Site topology summary">
                  <div className="ppuSiteSummaryItem">
                    <span>Physical Sites</span>
                    <strong>{selectedFleet?.topology.site_count || "—"}</strong>
                  </div>
                  <div className="ppuSiteSummaryItem">
                    <span>Enabled Sites</span>
                    <strong>{selectedFleet?.topology.enabled_site_count ?? "—"}</strong>
                  </div>
                  <div className="ppuSiteSummaryItem">
                    <span>Topology Source</span>
                    <strong>{selectedFleet?.topology.source ?? "none"}</strong>
                  </div>
                </div>

                {selectedFleet?.topology.sites.length ? (
                  <div className="ppuTableWrap">
                    <table className="ppuTable">
                      <thead>
                        <tr>
                          <th>Site ID</th>
                          <th>Enabled</th>
                          <th>Status</th>
                          <th>Interface</th>
                          <th>Target</th>
                          <th>Current Job</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedFleet.topology.sites.map(site => {
                          const state = siteState(site);
                          return (
                            <tr key={`${selectedEntry.alias}-site-${site.site_id}`}>
                              <td><span className="ppuIdLink">SITE{site.site_id}</span></td>
                              <td><input className="ppuSiteToggle" type="checkbox" checked={site.enabled} disabled readOnly aria-label={`SITE${site.site_id} enabled state`} /></td>
                              <td><span className={`ppuSiteStatus ${statusClass(state)}`}>{state}</span></td>
                              <td>{site.interface ?? "—"}</td>
                              <td>{site.target ?? "—"}</td>
                              <td>{site.current_job_id ?? "—"}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="ppuSiteNote"><strong>Topology unavailable:</strong> Manager has not obtained a current or last-known PPU topology yet. Site count is never entered manually.</p>
                )}

                <p className="ppuSiteNote">
                  <strong>Current boundary:</strong> Site enabled state shown here is PPU-reported and read-only in this slice. A separate PPU-owned Site configuration API is required before the Console can persist Site Enable/Disable changes.
                </p>
              </section>
            </>
          ) : (
            <section className="ppuSiteCard ppuEmptyRegistry" aria-label="Empty PPU registry">
              <h3>{loading ? "Loading Manager registry..." : "No selectable PPU"}</h3>
              <p>{loading ? "Reading Manager-owned inventory and Fleet state." : "Add a PPU with an alias and Gateway endpoint to begin validation."}</p>
            </section>
          )}
        </div>
      </div>

      <p className="ppuRegistryBoundary">
        Manager registry mutations are {registryMutable ? "enabled and persisted by Manager runtime state" : "read-only on this deployment"}. `manager.yaml` remains deployment/bootstrap configuration and is never edited by this page.
      </p>
    </section>
  );
}