"use client";

import { useMemo } from "react";
import { useI18n } from "../i18n";
import {
  OPERATOR_LOG_CATEGORIES,
  OperatorLogPanel,
  operatorLogCategoryLabel,
  type OperatorLogCategory,
  type OperatorLogEntry,
} from "../operator-ui/operator-log-panel";
import { useWorkspaceSession } from "../workspace-session";
import "./engineering-log-placement.css";

export type EngineeringLogCategory = OperatorLogCategory;

export type EngineeringLogEntry = {
  id: number;
  text: string;
  error: boolean;
  category: EngineeringLogCategory;
};

export const ENGINEERING_LOG_CATEGORIES: EngineeringLogCategory[] = OPERATOR_LOG_CATEGORIES;

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
  return operatorLogCategoryLabel(category);
}

function engineeringLogText(entry: EngineeringLogEntry): string {
  return entry.text
    .replace(/ · read offset \d+ · length \d+/gi, " · read MAIN FLASH")
    .replace(/ · offset \d+ · length \d+/gi, " · MAIN FLASH");
}

type EngineeringLogPanelProps = {
  logs: EngineeringLogEntry[];
  onClear: () => void;
};

export default function EngineeringLogPanel({ logs, onClear }: EngineeringLogPanelProps) {
  const { t } = useI18n();
  const { sessionAuditEntries, clearSessionAuditEntries } = useWorkspaceSession();
  const allLogs = useMemo<OperatorLogEntry[]>(() => {
    const localLogs = logs
      .filter(log => !log.text.includes("[SESSION] ACTIVE ·"))
      .map(log => ({
        id: log.id,
        text: engineeringLogText(log),
        level: log.error ? "error" as const : "info" as const,
        category: log.category,
      }));
    const sessionLogs: OperatorLogEntry[] = sessionAuditEntries.map(entry => ({
      id: -entry.id,
      text: `${entry.time}  [NET] ${entry.message}`,
      level: "info",
      category: "NET",
    }));
    return [...localLogs, ...sessionLogs].sort((left, right) => {
      const timeOrder = right.text.slice(0, 8).localeCompare(left.text.slice(0, 8));
      return timeOrder || right.id - left.id;
    });
  }, [logs, sessionAuditEntries]);

  function clearLog() {
    onClear();
    clearSessionAuditEntries();
  }

  return (
    <OperatorLogPanel
      entries={allLogs}
      title={t("engineeringProgramming.jobLog")}
      clearLabel={t("engineeringProgramming.clear")}
      onClear={clearLog}
      downloadFilenamePrefix="plasma-engineering"
      filterAriaLabel="Engineering log filters"
      filterItemAriaLabelPrefix="Engineering log filter"
      logAriaLabel="Engineering job log"
      className="engineeringOperatorLog"
    />
  );
}
