"use client";

import { useEffect, useRef } from "react";
import "./batch-dashboard-panels.css";

export const DEFAULT_SITE_RETRY_LIMIT = "3";

export type BatchDashboardCounts = {
  selected: number;
  running: number;
  pass: number;
  faulted: number;
  error: number;
  stopped: number;
  cancelled: number;
};

type TopologySummaryProps = {
  facilityCount: number;
  ppuCount: number;
  selectedSiteCount: number;
  selectedFacilityCount: number;
  selectedPpuCount: number;
  counts: BatchDashboardCounts;
  ariaLabel?: string;
};

type PolicyCopy = {
  repeatCount: string;
  retryLimit: string;
  stopThreshold: string;
  repeatTooltip: string;
  retryTooltip: string;
  thresholdTooltip: string;
  hint: string;
  invalid: string;
};

type PolicyProps = {
  repeatCount: string;
  retryLimit: string;
  stopThreshold: string;
  maxThreshold: number;
  disabled: boolean;
  valid: boolean;
  copy: PolicyCopy;
  onRepeatCount: (value: string) => void;
  onRetryLimit: (value: string) => void;
  onStopThreshold: (value: string) => void;
};

type ActiveCopy = {
  title: string;
  hint: string;
  selected: string;
  running: string;
  pass: string;
  faulted: string;
  error: string;
  stopped: string;
  cancelled: string;
};

type ActiveProps = {
  counts: BatchDashboardCounts;
  copy: ActiveCopy;
};

function PolicyInfo({ ariaLabel, text }: { ariaLabel: string; text: string }) {
  return (
    <span className="batchPolicyInfo" tabIndex={0} aria-label={ariaLabel}>
      i
      <span role="tooltip">{text}</span>
    </span>
  );
}

export function BatchTopologySummary({
  facilityCount,
  ppuCount,
  selectedSiteCount,
  selectedFacilityCount,
  selectedPpuCount,
  counts,
  ariaLabel = "Batch topology summary",
}: TopologySummaryProps) {
  const totalIc = counts.selected;
  const failedIc = counts.faulted;
  const yieldPercent = totalIc > 0 ? (counts.pass / totalIc) * 100 : 0;

  return (
    <section className="batchTopologySummary" aria-label={ariaLabel}>
      <article className="batchTopologyContext" data-topology-context="facilities"><small>Facilities</small><b>{facilityCount}</b></article>
      <article className="batchTopologyContext" data-topology-context="ppus"><small>PPUs</small><b>{ppuCount}</b></article>
      <article className="batchTopologyContext" data-topology-context="sites"><small>Sites</small><b>{selectedSiteCount}</b><span>{selectedFacilityCount} F / {selectedPpuCount} P</span></article>
      <article className="batchTopologyKpi batchTopologyTotal" data-production-kpi="total"><small>Total IC</small><b>{totalIc}</b></article>
      <article className="batchTopologyKpi batchTopologyPass" data-production-kpi="pass"><small>PASS</small><b>{counts.pass}</b></article>
      <article className="batchTopologyKpi batchTopologyFail" data-production-kpi="fail"><small>FAIL</small><b>{failedIc}</b></article>
      <article className="batchTopologyKpi batchTopologyYield" data-production-kpi="yield"><small>Yield</small><b>{yieldPercent.toFixed(1)}%</b></article>
    </section>
  );
}

export function BatchPolicyPanel({
  repeatCount,
  retryLimit,
  stopThreshold,
  maxThreshold,
  disabled,
  valid,
  copy,
  onRepeatCount,
  onRetryLimit,
  onStopThreshold,
}: PolicyProps) {
  const retryDefaultApplied = useRef(false);

  useEffect(() => {
    if (retryDefaultApplied.current) return;
    retryDefaultApplied.current = true;
    if (retryLimit === "0") onRetryLimit(DEFAULT_SITE_RETRY_LIMIT);
  }, [onRetryLimit, retryLimit]);

  return (
    <section className="unifiedBatchPolicyPanel" aria-label="Batch execution policy">
      <label className="batchPolicyField">
        <span className="batchPolicyLabel">{copy.repeatCount}<PolicyInfo ariaLabel="Repeat policy help" text={copy.repeatTooltip} /></span>
        <input aria-label="Repeat Count" type="number" min="1" max="10000" value={repeatCount} disabled={disabled} onChange={event => onRepeatCount(event.target.value)} />
      </label>
      <label className="batchPolicyField">
        <span className="batchPolicyLabel">{copy.retryLimit}<PolicyInfo ariaLabel="Retry policy help" text={copy.retryTooltip} /></span>
        <input aria-label="Site Retry Limit" type="number" min="0" max="20" value={retryLimit} disabled={disabled} onChange={event => onRetryLimit(event.target.value)} />
      </label>
      <label className="batchPolicyField">
        <span className="batchPolicyLabel">{copy.stopThreshold}<PolicyInfo ariaLabel="Stop threshold policy help" text={copy.thresholdTooltip} /></span>
        <input aria-label="Failed Site Stop Threshold" type="number" min="1" max={Math.max(1, maxThreshold)} placeholder="off" value={stopThreshold} disabled={disabled} onChange={event => onStopThreshold(event.target.value)} />
      </label>
      <small className={`batchPolicyHint ${valid ? "" : "invalid"}`}>{valid ? copy.hint : copy.invalid}</small>
    </section>
  );
}

function batchState(counts: BatchDashboardCounts): string {
  if (counts.running > 0) return "RUNNING";
  if (counts.error > 0 || counts.stopped > 0) return "ERROR";
  if (counts.faulted > 0) return "PARTIAL";
  if (counts.selected > 0 && counts.pass === counts.selected) return "SUCCESS";
  if (counts.cancelled > 0) return "CANCELLED";
  return "READY";
}

export function ActiveFpsSummary({ counts, copy }: ActiveProps) {
  const metrics = [
    ["selected", copy.selected, counts.selected],
    ["running", copy.running, counts.running],
    ["pass", copy.pass, counts.pass],
    ["faulted", copy.faulted, counts.faulted],
    ["error", copy.error, counts.error],
    ["stopped", copy.stopped, counts.stopped],
    ["cancelled", copy.cancelled, counts.cancelled],
  ] as const;

  return (
    <section className="activeFpsSummary" aria-label={copy.title}>
      <header>
        <h2>{copy.title}</h2>
        <span>{copy.hint}</span>
        <details className="engineeringBatchDetails">
          <summary>Batch Details</summary>
          <div className="engineeringBatchDetailsGrid">
            <div><small>STATE</small><b>{batchState(counts)}</b></div>
            <div><small>SELECTED</small><b>{counts.selected}</b></div>
            <div><small>PASS</small><b>{counts.pass}</b></div>
            <div><small>FAULTED</small><b>{counts.faulted}</b></div>
            <div><small>ERROR</small><b>{counts.error}</b></div>
            <div><small>STOPPED</small><b>{counts.stopped}</b></div>
            <div><small>CANCELLED</small><b>{counts.cancelled}</b></div>
          </div>
        </details>
      </header>
      <div className="activeFpsMetrics">
        {metrics.map(([state, label, value]) => (
          <article key={state} data-active-fps-state={state}>
            <small>{label}</small><b>{value}</b>
          </article>
        ))}
      </div>
    </section>
  );
}
