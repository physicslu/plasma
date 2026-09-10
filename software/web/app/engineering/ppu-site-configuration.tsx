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
import PpuSiteDesiredConfiguration from "./ppu-site-desired-configuration";
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
  const selectedLifecycle = selectedEntry ? lifecycleState(selectedEntry) : null;
  const selectedConnectivity = connectivityState(selectedFleet);
  const selectedHealth = healthState(selectedFleet);
  const selectedPrerequisites = validationPrerequisites(selectedFleet);
  const selectedCanValidate = canValidateAndEnable(selectedFleet);
  const selectedHasActiveExecution = hasActiveExecution(selectedFleet);
  const selectedInterfaces = interfaceSummary(selectedFleet);

  const stateCounts = useMemo(() => {
    const counts = {
      lifecycle: { commissioned: 0, pending: 0, disabled: 0 },
      connectivity: { online: 0, offline: 0, unknown: 0 },
      health: { healthy: 0, degraded: 0, error: 0, unknown: 0 },
    };
    for (const entry of registry?.ppus ?? []) {
      if (entry.lifecycle === "commissioned") counts.lifecycle.commissioned += 1;
      else if (entry.lifecycle === "disabled") counts.lifecycle.disabled += 1;
      else counts.lifecycle.pending += 1;

      const fleetView = fleetForEntry(entry, fleet);
      const connectivity = connectivityState(fleetView).label;
      if (connectivity === "Online") counts.connectivity.online += 1;
      else if (connectivity === "Offline") counts.connectivity.offline += 1;
      else counts.connectivity.unknown += 1;

      const health = healthState(fleetView).label;
      if (health === "Healthy") counts.health.healthy += 1;
      else if (health === "Degraded") counts.health.degraded += 1;
      else if (health === "Error") counts.health.error += 1;
      else counts.health.unknown += 1;
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

  async function selectForManagedOperations() {
    if (!selectedEntry?.alias || selectedEntry.lifecycle !== "commissioned") return;
    const alias = selectedEntry.alias;
    await runMutation(
      "select",
      () => selectManagerPpuForManagedOperations(alias),
      `${alias} selected for Managed operations.`,
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
  const validationBlockedReason = !registryMutable
    ? "Manager registry is read-only on this deployment."
    : selectedCanValidate
      ? null
      : `Failing prerequisites: ${validationBlockSummary(selectedFleet)}.`;

  return (
    <section className="ppuSiteConfiguration" aria-label="PPU and Site Configuration">
      <header className="ppuSiteHeader">
        <div>
          <small>PPU / SITE MANAGEMENT</small>
          <h2>PPU / Site Configuration</h2>
          <p>Add and remove Manager registry entries, validate new PPUs before use, and manage PPU-owned Site desired configuration.</p>
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
                  title={registryMutable ? "Add a Plasma Gateway to the Manager registry" : "Configure manager.registry_state_path to enable registry mutation"}
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
                  <span>Plasma Gateway Endpoint</span>
                  <input value={newGateway} placeholder="http://192.168.10.27:18080" disabled={busyAction !== null} onChange={event => setNewGateway(event.target.value)} />
                </label>
                <div className="ppuSiteCardHeaderActions">
                  <button className="ppuSiteButton primary" type="button" disabled={!newAlias.trim() || !newGateway.trim() || busyAction !== null} onClick={() => void addPpu()}>
                    {busyAction === "add" ? "Adding..." : "Add to Registry"}
                  </button>
                  <button className="ppuSiteButton" type="button" disabled={busyAction !== null} onClick={() => setShowAddForm(false)}>Cancel</button>
                </div>
                <p>Only Alias and Plasma Gateway Endpoint are entered manually. Canonical PPU identity, model and Site topology must be observed from the PPU before Validate &amp; Enable succeeds.</p>
              </div>
            )}

            <div className="ppuStateSummaryGrid" aria-label="PPU orthogonal state summary">
              <div className="ppuStateSummaryGroup">
                <small>Lifecycle</small>
                <span>Commissioned <strong>{stateCounts.lifecycle.commissioned}</strong></span>
                <span>Pending <strong>{stateCounts.lifecycle.pending}</strong></span>
                <span>Disabled <strong>{stateCounts.lifecycle.disabled}</strong></span>
              </div>
              <div className="ppuStateSummaryGroup">
                <small>Connectivity</small>
                <span>Online <strong>{stateCounts.connectivity.online}</strong></span>
                <span>Offline <strong>{stateCounts.connectivity.offline}</strong></span>
                {stateCounts.connectivity.unknown > 0 && <span>Unknown <strong>{stateCounts.connectivity.unknown}</strong></span>}
              </div>
              <div className="ppuStateSummaryGroup">
                <small>Health</small>
                <span>Healthy <strong>{stateCounts.health.healthy}</strong></span>
                <span>Degraded <strong>{stateCounts.health.degraded}</strong></span>
                {stateCounts.health.error > 0 && <span>Error <strong>{stateCounts.health.error}</strong></span>}
                {stateCounts.health.unknown > 0 && <span>Unknown <strong>{stateCounts.health.unknown}</strong></span>}
              </div>
            </div>

            <div className="ppuTableWrap">
              <table className="ppuTable">
                <thead>
                  <tr>
                    <th>Alias</th>
                    <th>PPU ID</th>
                    <th>Lifecycle</th>
                    <th>Connectivity</th>
                    <th>Health</th>
                    <th>Sites</th>
                    <th>Plasma Gateway</th>
                  </tr>
                </thead>
                <tbody>
                  {(registry?.ppus ?? []).map(entry => {
                    const fleetView = fleetForEntry(entry, fleet);
                    const lifecycle = lifecycleState(entry);
                    const connectivity = connectivityState(fleetView);
                    const health = healthState(fleetView);
                    const key = entry.alias ?? entry.endpoint;
                    return (
                      <tr
                        key={key}
                        className={entry.alias && entry.alias === effectiveSelectedAlias ? "selected" : ""}
                        onClick={() => { if (entry.alias) { setSelectedAlias(entry.alias); setRemoveCandidate(null); } }}
                      >
                        <td><span className="ppuIdLink">{entry.alias ?? "Unaliased"}</span></td>
                        <td>{fleetView?.identity.ppu_id ?? "Awaiting probe"}</td>
                        <td><span className="ppuDimensionPill" data-tone={lifecycle.tone} title={lifecycle.reason}>{lifecycle.label}</span></td>
                        <td><span className="ppuDimensionPill" data-tone={connectivity.tone} title={connectivity.reason}>{connectivity.label}</span></td>
                        <td><span className="ppuDimensionPill" data-tone={health.tone} title={health.reason}>{health.label}</span></td>
                        <td>{fleetView?.topology.site_count || "—"}</td>
                        <td>{entry.endpoint}</td>
                      </tr>
                    );
                  })}
                  {!loading && registry?.ppus.length === 0 && (
                    <tr><td colSpan={7}>No PPU is registered.</td></tr>
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
                <strong>Discovery boundary:</strong> automatic LAN discovery is not enabled in this phase. Add a known PPU by Plasma Gateway Endpoint; discovery can be added later without changing the registry admission flow.
              </p>
            </div>
          </section>
        </div>

        <div className="ppuSiteColumn">
          {selectedEntry && selectedLifecycle ? (
            <>
              <section className="ppuSiteCard" aria-label="PPU Information">
                <header className="ppuSiteCardHeader">
                  <div className="ppuSiteCardHeaderActions">
                    <h3>{selectedEntry.alias ?? "Unaliased PPU"}</h3>
                    <span className="ppuDimensionPill" data-tone={selectedLifecycle.tone}>{selectedLifecycle.label}</span>
                  </div>
                  <div className="ppuSiteCardHeaderActions">
                    {selectedEntry.lifecycle === "commissioned" && (
                      <button
                        className="ppuSiteButton primary"
                        type="button"
                        disabled={busyAction !== null}
                        title="Select this validated Manager registry alias for Managed Programming and Diagnostics"
                        onClick={() => void selectForManagedOperations()}
                      >
                        {busyAction === "select" ? "Selecting..." : "Use for Managed Operations"}
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

                <div className="ppuStateDimensionGrid" aria-label="PPU orthogonal state dimensions">
                  <article className="ppuStateDimensionCard" data-tone={selectedLifecycle.tone}>
                    <small>Lifecycle</small>
                    <strong>{selectedLifecycle.label}</strong>
                    <p>{selectedLifecycle.reason}</p>
                  </article>
                  <article className="ppuStateDimensionCard" data-tone={selectedConnectivity.tone}>
                    <small>Connectivity</small>
                    <strong>{selectedConnectivity.label}</strong>
                    <p>{selectedConnectivity.reason}</p>
                  </article>
                  <article className="ppuStateDimensionCard" data-tone={selectedHealth.tone}>
                    <small>Health</small>
                    <strong>{selectedHealth.label}</strong>
                    <p>{selectedHealth.reason}</p>
                  </article>
                </div>

                {selectedEntry.lifecycle !== "commissioned" && (
                  <div className="ppuReadinessPanel" aria-label="Validate prerequisites">
                    <header>
                      <div>
                        <small>READINESS</small>
                        <h4>Validate prerequisites</h4>
                      </div>
                      <span>All prerequisites must pass before this PPU can be enabled.</span>
                    </header>
                    <ul>
                      {selectedPrerequisites.map(item => (
                        <li key={item.key} data-state={item.passed ? "pass" : "fail"}>
                          <span className="ppuReadinessIcon" aria-hidden="true">{item.passed ? "✓" : "×"}</span>
                          <strong>{item.label}</strong>
                          <span>{item.detail}</span>
                          <b>{item.passed ? "OK" : "FAIL"}</b>
                        </li>
                      ))}
                    </ul>
                    <footer>
                      {validationBlockedReason ? (
                        <div className="ppuReadinessBlocked" role="status">
                          <strong>Blocked</strong>
                          <span>{validationBlockedReason}</span>
                        </div>
                      ) : (
                        <div className="ppuReadinessReady" role="status">
                          <strong>Ready</strong>
                          <span>Current observation satisfies the admission prerequisites.</span>
                        </div>
                      )}
                      <button
                        className="ppuSiteButton primary"
                        type="button"
                        disabled={!registryMutable || !selectedCanValidate || busyAction !== null}
                        title={validationBlockedReason ?? "Validate the current PPU identity/topology and enable it"}
                        onClick={() => void validateAndEnable()}
                      >
                        {busyAction === "validate" ? "Validating..." : "Validate & Enable"}
                      </button>
                    </footer>
                  </div>
                )}

                <div className="ppuInfoBody">
                  <dl className="ppuInfoGrid">
                    <div><dt>Registry Alias</dt><dd>{selectedEntry.alias ?? "—"}</dd></div>
                    <div><dt>PPU ID</dt><dd>{selectedFleet?.identity.ppu_id ?? "Awaiting probe"}</dd></div>
                    <div><dt>Observation</dt><dd>{selectedFleet?.observation.state ?? "unknown"}</dd></div>
                    <div><dt>Execution</dt><dd>{selectedFleet?.execution_state ?? "unknown"}</dd></div>
                    <div className="wide"><dt>Plasma Gateway Endpoint</dt><dd>{selectedEntry.endpoint}</dd></div>
                    <div><dt>Topology Source</dt><dd>{selectedFleet?.topology.source ?? "none"}</dd></div>
                    <div><dt>Reported Sites</dt><dd>{selectedFleet?.topology.site_count ?? "—"}</dd></div>
                    <div className="wide"><dt>Display Name</dt><dd>{selectedFleet?.identity.display_name ?? "—"}</dd></div>
                    <div><dt>HW Model</dt><dd>{selectedFleet?.identity.model ?? "—"}</dd></div>
                    <div><dt>Facility</dt><dd>{selectedFleet?.identity.facility_id ?? "—"}</dd></div>
                    <div className="wide"><dt>Manager Registered At</dt><dd>{selectedEntry.registered_at}</dd></div>
                    <div className="wide"><dt>Registry Updated At</dt><dd>{selectedEntry.updated_at}</dd></div>
                    <div className="wide">
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

              <PpuNetworkConfiguration
                entry={selectedEntry}
                hasActiveExecution={selectedHasActiveExecution}
              />

              <PpuSiteDesiredConfiguration
                entry={selectedEntry}
                hasActiveExecution={selectedHasActiveExecution}
              />
            </>
          ) : (
            <section className="ppuSiteCard ppuEmptyRegistry" aria-label="Empty PPU registry">
              <h3>{loading ? "Loading Manager registry..." : "No selectable PPU"}</h3>
              <p>{loading ? "Reading Manager-owned inventory and Fleet state." : "Add a PPU with an alias and Plasma Gateway Endpoint to begin validation."}</p>
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
