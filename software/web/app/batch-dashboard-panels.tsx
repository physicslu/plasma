"use client";

import "./batch-dashboard-panels.css";

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
  return (
    <section className="batchTopologySummary" aria-label={ariaLabel}>
      <article><small>Facilities</small><b>{facilityCount}</b></article>
      <article><small>PPUs</small><b>{ppuCount}</b></article>
      <article><small>Sites</small><b>{selectedSiteCount}</b><span>{selectedFacilityCount} F / {selectedPpuCount} P</span></article>
      <article className="batchTopologyPass"><small>PASS</small><b>{counts.pass}</b><span>FAULT {counts.faulted} · ERR {counts.error} · RUN {counts.running} · STOP {counts.stopped} · CAN {counts.cancelled}</span></article>
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
      <header><h2>{copy.title}</h2><span>{copy.hint}</span></header>
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
