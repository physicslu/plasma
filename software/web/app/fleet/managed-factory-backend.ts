// PMode Factory Console projection of canonical Manager-owned Batch.
// The Manager alone schedules PPU/Site Jobs, persists Journal/Receipt and
// applies retry/stop. This module only projects truth into the Factory UI.

import type { EngineeringTargetCatalog, PPUStatus } from "../plasma-api";
import {
  siteCapability, type ManagedTopology, type ProgrammingRoute,
} from "../programming/managed-programming";
import type { ProgrammingBatch, ProgrammingBatchUnit } from "../engineering/bundle-programming-api";
import type { ProgrammingCapabilityCatalog } from "../programming-capabilities";
import type { BatchSiteSnapshot, ServerBatchSiteState, ServerBatchSnapshot, ServerBatchState } from "../server-batch-api";

/** Factory catalog keyed by Manager Alias; the device PPU ID is shown, never routed on. */
export function managedFactoryCatalog(topology: ManagedTopology): ProgrammingCapabilityCatalog {
  const catalog: EngineeringTargetCatalog = {
    ok: true,
    provider: "manager",
    facility_count: topology.facilities.length,
    ppu_count: topology.ppus.length,
    site_count: topology.ppus.reduce((total, ppu) => total + ppu.siteCount, 0),
    facilities: topology.facilities.map(facility => ({
      facility_id: facility.facilityId,
      display_name: facility.displayName,
      ppus: facility.ppus.map(ppu => ({
        ppu_id: ppu.alias,
        display_name: `${ppu.alias} · PPU ID ${ppu.ppuId ?? "unknown"}`,
        model: ppu.model ?? "—",
        site_count: ppu.siteCount,
        provider: "manager",
      })),
    })),
  };
  return {
    ...catalog,
    // A formal Flash Job always needs an explicit IC and a real file.
    programming_capabilities: { synthetic_programming_image: false, target_device_required: true },
  };
}

/** Site status of one PPU from the Manager Fleet. Throws the exact reason when not observable. */
export function managedPpuStatus(topology: ManagedTopology, alias: string): PPUStatus {
  const ppu = topology.ppus.find(item => item.alias === alias);
  if (!ppu) throw new Error("PPU is not a commissioned Manager Registry entry");
  if (!ppu.online) throw new Error(`${ppu.availability.label} · ${ppu.availability.reason}`);
  return {
    sites: ppu.sites.map(site => ({
      site_id: site.site_id,
      enabled: site.enabled,
      state: site.state,
      current_job_id: site.current_job_id,
      target: site.target,
      interface: site.interface,
    })) as PPUStatus["sites"],
  };
}

/** Managed PMode is restricted to sequential, attended, session-based operation. */
export const MANAGED_PRODUCTION_MODE = Object.freeze({
  readyLabel: "MANAGER BATCH READY",
});

export type ManagedBatchReadiness = { ready: boolean; label: string; reason: string };

/** Every selected Site must be programmable on its own PPU; one blocker blocks the batch Start. */
export function managedBatchBlocker(
  topology: ManagedTopology | null,
  routes: ProgrammingRoute[] | null,
  icpn: string | null,
  targets: Array<{ alias: string; siteIds: number[] }>,
): ManagedBatchReadiness | null {
  if (!topology) return { ready: false, label: "MANAGER OFFLINE", reason: "The Manager Registry is unavailable." };
  for (const target of targets) {
    const ppu = topology.ppus.find(item => item.alias === target.alias);
    if (!ppu) {
      return { ready: false, label: "PPU NOT REGISTERED", reason: `PPU ${target.alias} is not a commissioned Registry entry.` };
    }
    if (!ppu.availability.ready) {
      return { ready: false, label: ppu.availability.label, reason: `PPU ${ppu.alias}: ${ppu.availability.reason}` };
    }
    for (const siteId of target.siteIds) {
      const site = ppu.sites.find(item => item.site_id === siteId);
      const capability = site ? siteCapability(site, routes, icpn) : null;
      if (!capability?.programmable) {
        return {
          ready: false,
          label: "PROGRAMMING UNAVAILABLE",
          reason: `PPU ${ppu.alias} Site ${siteId}: ${capability?.reason ?? "the Site is not reported by the PPU."}`,
        };
      }
    }
  }
  return null;
}


/**
 * Render the Manager's canonical per-Site outcomes in PMode's existing LED,
 * PASS/FAIL/Yield and Batch Summary schema. This is a READ-ONLY projection:
 * it neither schedules a Site nor derives PASS from HTTP 200.
 */
export function managedProductionSnapshot(
  batch: ProgrammingBatch,
  topology: ManagedTopology | null,
): ServerBatchSnapshot {
  const siteState = (unit: ProgrammingBatchUnit): ServerBatchSiteState => {
    if (unit.outcome === "PASS") return "success";
    if (unit.outcome === "FAIL") return "faulted";
    if (unit.outcome === "STOPPED"
        || (unit.outcome === "BLOCKED" && /STOP_|STOP_POLICY|PPU_LATCHED/.test(unit.reason ?? ""))) return "stopped";
    if (unit.outcome != null) return "error";
    if (unit.attempts.some(item => item.outcome == null)) return "running";
    return batch.stop_requested ? "stopped" : "ready";
  };
  const sites: BatchSiteSnapshot[] = batch.units.map(unit => {
    const ppu = topology?.ppus.find(item => item.alias === unit.ppu_alias);
    const state = siteState(unit);
    const last = unit.attempts[unit.attempts.length - 1] ?? null;
    const current = batch.current_run?.run_id === last?.run_id ? batch.current_run : null;
    const passed = state === "success";
    return {
      facility_id: ppu?.facilityId ?? "unassigned",
      ppu_id: unit.ppu_alias, site_id: unit.site_id,
      key: `${unit.ppu_alias}:${unit.site_id}`,
      state,
      current_round: unit.attempts.length ? 1 : 0,
      completed_rounds: passed ? 1 : 0,
      current_operation: null, current_job_id: last?.job_id ?? null,
      progress_percent: passed ? 100 : current?.job?.progress_percent ?? 0,
      total_attempts: unit.attempts.length,
      retry_count: Math.max(0, unit.attempts.length - 1),
      final_failures: state === "faulted" ? 1 : 0,
      faulted_round: state === "faulted" ? 1 : null,
      faulted_operation: null,
      last_failure_source: state === "faulted" || state === "error" ? unit.failure_domain ?? "manager_programming_run" : null,
      error: state === "faulted" || state === "error"
        ? { message: unit.reason ?? (unit.outcome === "OUTCOME_UNKNOWN" ? "OUTCOME UNKNOWN; do not resubmit" : "Manager reports no PASS") }
        : null,
      operation_statistics: {},
    };
  });
  const site_counts: Record<ServerBatchSiteState, number> = {
    ready: 0, running: 0, success: 0, faulted: 0, error: 0, stopped: 0, cancelled: 0,
  };
  for (const site of sites) site_counts[site.state] += 1;
  const state: ServerBatchState = batch.outcome == null
    ? batch.stop_requested ? "stopping" : "running"
    : batch.outcome === "PASS" ? "success"
    : batch.outcome === "PARTIAL" || (batch.outcome === "FAIL" && batch.counts.pass > 0) ? "partial"
    : batch.outcome === "STOPPED" ? "cancelled"
    : "error";
  return {
    batch_id: batch.batch_id, state,
    // The current Manager Batch response has no timestamps; never fabricate one.
    created_at: "", started_at: null, finished_at: null,
    operations: [...batch.operations],
    execution_policy: {
      repeat_count: 1,
      site_retry_limit: batch.policy.retry_limit,
      failed_site_stop_threshold: batch.policy.stop_policy.kind === "failed_sites"
        ? batch.policy.stop_policy.threshold : null,
    },
    target_device: null, asset: null, read: { scope: "main_flash" },
    cancel_requested: batch.stop_requested,
    stop_reason: batch.stop_requested ? batch.reason : null,
    error: state === "error" ? { message: batch.reason ?? "Manager Batch not confirmed PASS" } : null,
    faulted_site_count: site_counts.faulted,
    site_counts, operation_statistics: {}, sites,
  };
}
