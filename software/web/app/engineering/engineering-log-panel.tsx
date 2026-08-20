"use client";

import { useMemo, useState } from "react";
import { useI18n } from "../i18n";

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
  return entry.text;
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
  const [visibleCategories, setVisibleCategories] = useState<EngineeringLogCategory[]>(ENGINEERING_LOG_CATEGORIES);
  const visibleLogs = useMemo(
    () => logs.filter(log => visibleCategories.includes(log.category)),
    [logs, visibleCategories],
  );
  const allVisible = visibleCategories.length === ENGINEERING_LOG_CATEGORIES.length;

  function toggleCategory(category: EngineeringLogCategory) {
    setVisibleCategories(current => current.includes(category)
      ? current.filter(item => item !== category)
      : ENGINEERING_LOG_CATEGORIES.filter(item => current.includes(item) || item === category));
  }

  function downloadLog() {
    if (!logs.length) return;
    const content = `${logs.map(engineeringLogText).join("\n")}\n`;
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

  return (
    <section className="logCard engineeringLogCard">
      <div className="logHead engineeringLogHead">
        <div className="engineeringLogTitle"><span />{t("engineeringProgramming.jobLog")}</div>
        <div className="engineeringLogActions">
          <button type="button" onClick={downloadLog} disabled={!logs.length}>Download .log</button>
          <button type="button" onClick={onClear}>{t("engineeringProgramming.clear")}</button>
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
              key={log.id}
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