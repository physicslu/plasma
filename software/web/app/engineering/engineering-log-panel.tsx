"use client";

import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { useWorkspaceSession } from "../workspace-session";

export type EngineeringLogCategory = "USR" | "NET" | "PPU" | "DAT" | "BAT" | "SYS";

export type EngineeringLogEntry = {
  id: number;
  text: string;
  error: boolean;
  category: EngineeringLogCategory;
};

export const ENGINEERING_LOG_CATEGORIES: EngineeringLogCategory[] = [
  "USR",
  "NET",
  "PPU",
  "DAT",
  "BAT",
  "SYS",
];

export function classifyEngineeringLog(message: string): EngineeringLogCategory {
  if (
    message.startsWith("[IMG]")
    || message.startsWith("[ASSET]")
    || message.startsWith("[KEY]")
    || message.startsWith("[OPT]")
    || message.startsWith("[SERIAL]")
  ) return "DAT";
  if (
    message.startsWith("[SESSION]")
    || message.startsWith("[ENGINEERING]")
    || message.startsWith("[NET]")
    || message.startsWith("[CONNECTION]")
  ) return "NET";
  if (message.startsWith("[SITE-")) return "PPU";
  if (message.startsWith("[BATCH]")) return "BAT";
  return "SYS";
}

export function engineeringLogCategoryLabel(category: EngineeringLogCategory): string {
  return category.padEnd(3, " ");
}

function engineeringLogText(entry: EngineeringLogEntry): string {
  // Compatibility normalization: older Engineering workspace state still
  // carries offset/length fields. Canonical R means Read Entire Main Flash, so
  // operator-facing audit text must not present those legacy values as intent.
  return entry.text
    .replace(/ · read offset \d+ · length \d+/gi, " · read MAIN FLASH")
    .replace(/ · offset \d+ · length \d+/gi, " · MAIN FLASH");
}

function logDownloadTimestamp(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

type EngineeringLogPanelProps = {
  logs: EngineeringLogEntry[];
  onClear: () => void;
};

export default function EngineeringLogPanel({ logs, onClear }: EngineeringLogPanelProps) {
  const { t } = useI18n();
  const { sessionAuditEntries, clearSessionAuditEntries } = useWorkspaceSession();
  const [visibleCategories, setVisibleCategories] = useState<EngineeringLogCategory[]>(ENGINEERING_LOG_CATEGORIES);
  const allLogs = useMemo<EngineeringLogEntry[]>(() => {
    const localLogs = logs.filter(log => !log.text.includes("[SESSION] ACTIVE ·"));
    const sessionLogs: EngineeringLogEntry[] = sessionAuditEntries.map(entry => ({
      id: -entry.id,
      text: `${entry.time}  [NET] ${entry.message}`,
      error: false,
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
    const content = `${allLogs.map(engineeringLogText).join("\n")}\n`;
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `plasma-engineering-${logDownloadTimestamp(new Date())}.log`;
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
    <section className="logCard engineeringLogCard">
      <div className="logHead engineeringLogHead">
        <div className="engineeringLogTitle"><span />{t("engineeringProgramming.jobLog")}</div>
        <div className="engineeringLogActions">
          <button type="button" onClick={downloadLog} disabled={!allLogs.length}>Download .log</button>
          <button type="button" onClick={clearLog}>{t("engineeringProgramming.clear")}</button>
        </div>
      </div>
      <div className="engineeringLogFilters" role="group" aria-label="Engineering log filters">
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
              aria-label={`Engineering log filter ${category}`}
              checked={visibleCategories.includes(category)}
              onChange={() => toggleCategory(category)}
            />
            <span>{engineeringLogCategoryLabel(category)}</span>
          </label>
        ))}
      </div>
      <pre aria-label="Engineering job log">
        {visibleLogs.length
          ? visibleLogs.map(log => (
            <span
              key={`${log.category}-${log.id}`}
              data-level={log.error ? "error" : "info"}
              data-category={log.category}
            >
              {engineeringLogText(log)}
            </span>
          ))
          : "No log entries for selected filters."}
      </pre>
    </section>
  );
}
