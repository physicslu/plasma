"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getManagerPpuSites,
  ManagerApiError,
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

function reconciliationTone(state: PPUSiteReconciliation): "healthy" | "warning" | "muted" {
  if (state === "in_sync") return "healthy";
  if (state === "restart_required") return "warning";
  return "muted";
}

function overallLabel(state: PPUSiteConfigurationPayload["site_configuration"]["reconciliation"]): string {
  if (state === "in_sync") return "In Sync";
  if (state === "restart_required") return "Restart Required";
  if (state === "actual_unavailable") return "Actual Unavailable";
  return "Partially Observable";
}

function overallTone(state: PPUSiteConfigurationPayload["site_configuration"]["reconciliation"]): "healthy" | "warning" | "muted" {
  if (state === "in_sync") return "healthy";
  if (state === "restart_required") return "warning";
  return "muted";
}

function sameDesired(left: PPUSiteDesired, right: PPUSiteDesired): boolean {
  return left.enabled === right.enabled
    && left.interface === right.interface
    && left.target === right.target;
}

export default function PpuSiteDesiredConfiguration({ entry, hasActiveExecution }: Props) {
  const alias = entry.alias;
  const [payload, setPayload] = useState<PPUSiteConfigurationPayload | null>(null);
  const [drafts, setDrafts] = useState<Record<number, PPUSiteDesired>>({});
  const [baselineRevisions, setBaselineRevisions] = useState<Record<number, string>>({});
  const [dirty, setDirty] = useState<Set<number>>(new Set());
  const dirtyRef = useRef<Set<number>>(new Set());
  const [conflicts, setConflicts] = useState<Set<number>>(new Set());
  const [savingSite, setSavingSite] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const replaceDirty = useCallback((next: Set<number>) => {
    dirtyRef.current = next;
    setDirty(next);
  }, []);

  const clearConflict = useCallback((siteId: number) => {
    setConflicts(current => {
      if (!current.has(siteId)) return current;
      const next = new Set(current);
      next.delete(siteId);
      return next;
    });
  }, []);

  const applyPayload = useCallback((next: PPUSiteConfigurationPayload) => {
    setPayload(next);
    setDrafts(current => {
      const merged = { ...current };
      for (const site of next.site_configuration.sites) {
        if (!dirtyRef.current.has(site.site_id)) merged[site.site_id] = { ...site.desired };
      }
      return merged;
    });
    setBaselineRevisions(current => {
      const merged = { ...current };
      for (const site of next.site_configuration.sites) {
        if (!dirtyRef.current.has(site.site_id)) merged[site.site_id] = site.desired_revision;
      }
      return merged;
    });
  }, []);

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
    const initial = window.setTimeout(() => {
      setPayload(null);
      setDrafts({});
      setBaselineRevisions({});
      replaceDirty(new Set());
      setConflicts(new Set());
      setNotice(null);
      setError(null);
      if (alias) void refresh();
    }, 0);
    const timer = alias ? window.setInterval(() => { void refresh(true); }, 2500) : null;
    return () => {
      window.clearTimeout(initial);
      if (timer !== null) window.clearInterval(timer);
    };
  }, [alias, refresh, replaceDirty]);

  const writeBlockReason = useMemo(() => {
    if (entry.lifecycle !== "commissioned") return "Validate & Enable this PPU before changing Site desired configuration.";
    if (hasActiveExecution) return "Stop or cancel active Jobs before changing Site desired configuration.";
    return null;
  }, [entry.lifecycle, hasActiveExecution]);

  const observedRuntimeSites = useMemo(
    () => payload?.site_configuration.sites.filter(site => site.actual !== null).length ?? 0,
    [payload],
  );

  function markDirty(siteId: number) {
    const next = new Set(dirtyRef.current);
    next.add(siteId);
    replaceDirty(next);
  }

  function clearDirty(siteId: number) {
    const next = new Set(dirtyRef.current);
    next.delete(siteId);
    replaceDirty(next);
  }

  function updateDraft(siteId: number, patch: Partial<PPUSiteDesired>) {
    const persistedSite = payload?.site_configuration.sites.find(site => site.site_id === siteId);
    const persisted = persistedSite?.desired;
    const baseline = drafts[siteId] ?? persisted;
    if (!baseline) return;
    const nextDraft = { ...baseline, ...patch };
    setDrafts(current => ({ ...current, [siteId]: nextDraft }));
    if (persisted && persistedSite && sameDesired(nextDraft, persisted)) {
      clearDirty(siteId);
      clearConflict(siteId);
      setBaselineRevisions(current => ({ ...current, [siteId]: persistedSite.desired_revision }));
    } else {
      if (!dirtyRef.current.has(siteId) && persistedSite) {
        setBaselineRevisions(current => ({ ...current, [siteId]: persistedSite.desired_revision }));
      }
      markDirty(siteId);
    }
    setNotice(null);
  }

  function resetDraft(siteId: number) {
    const site = payload?.site_configuration.sites.find(item => item.site_id === siteId);
    if (!site) return;
    setDrafts(current => ({ ...current, [siteId]: { ...site.desired } }));
    setBaselineRevisions(current => ({ ...current, [siteId]: site.desired_revision }));
    clearDirty(siteId);
    clearConflict(siteId);
    setNotice(`SITE${siteId} Draft reset to the latest saved Desired configuration.`);
  }

  async function saveSite(siteId: number) {
    if (!alias || writeBlockReason || conflicts.has(siteId)) return;
    const desired = drafts[siteId];
    const persistedSite = payload?.site_configuration.sites.find(site => site.site_id === siteId);
    const expectedRevision = baselineRevisions[siteId] ?? persistedSite?.desired_revision;
    if (!desired || !expectedRevision) return;
    setSavingSite(siteId);
    setError(null);
    setNotice(null);
    try {
      const next = await saveManagerPpuSite(alias, siteId, desired, expectedRevision);
      clearDirty(siteId);
      clearConflict(siteId);
      setPayload(next);
      setDrafts(current => {
        const updated = { ...current };
        const saved = next.site_configuration.sites.find(site => site.site_id === siteId);
        if (saved) updated[siteId] = { ...saved.desired };
        return updated;
      });
      const saved = next.site_configuration.sites.find(site => site.site_id === siteId);
      if (saved) {
        setBaselineRevisions(current => ({ ...current, [siteId]: saved.desired_revision }));
      }
      const reconciliation = saved ? reconciliationLabel(saved.reconciliation) : overallLabel(next.site_configuration.reconciliation);
      setNotice(`SITE${siteId} desired configuration saved. Runtime reconciliation: ${reconciliation}.`);
    } catch (requestError) {
      if (
        requestError instanceof ManagerApiError
        && requestError.status === 412
        && requestError.code === "site_desired_conflict"
      ) {
        setConflicts(current => new Set(current).add(siteId));
        setError(`SITE${siteId} Desired changed elsewhere after this Draft was created. Reset Draft to the latest Desired state, then reapply and confirm the intended change.`);
        void refresh(true);
      } else {
        setError(requestError instanceof Error ? requestError.message : `SITE${siteId} save failed`);
      }
    } finally {
      setSavingSite(null);
    }
  }

  return (
    <section className="ppuSiteCard" aria-label="Programming Site Configuration">
      <header className="ppuSiteCardHeader">
        <div>
          <h3>Programming Site Configuration</h3>
          <p className="ppuSiteHeaderNote">Site is the canonical independently controlled programming position inside a PPU. Topology is discovered from the PPU; this UI does not hard-code an eight-Site assumption.</p>
        </div>
        <div className="ppuSiteCardHeaderActions">
          {payload && (
            <span className="ppuReconciliationBadge" data-tone={overallTone(payload.site_configuration.reconciliation)}>
              {overallLabel(payload.site_configuration.reconciliation)}
            </span>
          )}
          <button className="ppuSiteButton" type="button" disabled={loading || savingSite !== null} onClick={() => void refresh()}>
            Refresh
          </button>
        </div>
      </header>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}
      {notice && <p className="ppuRegistryMessage success" role="status">{notice}</p>}
      {writeBlockReason && <p className="ppuRegistryMessage warning" role="status">{writeBlockReason}</p>}

      {payload && (
        <div className="ppuConfigurationStateFlow" aria-label="Draft Desired Runtime configuration state">
          <article className="ppuConfigurationStateStep" data-tone={conflicts.size > 0 ? "danger" : dirty.size > 0 ? "warning" : "healthy"}>
            <small>Draft</small>
            <strong>{conflicts.size > 0 ? "Conflict" : dirty.size > 0 ? "Modified" : "Clean"}</strong>
            <span>{conflicts.size > 0 ? `${conflicts.size} stale Site draft${conflicts.size === 1 ? "" : "s"} blocked from overwriting newer Desired state` : dirty.size > 0 ? `${dirty.size} Site draft${dirty.size === 1 ? "" : "s"} not saved` : "Browser edits match saved Desired state"}</span>
          </article>
          <span className="ppuConfigurationStateArrow" aria-hidden="true">→</span>
          <article className="ppuConfigurationStateStep" data-tone="info">
            <small>Desired</small>
            <strong>Saved</strong>
            <span>{payload.site_configuration.sites.length} canonical Site record{payload.site_configuration.sites.length === 1 ? "" : "s"} persisted on the PPU</span>
          </article>
          <span className="ppuConfigurationStateArrow" aria-hidden="true">→</span>
          <article className="ppuConfigurationStateStep" data-tone={overallTone(payload.site_configuration.reconciliation)}>
            <small>Runtime</small>
            <strong>{overallLabel(payload.site_configuration.reconciliation)}</strong>
            <span>{observedRuntimeSites} of {payload.site_configuration.sites.length} Site runtime state{payload.site_configuration.sites.length === 1 ? "" : "s"} currently observable</span>
          </article>
        </div>
      )}

      {dirty.size > 0 && (
        <p className="ppuDraftWarning" role="status">
          <strong>{dirty.size} unsaved Draft change{dirty.size === 1 ? "" : "s"}.</strong>
          Saving updates Desired configuration only; Runtime remains separately reconciled.
        </p>
      )}

      {conflicts.size > 0 && (
        <p className="ppuRegistryMessage error" role="alert">
          <strong>Desired changed elsewhere.</strong> Stale Drafts are fail-closed and cannot overwrite the newer saved state. Reset the affected Draft to the latest Desired state before reapplying the intended change.
        </p>
      )}

      {payload?.site_configuration.sites.length ? (
        <div className="ppuTableWrap">
          <table className="ppuTable">
            <thead>
              <tr>
                <th>Site</th>
                <th>Desired Enabled</th>
                <th>Desired Interface</th>
                <th>Desired Target</th>
                <th>Runtime</th>
                <th>Reconciliation</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {payload.site_configuration.sites.map(site => {
                const draft = drafts[site.site_id] ?? site.desired;
                const isDirty = dirty.has(site.site_id);
                const isConflict = conflicts.has(site.site_id);
                const disabled = Boolean(writeBlockReason) || savingSite !== null;
                return (
                  <tr key={`${alias}-desired-site-${site.site_id}`} className={isDirty ? "ppuSiteDirtyRow" : ""}>
                    <td>
                      <span className="ppuIdLink">SITE{site.site_id}</span>
                      {isDirty && <span className="ppuDirtyBadge">Unsaved Draft</span>}
                      {isConflict && <span className="ppuReconciliationBadge" data-tone="danger">Desired changed elsewhere</span>}
                    </td>
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
                    <td>
                      <span className="ppuReconciliationBadge" data-tone={reconciliationTone(site.reconciliation)}>
                        {reconciliationLabel(site.reconciliation)}
                      </span>
                    </td>
                    <td>
                      <div className="ppuSiteCardHeaderActions">
                        <button
                          className="ppuSiteButton primary"
                          type="button"
                          disabled={disabled || !isDirty || !draft.target.trim() || isConflict}
                          title={isConflict ? "Reset Draft to the latest Desired state before saving" : undefined}
                          onClick={() => void saveSite(site.site_id)}
                        >
                          {savingSite === site.site_id ? "Saving..." : "Save Desired"}
                        </button>
                        <button className="ppuSiteButton" type="button" disabled={disabled || !isDirty} onClick={() => resetDraft(site.site_id)}>
                          Reset Draft
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
        <strong>Configuration boundary:</strong> Draft is browser-local, Desired is persisted in canonical PPU configuration, and Runtime is observed separately. Each Draft keeps the exact <code>desired_revision</code> it was based on and Save Desired sends it with <code>If-Match</code>; a stale Draft receives HTTP 412 and is blocked from silently overwriting newer Desired state. When Desired and Runtime differ, the API reports <code>restart_required</code>. Phase 1 reports <code>runtime_apply_supported=false</code>, so this page does not pretend a save has already changed the running service. Protocol v3.3 also does not expose dormant interface/target bindings for disabled Sites; those rows remain explicitly partially observable instead of guessed.
      </p>
    </section>
  );
}
