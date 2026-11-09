"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DeviceSearchResult } from "../device-catalog-api";
import { ICPickerField } from "../devices/ic-picker-field";
import {
  acknowledgeProgrammingRun,
  getProgrammingRoutes,
  getProgrammingRun,
  planProgramming,
  startProgramming,
  type ProgrammingPlan,
  type ProgrammingRoute,
  type ProgrammingRun,
} from "./bundle-programming-api";

const POLL_MS = 1000;
// Catalog Level is not a programming gate (Unified Decision 2026-11-04 §1);
// the Programming Route decides whether a Site can program the IC.
const PICKER_LEVELS: Array<1 | 2 | 3> = [1, 2, 3];

function short(value: string | null | undefined): string {
  return value ? `${value.slice(0, 12)}…` : "—";
}

function outcomeLabel(run: ProgrammingRun): string {
  if (run.outcome === "PASS") return "PASS";
  if (run.outcome === "FAIL") return "FAIL";
  if (run.outcome === "BLOCKED") return "BLOCKED";
  if (run.outcome === "OUTCOME_UNKNOWN") return "OUTCOME UNKNOWN";
  return run.state.toUpperCase();
}

export default function BundleProgramming({ alias }: { alias: string }) {
  const [routes, setRoutes] = useState<ProgrammingRoute[] | null>(null);
  const [routesError, setRoutesError] = useState<string | null>(null);
  const [device, setDevice] = useState<DeviceSearchResult | null>(null);
  const [chosenSite, setChosenSite] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [planState, setPlanState] = useState<{ key: string; plan: ProgrammingPlan } | null>(null);
  const [confirmedPlanId, setConfirmedPlanId] = useState<string | null>(null);
  const [pollTick, setPollTick] = useState(0);
  const [run, setRun] = useState<ProgrammingRun | null>(null);
  const [busy, setBusy] = useState<"plan" | "start" | "ack" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startedRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getProgrammingRoutes(alias)
      .then(next => { if (!cancelled) { setRoutes(next); setRoutesError(null); } })
      .catch(reason => {
        if (!cancelled) setRoutesError(reason instanceof Error ? reason.message : "Programming Routes unavailable");
      });
    return () => { cancelled = true; };
  }, [alias]);

  const icpn = device?.icpn ?? device?.identifier ?? null;
  const siteOptions = useMemo(() => {
    if (!icpn || !routes) return [];
    return [...new Set(routes.filter(route => route.icpn === icpn).flatMap(route => route.sites))].sort((a, b) => a - b);
  }, [icpn, routes]);

  const siteId = chosenSite != null && siteOptions.includes(chosenSite) ? chosenSite : siteOptions[0] ?? null;
  // A prepared plan (and its confirmation) is valid only for the exact selection it was built from.
  const selectionKey = `${alias}|${icpn ?? ""}|${siteId ?? ""}|${file ? `${file.name}:${file.size}:${file.lastModified}` : ""}`;
  const plan = planState?.key === selectionKey ? planState.plan : null;
  const confirmed = plan != null && confirmedPlanId === plan.plan_id;

  const runActive = run != null && run.outcome == null;
  const canPrepare = Boolean(icpn && siteId != null && file && !busy && !runActive);
  const canStart = Boolean(plan && confirmed && !busy && !runActive);

  async function prepare() {
    if (!icpn || siteId == null || !file) return;
    setBusy("plan");
    setError(null);
    setRun(null);
    try {
      const image = new Uint8Array(await file.arrayBuffer());
      const next = await planProgramming(alias, { icpn, siteId, image, filename: file.name });
      setPlanState({ key: selectionKey, plan: next });
      setConfirmedPlanId(null);
    } catch (reason) {
      setPlanState(null);
      setError(reason instanceof Error ? reason.message : "Programming plan failed");
    } finally {
      setBusy(null);
    }
  }

  async function start() {
    if (!plan || !confirmed) return;
    // One plan can start at most one run, even on a double click.
    if (startedRef.current === plan.plan_id) return;
    startedRef.current = plan.plan_id;
    setBusy("start");
    setError(null);
    try {
      setRun(await startProgramming(alias, plan.plan_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Programming start failed");
    } finally {
      setPlanState(null);
      setConfirmedPlanId(null);
      setBusy(null);
    }
  }

  const poll = useCallback(async (runId: string) => {
    try {
      setRun(await getProgrammingRun(alias, runId));
      setError(null);
    } catch (reason) {
      // Reads are safe to repeat; the run itself is never resubmitted.
      setError(reason instanceof Error ? reason.message : "Programming status unavailable; the run was NOT resubmitted");
      setPollTick(tick => tick + 1);
    }
  }, [alias]);

  useEffect(() => {
    if (!run || run.outcome != null) return;
    const timer = window.setTimeout(() => { void poll(run.run_id); }, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [run, poll, pollTick]);

  async function acknowledge() {
    if (!run) return;
    setBusy("ack");
    try {
      setRun(await acknowledgeProgrammingRun(alias, run.run_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Acknowledge failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="ppuSiteCard" aria-label="Bundle Programming">
      <header className="ppuSiteCardHeader">
        <div>
          <small>PROGRAMMING</small>
          <h3>Bundle Programming</h3>
          <p>
            Select IC, image and Site. The Manager builds the Bundle, activates it only when the PPU Active Set
            differs, then submits one flash_cycle Job. No automatic retry.
          </p>
        </div>
      </header>

      {routesError && <p className="ppuRegistryMessage error" role="alert">{routesError}</p>}

      <div className="ppuRegistryAddForm">
        <label>
          <span>IC</span>
          <ICPickerField
            value={device}
            onChange={setDevice}
            levels={PICKER_LEVELS}
            disabled={Boolean(busy) || runActive}
          />
        </label>
        <label>
          <span>Image (.bin)</span>
          <input
            type="file"
            accept=".bin,application/octet-stream"
            aria-label="Image file"
            disabled={Boolean(busy) || runActive}
            onChange={event => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          <span>Site</span>
          <select
            aria-label="Programming Site"
            value={siteId ?? ""}
            disabled={!siteOptions.length || Boolean(busy) || runActive}
            onChange={event => setChosenSite(Number(event.target.value))}
          >
            {siteOptions.map(site => <option key={site} value={site}>Site {site}</option>)}
          </select>
        </label>
        {icpn && routes && !siteOptions.length && (
          <p className="ppuRegistryMessage error" role="status">
            No Programming Route declares {icpn} on PPU {alias}.
          </p>
        )}
        <button className="ppuSiteButton" type="button" disabled={!canPrepare} onClick={() => void prepare()}>
          {busy === "plan" ? "Preparing Bundle…" : "Prepare Bundle"}
        </button>
      </div>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}

      {plan && (
        <section aria-label="Programming plan" className="ppuSiteCard">
          <dl>
            <dt>PPU / Site</dt><dd>{plan.ppu_alias} / Site {plan.site_id}</dd>
            <dt>IC</dt><dd>{plan.bundle.icpn}</dd>
            <dt>Route</dt><dd>{plan.route.route_id} ({plan.route.provider} → {plan.route.profile})</dd>
            <dt>Image</dt><dd>{plan.bundle.image_filename} · {plan.bundle.image_size} B · <code>{short(plan.bundle.image_sha256)}</code></dd>
            <dt>Bundle</dt><dd data-testid="plan-bundle-sha"><code>{plan.bundle.archive_sha256}</code></dd>
            <dt>Active Set</dt><dd>{plan.active_asset_set.state} <code>{short(plan.active_asset_set.asset_set_sha256)}</code></dd>
            <dt>Activation</dt>
            <dd data-testid="plan-activation">
              {plan.activation_required ? "Required: B1 upload → B2 admit → B3 activate (no FPGA load)" : "Not required: already the Active Set"}
            </dd>
          </dl>
          <label>
            <input
              type="checkbox"
              checked={confirmed}
              onChange={event => setConfirmedPlanId(event.target.checked ? plan.plan_id : null)}
              aria-label="Confirm programming"
            />
            I confirm programming {plan.bundle.icpn} on {plan.ppu_alias} Site {plan.site_id} with this exact image.
          </label>
          <button className="ppuSiteButton primary" type="button" disabled={!canStart} onClick={() => void start()}>
            {busy === "start" ? "Starting…" : "Start Programming"}
          </button>
        </section>
      )}

      {run && (
        <section aria-label="Programming run" className="ppuSiteCard">
          <h4 data-testid="run-outcome">{outcomeLabel(run)}</h4>
          {run.reason && <p data-testid="run-reason">Reason: {run.reason}</p>}
          <ol aria-label="Programming steps">
            {run.steps.map((step, index) => <li key={`${step.step}-${index}`}>{step.step}: {step.result}</li>)}
          </ol>
          {run.job && (
            <p data-testid="run-job">
              Job {run.job.job_id ?? "—"} · {run.job.state ?? "—"}
              {run.job.progress_percent != null ? ` · ${run.job.progress_percent}%` : ""}
            </p>
          )}
          {run.receipt && (
            <dl aria-label="Programming receipt">
              <dt>Readback SHA256</dt><dd data-testid="receipt-readback"><code>{run.receipt.readback_sha256 ?? "—"}</code></dd>
              <dt>Verified Bytes</dt><dd data-testid="receipt-bytes">{run.receipt.bytes_verified ?? "—"} / {run.receipt.image_size}</dd>
              <dt>SAFE_OFF</dt><dd data-testid="receipt-safe-off">{run.receipt.safe_off === true ? "VERIFIED" : "NOT VERIFIED"}</dd>
              <dt>Job</dt><dd>{run.receipt.job_id ?? "—"}</dd>
            </dl>
          )}
          {run.outcome === "OUTCOME_UNKNOWN" && (
            <div role="alert" className="ppuRegistryMessage error">
              <p>
                The device-side outcome is unknown. Nothing was resubmitted. Reconcile the PPU Job/Bootstrap state
                (and any SEALED Site) through the normal recovery procedure before programming this PPU again.
              </p>
              {!run.acknowledged && (
                <button className="ppuSiteButton" type="button" disabled={busy === "ack"} onClick={() => void acknowledge()}>
                  Acknowledge reconciliation
                </button>
              )}
            </div>
          )}
        </section>
      )}
    </section>
  );
}
