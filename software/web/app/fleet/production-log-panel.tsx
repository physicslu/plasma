"use client";

import { useMemo } from "react";
import {
  OperatorLogPanel,
  operatorLogCategoryLabel,
  type OperatorLogCategory,
  type OperatorLogEntry,
} from "../operator-ui/operator-log-panel";
import { useWorkspaceSession } from "../workspace-session";

export type ProductionLogEntry = {
  id: number;
  time: string;
  level: "INFO" | "WARN" | "ERROR";
  text: string;
};

type ProductionLogPanelProps = {
  logs: ProductionLogEntry[];
  title: string;
  clearLabel: string;
  onClear: () => void;
};

type ProductionLogClassification = {
  category: OperatorLogCategory;
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

export default function ProductionLogPanel({ logs, title, clearLabel, onClear }: ProductionLogPanelProps) {
  const { sessionAuditEntries, clearSessionAuditEntries } = useWorkspaceSession();
  const allLogs = useMemo<OperatorLogEntry[]>(() => {
    const localLogs = logs.map(entry => {
      const classification = productionLogClassification(entry.text);
      return {
        id: entry.id,
        text: `${entry.time}  [${operatorLogCategoryLabel(classification.category)}] ${classification.message}`,
        level: entry.level.toLowerCase() as OperatorLogEntry["level"],
        category: classification.category,
      };
    });
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
      title={title}
      clearLabel={clearLabel}
      onClear={clearLog}
      downloadFilenamePrefix="plasma-production"
      filterAriaLabel="Production log filters"
      logAriaLabel="Production batch log"
      className="productionLogCard productionOperatorLog"
    />
  );
}
