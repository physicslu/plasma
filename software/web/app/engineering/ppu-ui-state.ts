import type { FleetPPUView } from "../fleet/fleet-contract";
import type { ManagerRegistryEntry } from "./ppu-registry-api";

export type PpuStateTone = "healthy" | "warning" | "danger" | "muted" | "info";

export type PpuDimensionState = {
  label: string;
  reason: string;
  tone: PpuStateTone;
};

export type PpuValidationPrerequisite = {
  key: "observation" | "transport" | "execution" | "identity" | "degraded";
  label: string;
  passed: boolean;
  detail: string;
};

export function lifecycleState(entry: ManagerRegistryEntry): PpuDimensionState {
  if (entry.lifecycle === "commissioned") {
    return {
      label: "Commissioned",
      reason: "Registry admission is complete and the PPU may be used for managed operations.",
      tone: "healthy",
    };
  }
  if (entry.lifecycle === "disabled") {
    return {
      label: "Disabled",
      reason: "The PPU remains registered but is disabled for managed operations.",
      tone: "muted",
    };
  }
  return {
    label: "Pending",
    reason: "Registry admission is not complete. Validation prerequisites must pass before enablement.",
    tone: "warning",
  };
}

export function connectivityState(fleetView: FleetPPUView | null): PpuDimensionState {
  if (!fleetView || fleetView.transport_state === "unknown") {
    return {
      label: "Unknown",
      reason: "Transport reachability is not currently observable.",
      tone: "muted",
    };
  }
  if (fleetView.transport_state === "unreachable") {
    return {
      label: "Offline",
      reason: "The Manager cannot reach the PPU transport endpoint.",
      tone: "danger",
    };
  }
  return {
    label: "Online",
    reason: "The PPU transport endpoint is reachable.",
    tone: "healthy",
  };
}

export function healthState(fleetView: FleetPPUView | null): PpuDimensionState {
  if (!fleetView) {
    return {
      label: "Unknown",
      reason: "No Fleet health observation is available.",
      tone: "muted",
    };
  }
  if (fleetView.identity_conflict) {
    return {
      label: "Error",
      reason: "A canonical PPU identity conflict was detected.",
      tone: "danger",
    };
  }
  if (fleetView.degraded) {
    if (fleetView.execution_state !== "ready") {
      return {
        label: "Degraded",
        reason: `Execution service is ${fleetView.execution_state}; the PPU is not fully ready.`,
        tone: "warning",
      };
    }
    return {
      label: "Degraded",
      reason: "The Fleet observation reports one or more degraded PPU conditions.",
      tone: "warning",
    };
  }
  return {
    label: "Healthy",
    reason: "No degraded health condition is reported.",
    tone: "healthy",
  };
}

function observationDetail(fleetView: FleetPPUView | null): string {
  if (!fleetView) return "No Fleet observation is available.";
  if (fleetView.observation.state === "current") return "Observation data is current.";
  if (fleetView.observation.state === "stale") {
    if (fleetView.observation.stale_age_s !== null) {
      const ageSeconds = Math.max(0, Math.round(fleetView.observation.stale_age_s));
      return `Observation data is stale (${ageSeconds}s old).`;
    }
    return "Observation data is stale.";
  }
  return "Observation freshness is unknown.";
}

export function validationPrerequisites(fleetView: FleetPPUView | null): PpuValidationPrerequisite[] {
  return [
    {
      key: "observation",
      label: "Observation current",
      passed: fleetView?.observation.state === "current",
      detail: observationDetail(fleetView),
    },
    {
      key: "transport",
      label: "Transport reachable",
      passed: fleetView?.transport_state === "reachable",
      detail: !fleetView
        ? "No transport observation is available."
        : fleetView.transport_state === "reachable"
          ? "Transport layer is reachable."
          : `Transport state is ${fleetView.transport_state}.`,
    },
    {
      key: "execution",
      label: "Execution ready",
      passed: fleetView?.execution_state === "ready",
      detail: !fleetView
        ? "No execution observation is available."
        : fleetView.execution_state === "ready"
          ? "Execution service is ready."
          : `Execution service is ${fleetView.execution_state}.`,
    },
    {
      key: "identity",
      label: "No identity conflict",
      passed: Boolean(fleetView && !fleetView.identity_conflict),
      detail: !fleetView
        ? "Canonical PPU identity is not currently observable."
        : fleetView.identity_conflict
          ? "A conflicting canonical PPU identity was detected."
          : "No canonical PPU identity conflict is reported.",
    },
    {
      key: "degraded",
      label: "Not degraded",
      passed: Boolean(fleetView && !fleetView.degraded),
      detail: !fleetView
        ? "PPU health is not currently observable."
        : fleetView.degraded
          ? "The Fleet observation reports a degraded condition."
          : "No degraded condition is reported.",
    },
  ];
}

export function canValidateAndEnable(fleetView: FleetPPUView | null): boolean {
  return validationPrerequisites(fleetView).every(item => item.passed);
}

export function validationBlockSummary(fleetView: FleetPPUView | null): string {
  const failed = validationPrerequisites(fleetView).filter(item => !item.passed);
  return failed.length ? failed.map(item => item.label).join(", ") : "None";
}
