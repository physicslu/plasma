"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getManagerPpuNetwork,
  saveManagerPpuNetwork,
  type ManagerRegistryEntry,
  type PPUNetworkPayload,
  type PPUNetworkMode,
} from "./ppu-registry-api";
import "./ppu-network-configuration.css";

type Props = {
  entry: ManagerRegistryEntry;
  hasActiveExecution: boolean;
};

function dnsText(values: string[]): string {
  return values.join(", ");
}

function parseDns(value: string): string[] {
  return value
    .split(",")
    .map(item => item.trim())
    .filter(Boolean);
}

export default function PpuNetworkConfiguration({ entry, hasActiveExecution }: Props) {
  const [network, setNetwork] = useState<PPUNetworkPayload | null>(null);
  const [loadedAlias, setLoadedAlias] = useState<string | null>(null);
  const [mode, setMode] = useState<PPUNetworkMode>("dhcp");
  const [address, setAddress] = useState("");
  const [prefixLength, setPrefixLength] = useState("24");
  const [gateway, setGateway] = useState("");
  const [dnsServers, setDnsServers] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!entry.alias) return;
    let cancelled = false;
    void getManagerPpuNetwork(entry.alias)
      .then(payload => {
        if (cancelled) return;
        const settings = payload.ppu_network_settings;
        setNetwork(payload);
        setMode(settings.mode);
        setAddress(settings.address ?? "");
        setPrefixLength(settings.prefix_length == null ? "24" : String(settings.prefix_length));
        setGateway(settings.gateway ?? "");
        setDnsServers(dnsText(settings.dns_servers));
        setError(null);
        setSaved(false);
        setLoadedAlias(entry.alias);
      })
      .catch(loadError => {
        if (!cancelled) {
          setNetwork(null);
          setError(loadError instanceof Error ? loadError.message : "PPU network settings unavailable");
          setSaved(false);
          setLoadedAlias(entry.alias);
        }
      });
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
  const lifecycleWritable = entry.lifecycle === "commissioned";
  const canSave = lifecycleWritable && !hasActiveExecution && !activationBusy;

  async function saveDesired() {
    if (!entry.alias || !valid || !changed || !canSave || saving) return;
    setSaving(true);
    setSaved(false);
    try {
      const payload = await saveManagerPpuNetwork(entry.alias, desired);
      const settings = payload.ppu_network_settings;
      setNetwork(payload);
      setMode(settings.mode);
      setAddress(settings.address ?? "");
      setPrefixLength(settings.prefix_length == null ? "24" : String(settings.prefix_length));
      setGateway(settings.gateway ?? "");
      setDnsServers(dnsText(settings.dns_servers));
      setError(null);
      setSaved(true);
      setLoadedAlias(entry.alias);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "PPU network settings update failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="ppuSiteCard ppuNetworkConfiguration" aria-label="PPU Network Configuration">
      <header className="ppuSiteCardHeader">
        <div>
          <h3>PPU Network Configuration</h3>
          <p className="ppuNetworkSubtitle">PPU-owned desired <code>eth0</code> configuration. Saving here does not change the running Linux network.</p>
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
      </div>

      <div className="ppuNetworkGrid">
        <label>
          <span>Mode</span>
          <select
            aria-label="PPU network mode"
            value={mode}
            disabled={loading || saving || !canSave}
            onChange={event => { setSaved(false); setMode(event.target.value as PPUNetworkMode); }}
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
                disabled={loading || saving || !canSave}
                onChange={event => { setSaved(false); setAddress(event.target.value); }}
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
                disabled={loading || saving || !canSave}
                onChange={event => { setSaved(false); setPrefixLength(event.target.value); }}
              />
            </label>
            <label>
              <span>Gateway</span>
              <input
                aria-label="PPU static gateway"
                value={gateway}
                placeholder="192.168.10.1"
                disabled={loading || saving || !canSave}
                onChange={event => { setSaved(false); setGateway(event.target.value); }}
              />
            </label>
            <label className="wide">
              <span>DNS Servers</span>
              <input
                aria-label="PPU DNS servers"
                value={dnsServers}
                placeholder="192.168.10.1, 8.8.8.8"
                disabled={loading || saving || !canSave}
                onChange={event => { setSaved(false); setDnsServers(event.target.value); }}
              />
            </label>
          </>
        )}
      </div>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}
      {saved && !loading && <p className="ppuRegistryMessage success" role="status">Desired PPU network settings saved. Running <code>eth0</code> was not activated by this action.</p>}

      {!lifecycleWritable && (
        <p className="ppuSiteNote"><strong>Write gate:</strong> complete Validate &amp; Enable before changing PPU desired network settings through Manager.</p>
      )}
      {hasActiveExecution && (
        <p className="ppuSiteNote"><strong>Execution gate:</strong> finish or cancel active Site Jobs before changing PPU network intent.</p>
      )}
      {activationBusy && (
        <p className="ppuSiteNote"><strong>Activation in progress:</strong> desired settings are frozen until the PPU activation transaction reaches a terminal state.</p>
      )}
      <p className="ppuSiteNote">
        <strong>Current activation boundary:</strong> this screen persists validated desired settings only. Safe endpoint migration still requires Manager-orchestrated apply → reconnect → same <code>ppu_id</code> verification → commit/rollback; the Browser does not call the activation API directly.
      </p>

      <div className="ppuNetworkActions">
        <button
          className="ppuSiteButton primary"
          type="button"
          disabled={loading || saving || !valid || !changed || !canSave}
          onClick={() => void saveDesired()}
        >
          {saving ? "Saving..." : "Save Desired Network"}
        </button>
      </div>
    </section>
  );
}
