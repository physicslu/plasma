"use client";

import { useState } from "react";
import "./operator-log-panel.css";

export type OperatorLogCategory = "USR" | "NET" | "PPU" | "DAT" | "BAT" | "SYS";
export type OperatorLogLevel = "info" | "warn" | "error";

export type OperatorLogEntry = {
  id: number;
  text: string;
  level: OperatorLogLevel;
  category: OperatorLogCategory;
};

export const OPERATOR_LOG_CATEGORIES: OperatorLogCategory[] = [
  "USR",
  "NET",
  "PPU",
  "DAT",
  "BAT",
  "SYS",
];

export function operatorLogCategoryLabel(category: OperatorLogCategory): string {
  return category.padEnd(3, " ");
}

function logDownloadTimestamp(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

export function OperatorLogPanel({
  entries,
  title,
  clearLabel,
  onClear,
  downloadFilenamePrefix,
  filterAriaLabel,
  logAriaLabel,
  emptyText = "No log entries for selected filters.",
  className = "",
}: {
  entries: OperatorLogEntry[];
  title: string;
  clearLabel: string;
  onClear: () => void;
  downloadFilenamePrefix: string;
  filterAriaLabel: string;
  logAriaLabel: string;
  emptyText?: string;
  className?: string;
}) {
  const [visibleCategories, setVisibleCategories] = useState<OperatorLogCategory[]>(OPERATOR_LOG_CATEGORIES);
  const visibleLogs = entries.filter(log => visibleCategories.includes(log.category));
  const allVisible = visibleCategories.length === OPERATOR_LOG_CATEGORIES.length;

  function toggleCategory(category: OperatorLogCategory) {
    setVisibleCategories(current => current.includes(category)
      ? current.filter(item => item !== category)
      : OPERATOR_LOG_CATEGORIES.filter(item => current.includes(item) || item === category));
  }

  function downloadLog() {
    if (!entries.length) return;
    const content = `${entries.map(entry => entry.text).join("\n")}\n`;
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${downloadFilenamePrefix}-${logDownloadTimestamp(new Date())}.log`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
  }

  return (
    <section className={`logCard operatorLogCard ${className}`.trim()} aria-label={title}>
      <div className="logHead operatorLogHead">
        <div className="operatorLogTitle"><span />{title}</div>
        <div className="operatorLogActions">
          <button type="button" onClick={downloadLog} disabled={!entries.length}>Download .log</button>
          <button type="button" onClick={onClear}>{clearLabel}</button>
        </div>
      </div>
      <div className="operatorLogFilters" role="group" aria-label={filterAriaLabel}>
        <button
          type="button"
          className={allVisible ? "active" : ""}
          aria-pressed={allVisible}
          onClick={() => setVisibleCategories(OPERATOR_LOG_CATEGORIES)}
        >
          ALL
        </button>
        {OPERATOR_LOG_CATEGORIES.map(category => (
          <label key={category} className={visibleCategories.includes(category) ? "active" : ""}>
            <input
              type="checkbox"
              aria-label={`${filterAriaLabel} ${category}`}
              checked={visibleCategories.includes(category)}
              onChange={() => toggleCategory(category)}
            />
            <span>{operatorLogCategoryLabel(category)}</span>
          </label>
        ))}
      </div>
      <pre aria-label={logAriaLabel}>
        {visibleLogs.length
          ? visibleLogs.map(log => (
            <span
              key={`${log.category}-${log.id}`}
              data-level={log.level}
              data-category={log.category}
            >
              {log.text}
            </span>
          ))
          : emptyText}
      </pre>
    </section>
  );
}
