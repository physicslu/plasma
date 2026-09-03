"use client";

import { useEffect, useMemo, useState } from "react";
import {
  commissionManagerPpuStaticNetwork,
  getManagerPpuNetwork,
  getManagerPpuNetworkCommissioning,
  saveManagerPpuNetwork,
  type ManagerNetworkCommissioning,
  type ManagerRegistryEntry,
  type PPUNetworkPayload,
  type PPUNetworkMode,
} from "./ppu-registry-api";
import "./ppu-network-configuration.css";

type Props = {
  entry: ManagerRegistryEntry;
  hasActiveExecution: boolean;
  onRegistryChanged?: () => void | Promise<void>;
};

const ACTIVE_COMMISSIONING_STATES = new Set([
  "requested",
  "desired_saved",
  "apply_requested",
  "reconnecting",
  "identity_verified",
  "activation_committed",
  "registry_reconciled",
  "rollback_wait",
]);

function dnsText(values: string[]): string {
  return values.join(", ");
}

function parseDns(value: string): string[] {
  return value
    .split(",")
    .map(item => item.trim())
    .filter(Boolean);
}

export default function PpuNetworkConfiguration({ entry, hasActiveExecution, onRegistryChanged }: Props) {
  const [network, setNetwork] = useState<PPUNetworkPayload | null>(null);
  const [commissioning, setCommissioning] = useState<ManagerNetworkCommissioning | null>(null);
  const [loadedAlias, setLoadedAlias] = useState<string | null>(null);
  const [mode, setMode] = useState<PPUNetworkMode>("dhcp");
  const [address, setAddress] = useState("");
  const [prefixLength, setPrefixLength] = useState("24");
  const [gateway, setGateway] = useState("");
  const [dnsServers, setDnsServers] = useState("");
  const [saving, setSaving] = useState(false);
  const [commissioningBusy, setCommissioningBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [commissioned, setCommissioned] = useState(false);

  useEffect(() => {
    if (!entry.alias) return;
    let cancelled = false;
    const alias = entry.alias;
    void (async () => {
      try {
        const payload = await getManagerPpuNetwork(alias);
        if (cancelled) return;
        const settings = payload.ppu_network_settings;
        setNetwork(payload);
        setMode(settings.mode);
        setAddress(settings.address ?? "");
        setPrefixLength(settings.prefix_length == null ? "24" : String(settings.prefix_length));
        setGateway(settings.gateway ?? "");
        setDnsServers(dnsText(settings.dns_servers));
        setError(null);
      } catch (loadError) {
        if (!cancelled) {
          setNetwork(null);
          setError(loadError instanceof Error ? loadError.message : "PPU network settings unavailable");
        }
      }
      try {
        const transaction = await getManagerPpuNetworkCommissioning(alias);
        if (!cancelled) setCommissioning(transaction);
      } catch (loadError) {
        if (!cancelled) {
          setCommissioning(null);
          setError(loadError instanceof Error ? loadError.message : "Manager network commissioning status unavailable");
        }
      }
      if (!cancelled) {
        setSaved(false);
        setCommissioned(false);
        setLoadedAlias(alias);
      }
    })();
    return () => { cancelled = true; };
  }, [entry.alias, entry.endpoint]);

  const loading = Boolean(entry.alias) && loadedAlias !== entry.alias;
  const parsedPrefix = Number(prefixLength);
  const desired = useMemo(() => ({
    mode,
    address: mode === "static" ? address.trim() || null : null,
    prefix_length: mode === "static" && Number.isInteger(parsedPrefix) ? parsedPrefix : null,
    gateway: mode === "static" ? gateway.trim() || null : null,
    dns_servers: mode === "static" ? parseDns(dnsServers) : [],
  }), [address, dnsServers, gateway, mode, parsedPrefix]);

  const valid = mode === "dhcp" || Boolean(
    desired.address
    && desired.prefix_length != null
    && desired.prefix_length >= 1
    && desired.prefix_length <= 32,
  );
  const current = network?.ppu_network_settings;
  const changed = Boolean(current && (
    current.mode !== desired.mode
    || current.address !== desired.address
    || current.prefix_length !== desired.prefix_length
    || current.gateway !== desired.gateway
    || current.dns_servers.join(",") !== desired.dns_servers.join(",")
  ));
  const activationBusy = Boolean(network?.activation.state && [
    "scheduled",
    "applying",
    "applied_waiting_commit",
    "rolling_back",
  ].includes(network.activation.state));
  const commissioningActive = Boolean(commissioning && ACTIVE_COMMISSIONING_STATES.has(commissioning.state));
  const recoveryRequired = commissioning?.state === "recovery_required";
  const commissioningBlocking = commissioningActive || recoveryRequired;
  const lifecycleWritable = entry.lifecycle === "commissioned";
  const canEdit = lifecycleWritable && !hasActiveExecution && !activationBusy && !commissioningBlocking;
  const canSave = canEdit;
  const canCommission = canEdit
    && mode === "static"
    && valid
    && network?.activation.supported === true;

  function applyNetworkPayload(payload: PPUNetworkPayload) {
    const settings = payload.ppu_network_settings;
    setNetwork(payload);
    setMode(settings.mode);
    setAddress(settings.address ?? "");
    setPrefixLength(settings.prefix_length == null ? "24" : String(settings.prefix_length));
    setGateway(settings.gateway ?? "");
    setDnsServers(dnsText(settings.dns_servers));
  }

  async function saveDesired() {
    if (!entry.alias || !valid || !changed || !canSave || saving || commissioningBusy) return;
    setSaving(true);
    setSaved(false);
    setCommissioned(false);
    try {
      const payload = await saveManagerPpuNetwork(entry.alias, desired);
      applyNetworkPayload(payload);
      setError(null);
      setSaved(true);
      setLoadedAlias(entry.alias);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "PPU network settings update failed");
    } finally {
      setSaving(false);
    }
  }

  async function commissionStatic() {
    if (!entry.alias || !canCommission || commissioningBusy || saving || desired.mode !== "static") return;
    setCommissioningBusy(true);
    setSaved(false);
    setCommissioned(false);
    try {
      const result = await commissionManagerPpuStaticNetwork(entry.alias, desired, 20);
      setCommissioning(result.commissioning);
      setError(null);
      setCommissioned(true);
      const refreshed = await getManagerPpuNetwork(entry.alias);
      applyNetworkPayload(refreshed);
      setLoadedAlias(entry.alias);
      await onRegistryChanged?.();
    } catch (commissionError) {
      setError(commissionError instanceof Error ? commissionError.message : "Static IPv4 commissioning failed");
      try {
        setCommissioning(await getManagerPpuNetworkCommissioning(entry.alias));
      } catch {
        // Preserve the primary commissioning error. The Manager journal remains authoritative.
      }
    } finally {
      setCommissioningBusy(false);
    }
  }

  const controlsDisabled = loading || saving || commissioningBusy || !canEdit;

  return (
    <section className="ppuSiteCard ppuNetworkConfiguration" aria-label="PPU Network Configuration">
      <header className="ppuSiteCardHeader">
        <div>
          <h3>PPU Network Configuration</h3>
          <p className="ppuNetworkSubtitle">PPU-owned desired <code>eth0</code> configuration. Save stores intent only; Static IPv4 commissioning is a separate Manager-owned transaction.</p>
        </div>
        <div className="ppuSiteCardHeaderActions">
          <span className="ppuSiteFilter">REV {current?.revision ?? "—"}</span>
          <span className="ppuSiteFilter">{network?.activation.supported ? "Activation Ready" : "Desired State Only"}</span>
        </div>
      </header>

      <div className="ppuSiteSummary">
        <span>Interface <strong>{current?.interface ?? "eth0"}</strong></span>
        <span>Desired Mode <strong>{current?.mode?.toUpperCase() ?? "—"}</strong></span>
        <span>Activation <strong>{network?.activation.state ?? "unknown"}</strong></span>
        <span>Committed REV <strong>{network?.activation.committed_revision ?? "—"}</strong></span>
        <span>Manager Txn <strong>{commissioning?.state ?? "none"}</strong></span>
      </div>

      <div className="ppuNetworkGrid">
        <label>
          <span>Mode</span>
          <select
            aria-label="PPU network mode"
            value={mode}
            disabled={controlsDisabled}
            onChange={event => { setSaved(false); setCommissioned(false); setMode(event.target.value as PPUNetworkMode); }}
          >
            <option value="dhcp">DHCP</option>
            <option value="static">Static IPv4</option>
          </select>
        </label>

        {mode === "static" && (
          <>
            <label>
              <span>IPv4 Address</span>
              <input
                aria-label="PPU static IPv4 address"
                value={address}
                placeholder="192.168.10.21"
                disabled={controlsDisabled}
                onChange={event => { setSaved(false); setCommissioned(false); setAddress(event.target.value); }}
              />
            </label>
            <label>
              <span>Prefix Length</span>
              <input
                aria-label="PPU static prefix length"
                type="number"
                min="1"
                max="32"
                value={prefixLength}
                disabled={controlsDisabled}
                onChange={event => { setSaved(false); setCommissioned(false); setPrefixLength(event.target.value); }}
              />
            </label>
            <label>
              <span>Default Gateway</span>
              <input
                aria-label="PPU static default gateway"
                value={gateway}
                placeholder="192.168.10.1"
                disabled={controlsDisabled}
                onChange={event => { setSaved(false); setCommissioned(false); setGateway(event.target.value); }}
              />
            </label>
            <label className="wide">
              <span>DNS Servers</span>
              <input
                aria-label="PPU DNS servers"
                value={dnsServers}
                placeholder="192.168.10.1, 8.8.8.8"
                disabled={controlsDisabled}
                onChange={event => { setSaved(false); setCommissioned(false); setDnsServers(event.target.value); }}
              />
            </label>
          </>
        )}
      </div>

      {mode === "static" && (
        <p className="ppuSiteNote">
          <strong>Network terminology:</strong> Default Gateway is the Linux Layer-3 next-hop router for <code>eth0</code>. It is not the Plasma Gateway service running on this PPU.
        </p>
      )}

      {commissioning?.candidate_endpoint && (
        <p className="ppuSiteNote">
          <strong>Commissioning evidence:</strong> candidate Plasma Gateway Endpoint <code>{commissioning.candidate_endpoint}</code>; transaction <code>{commissioning.transaction_id}</code>.
        </p>
      )}
      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}
      {saved && !loading && <p className="ppuRegistryMessage success" role="status">Desired PPU network settings saved. Running <code>eth0</code> was not activated by this action.</p>}
      {commissioned && commissioning?.state === "completed" && (
        <p className="ppuRegistryMessage success" role="status">Static IPv4 commissioning completed. Manager verified the same <code>ppu_id</code>, committed the PPU activation, and reconciled the durable Plasma Gateway Endpoint.</p>
      )}
      {recoveryRequired && (
        <p className="ppuRegistryMessage warning" role="alert"><strong>Recovery required:</strong> {commissioning?.error_message ?? "Manager cannot prove a safe automatic continuation."} Do not start another network transaction until the PPU network and Manager registry are reconciled.</p>
      )}

      {!lifecycleWritable && (
        <p className="ppuSiteNote"><strong>Write gate:</strong> complete Validate &amp; Enable before changing PPU desired network settings through Manager.</p>
      )}
      {hasActiveExecution && (
        <p className="ppuSiteNote"><strong>Execution gate:</strong> finish or cancel active Site Jobs before changing PPU network intent.</p>
      )}
      {activationBusy && (
        <p className="ppuSiteNote"><strong>Activation in progress:</strong> desired settings are frozen until the PPU activation transaction reaches a terminal state.</p>
      )}
      {commissioningActive && (
        <p className="ppuSiteNote"><strong>Manager commissioning in progress:</strong> desired settings and endpoint ownership are frozen while the transaction is non-terminal.</p>
      )}
      {network && !network.activation.supported && (
        <p className="ppuSiteNote"><strong>Commissioning unavailable:</strong> this Plasma Gateway does not currently expose a configured privileged network-activation helper. Desired-state Save remains safe and available.</p>
      )}
      <p className="ppuSiteNote">
        <strong>Commissioning boundary:</strong> Static IPv4 uses one Manager-owned transaction: persist desired state → apply on the old endpoint → reconnect to the deterministic candidate endpoint → verify the same <code>ppu_id</code> → commit → durable registry reconciliation. DHCP remains desired-state only until deterministic lease/discovery exists.
      </p>

      <div className="ppuNetworkActions">
        <button
          className="ppuSiteButton"
          type="button"
          disabled={loading || saving || commissioningBusy || !valid || !changed || !canSave}
          onClick={() => void saveDesired()}
        >
          {saving ? "Saving..." : "Save Desired Network"}
        </button>
        <button
          className="ppuSiteButton primary"
          type="button"
          disabled={loading || saving || commissioningBusy || !canCommission}
          title={network?.activation.supported ? "Run Manager-owned static IPv4 commissioning" : "PPU network activation helper is unavailable"}
          onClick={() => void commissionStatic()}
        >
          {commissioningBusy ? "Commissioning..." : "Commission Static Network"}
        </button>
      </div>
    </section>
  );
}
