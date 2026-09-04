"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getManagerPpuSites,
  saveManagerPpuSite,
  type ManagerRegistryEntry,
  type PPUSiteConfigurationPayload,
  type PPUSiteDesired,
  type PPUSiteReconciliation,
} from "./ppu-registry-api";

const SITE_INTERFACES = ["mock", "openocd", "fpga"] as const;

type Props = {
  entry: ManagerRegistryEntry;
  hasActiveExecution: boolean;
};

function reconciliationLabel(state: PPUSiteReconciliation): string {
  if (state === "in_sync") return "In sync";
  if (state === "restart_required") return "Restart required";
  if (state === "actual_unavailable") return "Actual unavailable";
  return "Disabled / binding unobservable";
}

function overallLabel(state: PPUSiteConfigurationPayload["site_configuration"]["reconciliation"]): string {
  if (state === "in_sync") return "In Sync";
  if (state === "restart_required") return "Restart Required";
  if (state === "actual_unavailable") return "Actual Unavailable";
  return "Partially Observable";
}

export default function PpuSiteDesiredConfiguration({ entry, hasActiveExecution }: Props) {
  const alias = entry.alias;
  const [payload, setPayload] = useState<PPUSiteConfigurationPayload | null>(null);
  const [drafts, setDrafts] = useState<Record<number, PPUSiteDesired>>({});
  const [dirty, setDirty] = useState<Set<number>>(new Set());
  const [savingSite, setSavingSite] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const applyPayload = useCallback((next: PPUSiteConfigurationPayload) => {
    setPayload(next);
    setDrafts(current => {
      const merged = { ...current };
      for (const site of next.site_configuration.sites) {
        if (!dirty.has(site.site_id)) merged[site.site_id] = { ...site.desired };
      }
      return merged;
    });
  }, [dirty]);

  const refresh = useCallback(async (quiet = false) => {
    if (!alias) return;
    if (!quiet) setLoading(true);
    try {
      applyPayload(await getManagerPpuSites(alias));
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Site configuration unavailable");
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [alias, applyPayload]);

  useEffect(() => {
    setPayload(null);
    setDrafts({});
    setDirty(new Set());
    setNotice(null);
    setError(null);
    if (!alias) return;
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const timer = window.setInterval(() => { void refresh(true); }, 2500);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [alias, refresh]);

  const writeBlockReason = useMemo(() => {
    if (entry.lifecycle !== "commissioned") return "Validate & Enable this PPU before changing Site desired configuration.";
    if (hasActiveExecution) return "Stop or cancel active Jobs before changing Site desired configuration.";
    return null;
  }, [entry.lifecycle, hasActiveExecution]);

  function updateDraft(siteId: number, patch: Partial<PPUSiteDesired>) {
    const baseline = drafts[siteId]
      ?? payload?.site_configuration.sites.find(site => site.site_id === siteId)?.desired;
    if (!baseline) return;
    setDrafts(current => ({ ...current, [siteId]: { ...baseline, ...patch } }));
    setDirty(current => new Set(current).add(siteId));
    setNotice(null);
  }

  function resetDraft(siteId: number) {
    const desired = payload?.site_configuration.sites.find(site => site.site_id === siteId)?.desired;
    if (!desired) return;
    setDrafts(current => ({ ...current, [siteId]: { ...desired } }));
    setDirty(current => {
      const next = new Set(current);
      next.delete(siteId);
      return next;
    });
  }

  async function saveSite(siteId: number) {
    if (!alias || writeBlockReason) return;
    const desired = drafts[siteId];
    if (!desired) return;
    setSavingSite(siteId);
    setError(null);
    setNotice(null);
    try {
      const next = await saveManagerPpuSite(alias, siteId, desired);
      setDirty(current => {
        const updated = new Set(current);
        updated.delete(siteId);
        return updated;
      });
      setPayload(next);
      setDrafts(current => {
        const updated = { ...current };
        const saved = next.site_configuration.sites.find(site => site.site_id === siteId);
        if (saved) updated[siteId] = { ...saved.desired };
        return updated;
      });
      setNotice(`SITE${siteId} desired configuration saved.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : `SITE${siteId} save failed`);
    } finally {
      setSavingSite(null);
    }
  }

  return (
    <section className="ppuSiteCard" aria-label="Site Configuration">
      <header className="ppuSiteCardHeader">
        <div>
          <h3>Site Configuration</h3>
          <p className="ppuSiteNote">PPU-owned desired state is persisted in canonical PPU configuration. Phase 1 does not restart Plasma Server automatically.</p>
        </div>
        <div className="ppuSiteCardHeaderActions">
          {payload && <span className="ppuSiteFilter">{overallLabel(payload.site_configuration.reconciliation)}</span>}
          <button className="ppuSiteButton" type="button" disabled={loading || savingSite !== null} onClick={() => void refresh()}>
            Refresh
          </button>
        </div>
      </header>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}
      {notice && <p className="ppuRegistryMessage success" role="status">{notice}</p>}
      {writeBlockReason && <p className="ppuRegistryMessage warning" role="status">{writeBlockReason}</p>}

      {payload?.site_configuration.sites.length ? (
        <div className="ppuTableWrap">
          <table className="ppuTable">
            <thead>
              <tr>
                <th>Site</th>
                <th>Desired Enabled</th>
                <th>Desired Interface</th>
                <th>Desired Target</th>
                <th>Actual</th>
                <th>Reconciliation</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {payload.site_configuration.sites.map(site => {
                const draft = drafts[site.site_id] ?? site.desired;
                const isDirty = dirty.has(site.site_id);
                const disabled = Boolean(writeBlockReason) || savingSite !== null;
                return (
                  <tr key={`${alias}-desired-site-${site.site_id}`}>
                    <td><span className="ppuIdLink">SITE{site.site_id}</span></td>
                    <td>
                      <input
                        className="ppuSiteToggle"
                        type="checkbox"
                        checked={draft.enabled}
                        disabled={disabled}
                        aria-label={`SITE${site.site_id} desired enabled`}
                        onChange={event => updateDraft(site.site_id, { enabled: event.target.checked })}
                      />
                    </td>
                    <td>
                      <select
                        value={draft.interface}
                        disabled={disabled}
                        aria-label={`SITE${site.site_id} desired interface`}
                        onChange={event => updateDraft(site.site_id, { interface: event.target.value })}
                      >
                        {SITE_INTERFACES.map(value => <option value={value} key={value}>{value}</option>)}
                      </select>
                    </td>
                    <td>
                      <input
                        value={draft.target}
                        disabled={disabled}
                        maxLength={256}
                        aria-label={`SITE${site.site_id} desired target`}
                        onChange={event => updateDraft(site.site_id, { target: event.target.value })}
                      />
                    </td>
                    <td>
                      {site.actual
                        ? `${site.actual.enabled ? "Enabled" : "Disabled"} · ${site.actual.interface ?? "—"} · ${site.actual.target ?? "—"}`
                        : "Unavailable"}
                    </td>
                    <td>{reconciliationLabel(site.reconciliation)}</td>
                    <td>
                      <div className="ppuSiteCardHeaderActions">
                        <button
                          className="ppuSiteButton primary"
                          type="button"
                          disabled={disabled || !isDirty || !draft.target.trim()}
                          onClick={() => void saveSite(site.site_id)}
                        >
                          {savingSite === site.site_id ? "Saving..." : "Save"}
                        </button>
                        <button className="ppuSiteButton" type="button" disabled={disabled || !isDirty} onClick={() => resetDraft(site.site_id)}>
                          Reset
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="ppuSiteNote">{loading ? "Loading PPU-owned Site desired configuration..." : "Site desired configuration is unavailable."}</p>
      )}

      <p className="ppuSiteNote">
        <strong>Reconciliation:</strong> when desired and running state differ, the API reports <code>restart_required</code>. Protocol v3.3 does not expose dormant interface/target bindings for disabled Sites, so those rows are explicitly marked partially observable instead of guessed.
      </p>
    </section>
  );
}
