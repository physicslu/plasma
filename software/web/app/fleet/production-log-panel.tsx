"use client";

import { useMemo, useState } from "react";
import { useWorkspaceSession } from "../workspace-session";
import {
  ENGINEERING_LOG_CATEGORIES,
  engineeringLogCategoryLabel,
  type EngineeringLogCategory,
} from "../engineering/engineering-log-panel";
import "./production-log.css";

export type ProductionLogEntry = {
  id: number;
  time: string;
  level: "INFO" | "WARN" | "ERROR";
  text: string;
};

type NormalizedProductionLogEntry = {
  id: number;
  text: string;
  level: ProductionLogEntry["level"];
  category: EngineeringLogCategory;
};

type ProductionLogPanelProps = {
  logs: ProductionLogEntry[];
  title: string;
  clearLabel: string;
  onClear: () => void;
};

type ProductionLogClassification = {
  category: EngineeringLogCategory;
  message: string;
};

function productionLogClassification(message: string): ProductionLogClassification {
  if (message.startsWith("[BAT]")) {
    return { category: "BAT", message: message.slice("[BAT]".length).trimStart() };
  }
  if (message.startsWith("[PPU]")) {
    return { category: "PPU", message: message.slice("[PPU]".length).trimStart() };
  }
  if (
    message.startsWith("[IMG]")
    || message.startsWith("[ASSET]")
    || message.startsWith("[KEY]")
    || message.startsWith("[OPT]")
    || message.startsWith("[SERIAL]")
  ) return { category: "DAT", message };
  if (
    message.startsWith("[PROVIDER]")
    || message.startsWith("[SESSION]")
    || message.startsWith("[NET]")
    || message.startsWith("[CONNECTION]")
  ) return { category: "NET", message };
  if (message.startsWith("[SITE-")) return { category: "PPU", message };
  if (message.startsWith("[FPS]")) return { category: "USR", message };
  return { category: "SYS", message };
}

function renderProductionLog(entry: NormalizedProductionLogEntry): string {
  return entry.text;
}

function logDownloadTimestamp(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

export default function ProductionLogPanel({ logs, title, clearLabel, onClear }: ProductionLogPanelProps) {
  const { sessionAuditEntries, clearSessionAuditEntries } = useWorkspaceSession();
  const [visibleCategories, setVisibleCategories] = useState<EngineeringLogCategory[]>(ENGINEERING_LOG_CATEGORIES);
  const allLogs = useMemo<NormalizedProductionLogEntry[]>(() => {
    const localLogs = logs.map(entry => {
      const classification = productionLogClassification(entry.text);
      return {
        id: entry.id,
        text: `${entry.time}  [${engineeringLogCategoryLabel(classification.category)}] ${classification.message}`,
        level: entry.level,
        category: classification.category,
      };
    });
    const sessionLogs: NormalizedProductionLogEntry[] = sessionAuditEntries.map(entry => ({
      id: -entry.id,
      text: `${entry.time}  [NET] ${entry.message}`,
      level: "INFO",
      category: "NET",
    }));
    return [...localLogs, ...sessionLogs].sort((left, right) => {
      const timeOrder = right.text.slice(0, 8).localeCompare(left.text.slice(0, 8));
      return timeOrder || right.id - left.id;
    });
  }, [logs, sessionAuditEntries]);
  const visibleLogs = useMemo(
    () => allLogs.filter(log => visibleCategories.includes(log.category)),
    [allLogs, visibleCategories],
  );
  const allVisible = visibleCategories.length === ENGINEERING_LOG_CATEGORIES.length;

  function toggleCategory(category: EngineeringLogCategory) {
    setVisibleCategories(current => current.includes(category)
      ? current.filter(item => item !== category)
      : ENGINEERING_LOG_CATEGORIES.filter(item => current.includes(item) || item === category));
  }

  function downloadLog() {
    if (!allLogs.length) return;
    const content = `${allLogs.map(renderProductionLog).join("\n")}\n`;
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `plasma-production-${logDownloadTimestamp(new Date())}.log`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
  }

  function clearLog() {
    onClear();
    clearSessionAuditEntries();
  }

  return (
    <section className="logCard engineeringLogCard productionLogCard">
      <div className="logHead engineeringLogHead">
        <div className="engineeringLogTitle"><span />{title}</div>
        <div className="engineeringLogActions">
          <button type="button" onClick={downloadLog} disabled={!allLogs.length}>Download .log</button>
          <button type="button" onClick={clearLog}>{clearLabel}</button>
        </div>
      </div>
      <div className="engineeringLogFilters" role="group" aria-label="Production log filters">
        <button
          type="button"
          className={allVisible ? "active" : ""}
          aria-pressed={allVisible}
          onClick={() => setVisibleCategories(ENGINEERING_LOG_CATEGORIES)}
        >
          ALL
        </button>
        {ENGINEERING_LOG_CATEGORIES.map(category => (
          <label key={category} className={visibleCategories.includes(category) ? "active" : ""}>
            <input
              type="checkbox"
              aria-label={`Production log filter ${category}`}
              checked={visibleCategories.includes(category)}
              onChange={() => toggleCategory(category)}
            />
            <span>{engineeringLogCategoryLabel(category)}</span>
          </label>
        ))}
      </div>
      <pre aria-label="Production batch log">
        {visibleLogs.length
          ? visibleLogs.map(log => (
            <span
              key={`${log.category}-${log.id}`}
              data-level={log.level.toLowerCase()}
              data-category={log.category}
            >
              {renderProductionLog(log)}
            </span>
          ))
          : "No log entries for selected filters."}
      </pre>
    </section>
  );
}
