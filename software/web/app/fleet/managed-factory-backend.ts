// PMode Factory Console projection of canonical Manager-owned Batch.
// The Manager alone schedules PPU/Site Jobs, persists Journal/Receipt and
// applies retry/stop. This module only projects truth into the Factory UI.

import type { EngineeringTargetCatalog, PPUStatus } from "../plasma-api";
import {
  awaitingUnits, batchSiteVerdict, runOfUnit, siteCapability, unitCycleLabel, unitFailDetail,
  unitProgressPercent, type ManagedTopology, type ProgrammingRoute,
} from "../programming/managed-programming";
import type { ProgrammingBatch, ProgrammingBatchUnit } from "../engineering/bundle-programming-api";
import { unitCycleTally } from "../programming/batch-statistics";
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
    // The Manager's Site outcome is the verdict (U9: it alone judges the
    // receipt); the projection only refuses a record of another Site.
    const judged = batchSiteVerdict(batch, unit, runOfUnit(batch, unit));
    if (judged.verdict === "PASS") return "success";
    if (judged.verdict === "FAIL") return "faulted";
    // An operator Stop / Stop Policy ends a Site as STOPPED, or PARTIAL when
    // it had settled Cycles: a stop, never an equipment error. A PARTIAL for
    // any other reason (SAFE_OFF not proven, Manager restart, shared control
    // failure) stays "error" on purpose; its PASS Cycles still count.
    const outcome: string | null = unit.outcome;
    if (outcome === "STOPPED"
        || ((outcome === "BLOCKED" || outcome === "PARTIAL")
          && /STOP_|STOP_POLICY|PPU_LATCHED/.test(unit.reason ?? ""))) return "stopped";
    if (unit.outcome != null) return "error";
    if (unit.attempts.some(item => item.outcome == null)) return "running";
    return batch.stop_requested ? "stopped" : "ready";
  };
  const sites: BatchSiteSnapshot[] = batch.units.map(unit => {
    const ppu = topology?.ppus.find(item => item.alias === unit.ppu_alias);
    const state = siteState(unit);
    const last = unit.attempts[unit.attempts.length - 1] ?? null;
    const current = runOfUnit(batch, unit);
    const judged = batchSiteVerdict(batch, unit, current);
    const passed = state === "success";
    // Batch Statistics v1: the same per-Site Cycle tally EMode uses.
    const tally = unitCycleTally(unit.cycle, judged.verdict);
    return {
      facility_id: ppu?.facilityId ?? "unassigned",
      ppu_id: unit.ppu_alias, site_id: unit.site_id,
      key: `${unit.ppu_alias}:${unit.site_id}`,
      state,
      // Manual Repeat: rounds are the Site's Cycles; a FAIL settles one too.
      current_round: unit.cycle && unit.cycle.planned > 1
        ? Math.min(unit.cycle.index, unit.cycle.planned) : unit.attempts.length ? 1 : 0,
      // Settled Cycles (PASS + FAIL); PASS, FAIL and Retry stay separate below.
      completed_rounds: tally.settled,
      pass_rounds: tally.pass,
      current_operation: null, current_job_id: last?.job_id ?? null,
      // Each Site's own progress: lanes run concurrently, current_run is one Site.
      progress_percent: passed ? 100 : unitProgressPercent(batch, unit) ?? 0,
      // Cumulative over every Cycle (Manager counter), never the current
      // Cycle's attempt list.
      total_attempts: unit.cycle?.attempts ?? unit.attempts.length,
      retry_count: unit.cycle?.retry_attempts ?? Math.max(0, unit.attempts.length - 1),
      final_failures: tally.fail,
      faulted_round: state === "faulted" ? 1 : null,
      faulted_operation: null,
      last_failure_source: state === "faulted" || state === "error" ? unit.failure_domain ?? "manager_programming_run" : null,
      error: state === "faulted" || state === "error"
        ? { message: judged.reason ?? unit.reason ?? (unit.outcome === "OUTCOME_UNKNOWN" ? "OUTCOME UNKNOWN; do not resubmit" : "Manager reports no PASS") }
        : null,
      operation_statistics: {},
    };
  });
  const site_counts: Record<ServerBatchSiteState, number> = {
    ready: 0, running: 0, success: 0, faulted: 0, error: 0, stopped: 0, cancelled: 0,
  };
  for (const site of sites) site_counts[site.state] += 1;
  const allSitesVerified = sites.length > 0 && site_counts.success === sites.length;
  const state: ServerBatchState = batch.outcome == null
    ? batch.stop_requested ? "stopping" : "running"
    : batch.outcome === "PASS" && allSitesVerified ? "success"
    : batch.outcome === "STOPPED" ? "cancelled"
    // PARTIAL is its own terminal state, whatever the Site count that passed.
    : batch.outcome === "PARTIAL" ? "partial"
    : site_counts.success > 0 && (site_counts.faulted > 0 || site_counts.error > 0)
      ? "partial"
    : "error";
  return {
    batch_id: batch.batch_id, state,
    // Forward Manager truth unchanged, including unknown historical timing.
    created_at: batch.created_at ?? "",
    started_at: batch.started_at ?? null, finished_at: batch.finished_at ?? null,
    operations: [...(batch.operations ?? [])],
    awaiting_continue: awaitingUnits(batch).map(unit => ({
      ppu_id: unit.ppu_alias, site_id: unit.site_id, continue_seq: unit.cycle!.continue_seq,
      detail: unitFailDetail(unit) ?? unitCycleLabel(unit) ?? "waiting for Continue",
    })),
    execution_policy: {
      repeat_count: batch.policy.repeat,
      replace_ic_before_next_cycle: batch.policy.replace_ic_before_next_cycle ?? true,
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
