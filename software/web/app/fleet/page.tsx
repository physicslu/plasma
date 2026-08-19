"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n";
import type { FleetJobSummary, FleetPPUView, FleetSiteView, FleetWebPayload } from "./fleet-contract";
import "./fleet.css";

type LoadState = "loading" | "ready" | "disabled" | "error";
type VisualStatus = "ready" | "running" | "pass" | "fail" | "error" | "disabled" | "offline";
type LogSeverity = "INFO" | "WARN" | "ERROR";
type LogFilter = "all" | "errors" | string;
type FactoryLogEntry = {
  id: number;
  timestamp: string;
  ppu: string;
  site: string | null;
  severity: LogSeverity;
  operation: string;
  eventCode: "fleetConnected" | "ppuChanged" | "siteChanged" | "jobObserved" | "siteResultCleared";
  detail: string;
};

const operations = [
  { code: "E", labelKey: "operation.erase" },
  { code: "P", labelKey: "operation.program" },
  { code: "V", labelKey: "operation.verify" },
  { code: "R", labelKey: "operation.read" },
] as const;

const terminalStates = new Set(["success", "failed", "cancelled", "timeout", "aborted"]);
const failedStates = new Set(["failed", "timeout", "aborted"]);

function ppuKey(ppu: FleetPPUView): string {
  return ppu.identity.ppu_id ?? ppu.alias ?? "unknown-ppu";
}

function displayName(ppu: FleetPPUView): string {
  return ppu.identity.display_name ?? ppu.identity.ppu_id ?? ppu.alias ?? "Unknown PPU";
}

function siteKey(ppu: FleetPPUView, site: FleetSiteView): string {
  return `${ppuKey(ppu)}:${site.site_id}`;
}

function ppuOperational(ppu: FleetPPUView): boolean {
  return ppu.transport_state === "reachable" && ppu.observation.state === "current";
}

function jobSignature(job: FleetJobSummary | null): string | null {
  if (!job || !terminalStates.has(job.state)) return null;
  return `${job.job_id}:${job.state}:${job.updated_at ?? ""}`;
}

function operationCode(site: FleetSiteView): string {
  switch (site.latest_job?.operation) {
    case "erase": return "E";
    case "program": return "P";
    case "verify": return "V";
    case "read": return "R";
    default: return "—";
  }
}

function siteStatus(ppu: FleetPPUView, site: FleetSiteView, clearedSignature?: string): VisualStatus {
  if (!site.enabled) return "disabled";
  if (!ppuOperational(ppu)) return "offline";

  const job = site.latest_job;
  if (job) {
    if (job.state === "queued" || job.state === "running") return "running";
    const signature = jobSignature(job);
    const cleared = signature !== null && signature === clearedSignature;
    if (!cleared && job.state === "success") return "pass";
    if (!cleared && failedStates.has(job.state)) return "fail";
  }

  if (site.state === "queued" || site.state === "running") return "running";
  if (site.state === "error") return "error";
  return "ready";
}

function resultLabel(site: FleetSiteView, clearedSignature?: string): string {
  const job = site.latest_job;
  const signature = jobSignature(job);
  if (!job || !signature || signature === clearedSignature) return "NONE";
  return job.state.toUpperCase();
}

function severityForJob(job: FleetJobSummary): LogSeverity {
  if (failedStates.has(job.state)) return "ERROR";
  if (job.state === "cancelled") return "WARN";
  return "INFO";
}

function severityForSite(status: VisualStatus, ppu?: FleetPPUView): LogSeverity {
  if (status === "fail" || status === "error" || status === "offline") return "ERROR";
  if (ppu?.observation.state === "stale") return "WARN";
  return "INFO";
}

function nowTime(): string {
  return new Date().toLocaleTimeString([], { hour12: false });
}

function observedTime(job: FleetJobSummary | null): string {
  const raw = job?.updated_at;
  if (!raw) return nowTime();
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? nowTime() : parsed.toLocaleTimeString([], { hour12: false });
}

export default function FleetPage() {
  const { t } = useI18n();
  const [payload, setPayload] = useState<FleetWebPayload | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [message, setMessage] = useState("Loading fleet snapshot…");
  const [selectedSites, setSelectedSites] = useState<Set<string>>(new Set());
  const [selectedOperations, setSelectedOperations] = useState<Set<string>>(new Set());
  const [clearedResults, setClearedResults] = useState<Map<string, string>>(new Map());
  const [selectedDetail, setSelectedDetail] = useState<{ ppu: string; siteId: number } | null>(null);
  const [logs, setLogs] = useState<FactoryLogEntry[]>([]);
  const [logFilter, setLogFilter] = useState<LogFilter>("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const [fullLog, setFullLog] = useState(false);
  const previousSnapshot = useRef<Map<string, string>>(new Map());
  const logSequence = useRef(0);
  const logBodyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    function processObservation(next: FleetWebPayload) {
      const nextSnapshot = new Map<string, string>();
      const entries: Omit<FactoryLogEntry, "id">[] = [];
      const firstObservation = previousSnapshot.current.size === 0;

      if (firstObservation) {
        entries.push({
          timestamp: nowTime(), ppu: "FLEET", site: null, severity: "INFO", operation: "—",
          eventCode: "fleetConnected", detail: `${next.summary.configured_ppus} PPU / ${next.summary.reported_sites} Sites`,
        });
      }

      for (const ppu of next.ppus) {
        const id = ppuKey(ppu);
        const ppuValue = `${ppu.transport_state}/${ppu.execution_state}/${ppu.observation.state}`;
        nextSnapshot.set(`ppu:${id}`, ppuValue);
        const previousPpu = previousSnapshot.current.get(`ppu:${id}`);
        if (previousPpu && previousPpu !== ppuValue) {
          entries.push({ timestamp: nowTime(), ppu: id, site: null, severity: ppuOperational(ppu) ? "INFO" : ppu.observation.state === "stale" ? "WARN" : "ERROR", operation: "—", eventCode: "ppuChanged", detail: `${previousPpu} → ${ppuValue}` });
        }

        for (const site of ppu.topology.sites) {
          const key = siteKey(ppu, site);
          const siteValue = `${site.state}/${site.current_job_id ?? "none"}`;
          nextSnapshot.set(`site:${key}`, siteValue);
          const previousSite = previousSnapshot.current.get(`site:${key}`);
          if (previousSite && previousSite !== siteValue) {
            entries.push({ timestamp: nowTime(), ppu: id, site: `SITE ${site.site_id}`, severity: severityForSite(siteStatus(ppu, site), ppu), operation: operationCode(site), eventCode: "siteChanged", detail: `${previousSite} → ${siteValue}` });
          }

          const job = site.latest_job;
          if (job) {
            const jobValue = [job.job_id, job.operation, job.state, job.stage ?? "", job.stage_state ?? "", Math.round(job.progress_percent), job.updated_at ?? ""].join("/");
            nextSnapshot.set(`job:${key}`, jobValue);
            const previousJob = previousSnapshot.current.get(`job:${key}`);
            if ((firstObservation || previousJob) && previousJob !== jobValue) {
              const stage = job.stage ? ` stage=${job.stage}` : "";
              entries.push({ timestamp: observedTime(job), ppu: id, site: `SITE ${site.site_id}`, severity: severityForJob(job), operation: operationCode(site), eventCode: "jobObserved", detail: `${job.job_id} ${job.state.toUpperCase()} ${Math.round(job.progress_percent)}%${stage}` });
            }
          }
        }
      }

      previousSnapshot.current = nextSnapshot;
      if (entries.length > 0) setLogs(current => [...current, ...entries.map(entry => ({ ...entry, id: ++logSequence.current }))].slice(-500));

      const allowed = new Set<string>();
      for (const ppu of next.ppus) {
        if (!ppuOperational(ppu)) continue;
        for (const site of ppu.topology.sites) if (site.enabled) allowed.add(siteKey(ppu, site));
      }
      setSelectedSites(current => {
        const filtered = new Set([...current].filter(key => allowed.has(key)));
        return filtered.size === current.size ? current : filtered;
      });
    }

    async function poll() {
      try {
        const response = await fetch("/api/fleet", { cache: "no-store" });
        if (stopped) return;
        if (response.status === 404) {
          setState("disabled");
          setMessage("Fleet UI is disabled on this host.");
          setPayload(null);
          return;
        }
        if (!response.ok) throw new Error(`Fleet BFF HTTP ${response.status}`);
        const next = await response.json() as FleetWebPayload;
        if (stopped) return;
        processObservation(next);
        setPayload(next);
        setState("ready");
        setMessage("");
      } catch (error) {
        if (stopped) return;
        setState("error");
        setMessage(error instanceof Error ? error.message : "Fleet data unavailable");
      } finally {
        if (!stopped) timer = window.setTimeout(poll, 2_000);
      }
    }

    void poll();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  const facilities = useMemo(() => {
    const groups = new Map<string, FleetPPUView[]>();
    for (const ppu of payload?.ppus ?? []) {
      const key = ppu.identity.facility_id ?? "Unidentified Facility";
      const group = groups.get(key) ?? [];
      group.push(ppu);
      groups.set(key, group);
    }
    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [payload]);

  const siteViews = useMemo(() => {
    const views: { ppu: FleetPPUView; site: FleetSiteView; status: VisualStatus; key: string }[] = [];
    for (const ppu of payload?.ppus ?? []) {
      for (const site of ppu.topology.sites) {
        const key = siteKey(ppu, site);
        views.push({ ppu, site, key, status: siteStatus(ppu, site, clearedResults.get(key)) });
      }
    }
    return views;
  }, [payload, clearedResults]);

  const summary = useMemo(() => ({
    ppuOnline: (payload?.ppus ?? []).filter(ppuOperational).length,
    ppuTotal: payload?.ppus.length ?? 0,
    sites: siteViews.length,
    running: siteViews.filter(item => item.status === "running").length,
    pass: siteViews.filter(item => item.status === "pass").length,
    fail: siteViews.filter(item => item.status === "fail").length,
    offline: siteViews.filter(item => item.status === "offline").length,
  }), [payload, siteViews]);

  const ppuIds = useMemo(() => (payload?.ppus ?? []).map(ppuKey), [payload]);
  const filteredLogs = useMemo(() => logs.filter(entry => logFilter === "errors" ? entry.severity === "ERROR" : logFilter === "all" || entry.ppu === logFilter), [logs, logFilter]);

  useEffect(() => {
    if (!autoScroll || !logBodyRef.current) return;
    logBodyRef.current.scrollTop = logBodyRef.current.scrollHeight;
  }, [filteredLogs, autoScroll]);

  const detail = useMemo(() => {
    if (!selectedDetail || !payload) return null;
    const ppu = payload.ppus.find(item => ppuKey(item) === selectedDetail.ppu);
    const site = ppu?.topology.sites.find(item => item.site_id === selectedDetail.siteId);
    if (!ppu || !site) return null;
    const key = siteKey(ppu, site);
    return { ppu, site, key, status: siteStatus(ppu, site, clearedResults.get(key)), result: resultLabel(site, clearedResults.get(key)), terminalSignature: jobSignature(site.latest_job) };
  }, [selectedDetail, payload, clearedResults]);

  function selectAllForPpu(ppu: FleetPPUView) {
    if (!ppuOperational(ppu)) return;
    setSelectedSites(current => {
      const next = new Set(current);
      for (const site of ppu.topology.sites) if (site.enabled) next.add(siteKey(ppu, site));
      return next;
    });
  }

  function deselectAllForPpu(ppu: FleetPPUView) {
    setSelectedSites(current => {
      const next = new Set(current);
      for (const site of ppu.topology.sites) next.delete(siteKey(ppu, site));
      return next;
    });
  }

  function toggleSite(ppu: FleetPPUView, site: FleetSiteView) {
    if (!site.enabled || !ppuOperational(ppu)) return;
    const key = siteKey(ppu, site);
    setSelectedSites(current => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  function toggleOperation(code: string) {
    setSelectedOperations(current => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  }

  function clearDisplayedResult() {
    if (!detail?.terminalSignature || detail.result === "NONE") return;
    setClearedResults(current => {
      const next = new Map(current);
      next.set(detail.key, detail.terminalSignature as string);
      return next;
    });
    const entry: FactoryLogEntry = { id: ++logSequence.current, timestamp: nowTime(), ppu: ppuKey(detail.ppu), site: `SITE ${detail.site.site_id}`, severity: "INFO", operation: operationCode(detail.site), eventCode: "siteResultCleared", detail: detail.result };
    setLogs(current => [...current, entry].slice(-500));
  }

  return (
    <main className="fleetPage">
      <section className="fleetShell">
        <header className="productionHeading"><div><p>PRODUCTION MODE</p><h1>{t("production.title")}</h1><span>{t("production.subtitle")}</span></div><div className={`fleetHealth ${state}`}><i /><div><small>Fleet BFF</small><b>{state === "ready" ? t("fleet.online") : state === "loading" ? t("fleet.connecting") : state === "disabled" ? t("fleet.disabled") : t("fleet.unavailable")}</b></div></div></header>

        <section className="productionSummary" aria-label="Production summary"><article><small>{t("summary.ppuOnline")}</small><b>{summary.ppuOnline}/{summary.ppuTotal}</b></article><article><small>{t("summary.sites")}</small><b>{summary.sites}</b></article><article className="summaryRunning"><small>{t("summary.running")}</small><b>{summary.running}</b></article><article className="summaryPass"><small>{t("summary.pass")}</small><b>{summary.pass}</b></article><article className="summaryFail"><small>{t("summary.fail")}</small><b>{summary.fail}</b></article><article><small>{t("summary.offline")}</small><b>{summary.offline}</b></article></section>

        <section className="batchToolbar" aria-label="Production batch selection"><div className="selectionCount"><b>{t("selection.selectedSites")}: {selectedSites.size}</b><button type="button" onClick={() => setSelectedSites(new Set())}>{t("selection.clear")}</button></div><div className="operationChecks"><span>{t("selection.operations")}</span>{operations.map(operation => <label key={operation.code}><input type="checkbox" checked={selectedOperations.has(operation.code)} onChange={() => toggleOperation(operation.code)} /><b>{operation.code}</b> {t(operation.labelKey)}</label>)}</div><div className="batchActions" title={t("selection.writeLocked")}><button type="button" className="primary" disabled>{t("selection.execute")}</button><button type="button" disabled>{t("selection.cancel")}</button></div></section>

        <p className="productionBoundary">{t("production.readOnly")}</p>
        {state !== "ready" && <section className="fleetNotice" role="status"><b>{state === "disabled" ? t("fleet.disabledTitle") : t("fleet.unavailableTitle")}</b><p>{message}</p><p>{t("fleet.managerIndependent")}</p></section>}

        {facilities.map(([facilityId, ppus]) => <section className="facilityBlock" key={facilityId}><div className="facilityHead"><div><p>FACILITY</p><h2>{facilityId}</h2></div><span>{ppus.length} PPU{ppus.length === 1 ? "" : "s"}</span></div><div className="productionPpuStack">{ppus.map(ppu => {
          const id = ppuKey(ppu);
          const online = ppuOperational(ppu);
          return <article className="productionPpu" key={id} data-ppu={id}><header className="productionPpuHead"><div className="ppuIdentity"><i className={online ? "online" : "offline"} /><div><small>{ppu.alias ?? "PPU"}</small><h3>{displayName(ppu)}</h3></div></div><div className="ppuTelemetry"><span>{t("ppu.transport")}: <b>{ppu.transport_state.toUpperCase()}</b></span><span>{t("ppu.gateway")}: <b>{ppu.observation.state.toUpperCase()}</b></span></div><div className="ppuSelection"><button type="button" onClick={() => selectAllForPpu(ppu)} disabled={!online}>{t("selection.selectAll")}</button><button type="button" onClick={() => deselectAllForPpu(ppu)}>{t("selection.deselectAll")}</button><span>{t("ppu.sites")}: {ppu.topology.sites.length}</span></div></header><div className="siteProductionGrid">{ppu.topology.sites.map(site => {
            const key = siteKey(ppu, site);
            const status = siteStatus(ppu, site, clearedResults.get(key));
            const result = resultLabel(site, clearedResults.get(key));
            const selectable = site.enabled && online;
            const selected = selectedSites.has(key);
            const job = site.latest_job;
            return <article key={site.site_id} className={`productionSite status-${status} ${selected ? "selected" : ""}`} data-site-id={site.site_id} data-status={status} onClick={() => setSelectedDetail({ ppu: id, siteId: site.site_id })}><div className="siteCardTop"><label onClick={event => event.stopPropagation()}><input type="checkbox" aria-label={`${id} SITE ${site.site_id}`} checked={selected} disabled={!selectable} onChange={() => toggleSite(ppu, site)} /></label><b>SITE {site.site_id}</b>{result !== "NONE" && <span className="latchedBadge">LATCHED</span>}</div><div className={`statusLamp ${status}`} aria-hidden="true"><i /></div><strong>{t(`status.${status}`)}</strong><div className="siteCardMeta"><span>{t("site.execution")}: <b>{job?.state.toUpperCase() ?? site.state.toUpperCase()}</b></span><span>{t("site.operation")}: <b>{operationCode(site)}</b></span>{status === "running" && job && <span>{t("site.progress")}: <b>{Math.round(job.progress_percent)}%</b></span>}</div></article>;
          })}</div></article>;
        })}</div></section>)}

        <section className={`factoryLogPanel ${fullLog ? "full" : ""}`} aria-label={t("log.title")}><header className="factoryLogHead"><div><p>FACTORY OBSERVABILITY</p><h2>{t("log.title")}</h2></div><div className="logControls"><label><input type="checkbox" checked={autoScroll} onChange={event => setAutoScroll(event.target.checked)} /> {t("log.autoScroll")}</label><button type="button" onClick={() => setLogs([])}>{t("log.clear")}</button><button type="button" onClick={() => setFullLog(value => !value)}>{fullLog ? t("log.closeFull") : t("log.full")}</button></div></header><div className="logTabs"><button type="button" className={logFilter === "all" ? "active" : ""} onClick={() => setLogFilter("all")}>{t("log.all")}</button><button type="button" className={logFilter === "errors" ? "active" : ""} onClick={() => setLogFilter("errors")}>{t("log.errors")}</button>{ppuIds.map(id => <button key={id} type="button" className={logFilter === id ? "active" : ""} onClick={() => setLogFilter(id)}>{id}</button>)}</div><p className="logContractNote">{t("log.observationNote")}</p><div className="logTableHead"><span>{t("log.time")}</span><span>{t("log.ppu")}</span><span>{t("log.site")}</span><span>{t("log.level")}</span><span>{t("log.operation")}</span><span>{t("log.message")}</span></div><div className="logBody" ref={logBodyRef}>{filteredLogs.length === 0 && <div className="emptyLog">{t("log.empty")}</div>}{filteredLogs.map(entry => <div className={`logRow severity-${entry.severity.toLowerCase()}`} key={entry.id}><span>{entry.timestamp}</span><span>{entry.ppu}</span><span>{entry.site ?? "—"}</span><span><b>{entry.severity}</b></span><span>{entry.operation}</span><span>{t(`log.event.${entry.eventCode}`)} · {entry.detail}</span></div>)}</div></section>
      </section>

      {detail && <aside className="siteDetailDrawer" aria-label={t("site.detail")}><header><div><small>{ppuKey(detail.ppu)}</small><h2>SITE {detail.site.site_id}</h2></div><button type="button" aria-label="Close" onClick={() => setSelectedDetail(null)}>×</button></header><div className={`detailResult status-${detail.status}`}><i /><b>{t(`status.${detail.status}`)}</b>{detail.result !== "NONE" && <span>LATCHED</span>}</div><dl><div><dt>PPU</dt><dd>{displayName(detail.ppu)}</dd></div><div><dt>SITE</dt><dd>SITE {detail.site.site_id}</dd></div><div><dt>{t("site.execution")}</dt><dd>{detail.site.latest_job?.state.toUpperCase() ?? detail.site.state.toUpperCase()}</dd></div><div><dt>{t("site.lastResult")}</dt><dd>{detail.result}</dd></div><div><dt>{t("site.operation")}</dt><dd>{operationCode(detail.site)}</dd></div><div><dt>Job ID</dt><dd>{detail.site.latest_job?.job_id ?? "—"}</dd></div><div><dt>{t("site.progress")}</dt><dd>{detail.site.latest_job ? `${Math.round(detail.site.latest_job.progress_percent)}%` : "—"}</dd></div><div><dt>Stage</dt><dd>{detail.site.latest_job?.stage ?? "—"}</dd></div><div><dt>{t("site.interface")}</dt><dd>{detail.site.interface ?? "—"}</dd></div><div><dt>{t("site.target")}</dt><dd>{detail.site.target ?? "—"}</dd></div><div><dt>{t("ppu.transport")}</dt><dd>{detail.ppu.transport_state}</dd></div></dl><button type="button" className="clearResultButton" onClick={clearDisplayedResult} disabled={!detail.terminalSignature || detail.result === "NONE"}>{t("site.clearResult")}</button></aside>}
    </main>
  );
}
