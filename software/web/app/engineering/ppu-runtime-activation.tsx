"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  OperatorActions,
  OperatorButton,
  OperatorCard,
  OperatorMessage,
} from "../operator-ui/operator-surface";
import {
  activateManagerPpuSiteDesired,
  getManagerPpuSites,
  type ManagerRegistryEntry,
  type PPUSiteConfigurationPayload,
} from "./ppu-registry-api";

type Props = {
  entry: ManagerRegistryEntry;
  hasActiveExecution: boolean;
};

type P3Configuration = PPUSiteConfigurationPayload["site_configuration"] & {
  desired_runtime_revision?: string;
  runtime_ppu_id?: string | null;
};

export default function PpuRuntimeActivation({ entry, hasActiveExecution }: Props) {
  const alias = entry.alias;
  const [payload, setPayload] = useState<PPUSiteConfigurationPayload | null>(null);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!alias) return;
    try {
      setPayload(await getManagerPpuSites(alias));
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Runtime activation state unavailable");
    }
  }, [alias]);

  useEffect(() => {
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const timer = alias ? window.setInterval(() => { void refresh(); }, 2500) : null;
    return () => {
      window.clearTimeout(initial);
      if (timer !== null) window.clearInterval(timer);
    };
  }, [alias, refresh]);

  const configuration = payload?.site_configuration as P3Configuration | undefined;
  const desiredRuntimeRevision = configuration?.desired_runtime_revision ?? null;
  const runtimePpuId = configuration?.runtime_ppu_id ?? null;
  const reconciliation = configuration?.reconciliation ?? "actual_unavailable";

  const blockReason = useMemo(() => {
    if (entry.lifecycle !== "commissioned") return "Validate & Enable this PPU before runtime activation.";
    if (hasActiveExecution) return "Runtime activation is blocked while any Site execution is active.";
    if (!configuration) return "Runtime activation state is unavailable.";
    if (!configuration.runtime_apply_supported) return "This PPU deployment does not expose the bounded runtime-activation helper.";
    if (!desiredRuntimeRevision || !/^sha256:[0-9a-f]{64}$/.test(desiredRuntimeRevision)) return "Desired runtime revision is unavailable.";
    if (!runtimePpuId) return "Running PPU identity is unavailable; activation cannot safely verify identity.";
    if (reconciliation === "actual_unavailable") return "Runtime state is unavailable; activation cannot safely proceed.";
    if (reconciliation === "in_sync") return "Runtime already matches saved Desired configuration.";
    if (reconciliation === "partially_observable") return "Runtime effective disabled state is known, but dormant bindings are not observable in Protocol v3.3.";
    return null;
  }, [configuration, desiredRuntimeRevision, entry.lifecycle, hasActiveExecution, reconciliation, runtimePpuId]);

  async function activate() {
    if (!alias || !desiredRuntimeRevision || !runtimePpuId || blockReason || activating) return;
    setActivating(true);
    setError(null);
    setNotice(null);
    try {
      const result = await activateManagerPpuSiteDesired(alias, desiredRuntimeRevision, runtimePpuId);
      const state = result.runtime_activation.state;
      setNotice(
        state === "in_sync"
          ? "Runtime activation completed. Saved Desired configuration is now in sync with the running Plasma Server."
          : "Runtime activation completed, but disabled Site dormant bindings remain partially observable under Protocol v3.3.",
      );
      await refresh();
    } catch (activationError) {
      setError(activationError instanceof Error ? activationError.message : "Runtime activation failed");
      await refresh();
    } finally {
      setActivating(false);
    }
  }

  return (
    <OperatorCard className="ppuSiteCard" ariaLabel="Site Desired Runtime Activation">
      <header className="ppuSiteCardHeader">
        <div>
          <h3>Runtime Activation</h3>
          <p className="ppuSiteHeaderNote">
            Activation is PPU-level. It quiesces new Job admission, restarts only the Plasma Server, reloads the canonical Site Desired configuration, then verifies the same PPU identity and Runtime reconciliation.
          </p>
        </div>
        <span className="ppuReconciliationBadge" data-tone={reconciliation === "in_sync" ? "healthy" : reconciliation === "restart_required" ? "warning" : "muted"}>
          {reconciliation === "in_sync" ? "Runtime In Sync" : reconciliation === "restart_required" ? "Activation Required" : reconciliation === "partially_observable" ? "Partially Observable" : "Runtime Unavailable"}
        </span>
      </header>

      <OperatorMessage className="ppuRegistryMessage warning" tone="warning" role="status">
        <strong>All-Site impact:</strong> activating saved Desired configuration restarts the PPU programming server. It never applies unsaved Browser Drafts, and it is rejected if execution is active or the saved Desired revision changes before activation.
      </OperatorMessage>
      {error && <OperatorMessage className="ppuRegistryMessage error" tone="error" role="alert">{error}</OperatorMessage>}
      {notice && <OperatorMessage className="ppuRegistryMessage success" tone="success" role="status">{notice}</OperatorMessage>}

      <div className="ppuConfigurationStateFlow" aria-label="Desired runtime activation flow">
        <article className="ppuConfigurationStateStep" data-tone="info">
          <small>Desired Revision</small>
          <strong>{desiredRuntimeRevision ? desiredRuntimeRevision.slice(0, 18) + "…" : "Unavailable"}</strong>
          <span>Aggregate revision is derived from all canonical per-Site Desired revisions.</span>
        </article>
        <span className="ppuConfigurationStateArrow" aria-hidden="true">→</span>
        <article className="ppuConfigurationStateStep" data-tone={hasActiveExecution ? "danger" : "healthy"}>
          <small>Execution Gate</small>
          <strong>{hasActiveExecution ? "Busy" : "Quiesce on activation"}</strong>
          <span>Server-authoritative admission gate closes the idle-check → restart race.</span>
        </article>
        <span className="ppuConfigurationStateArrow" aria-hidden="true">→</span>
        <article className="ppuConfigurationStateStep" data-tone={reconciliation === "in_sync" ? "healthy" : "warning"}>
          <small>Runtime</small>
          <strong>{reconciliation === "in_sync" ? "In Sync" : "Reconcile after restart"}</strong>
          <span>Identity and Desired revision are revalidated after Plasma Server restart.</span>
        </article>
      </div>

      <OperatorActions className="ppuSiteCardHeaderActions">
        <OperatorButton
          className="ppuSiteButton primary"
          variant="primary"
          type="button"
          disabled={Boolean(blockReason) || activating}
          title={blockReason ?? "Apply saved Site Desired configuration by controlled Plasma Server restart"}
          onClick={() => void activate()}
        >
          {activating ? "Activating…" : "Activate Desired Configuration"}
        </OperatorButton>
        <OperatorButton className="ppuSiteButton" type="button" disabled={activating} onClick={() => void refresh()}>
          Refresh Runtime State
        </OperatorButton>
      </OperatorActions>
      {blockReason && <p className="ppuSiteNote"><strong>Activation status:</strong> {blockReason}</p>}
    </OperatorCard>
  );
}
