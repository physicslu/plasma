// PMode Factory Console on the formal backend.
//
// The Factory UI keeps its Facility -> PPU -> Site model; this module feeds it
// from the Manager Registry / Fleet / Programming Routes and runs a production
// batch as a sequence of independent Manager programming runs, each with its
// own plan, Site lease, Resource check and Job Binding on its own PPU.
//
// Boundaries (deliberate):
// - one run at a time: neither parallel Sites on one PPU nor parallel PPUs
//   are physically qualified, so nothing here runs concurrently;
// - attempts = 1 per Site, never a retry, never a resubmission;
// - the batch lives in this Browser session. Reloading the page stops queuing
//   further Sites; an in-flight run finishes in the Manager. A durable,
//   Manager-owned production batch is NOT implemented here.

import type { EngineeringTargetCatalog, PPUStatus } from "../plasma-api";
import {
  describeBlocked,
  loadManagedTopology,
  loadPlatformAvailability,
  loadProgrammingRoutes,
  ManagedProgrammingBlocked,
  ManagedStartOutcomeUnknown,
  routesAvailability,
  runManagedProgramming,
  runProgressPercent,
  runVerdict,
  siteCapability,
  type ManagedPpu,
  type ManagedTopology,
  type ProgrammingRoute,
  type ProgrammingRun,
  type ProgrammingSource,
} from "../programming/managed-programming";
import type { ImageOperation } from "../engineering/bundle-programming-api";
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

export type ManagedBatchInput = {
  targets: Array<{ facilityId: string; alias: string; siteIds: number[] }>;
  icpn: string;
  operation: ImageOperation;
  source: ProgrammingSource;
  file: File;
  /** Stop queuing further Sites after this many failed / errored Sites. */
  failedSiteStopThreshold: number | null;
};

export type ManagedSiteRecord = {
  key: string;
  alias: string;
  ppuId: string | null;
  siteId: number;
  run: ProgrammingRun | null;
  /** Why the Site did not produce a run (blocked, stopped, cancelled). */
  note: string | null;
};

type SiteEntry = ManagedSiteRecord & { facilityId: string; state: ServerBatchSiteState; pass: boolean };

function siteKey(alias: string, siteId: number): string {
  return `${alias}:${siteId}`;
}

export class ManagedProductionBatch {
  readonly batchId = `console-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  private readonly createdAt = new Date().toISOString();
  private finishedAt: string | null = null;
  private stopRequested = false;
  private stopReason: string | null = null;
  private readonly entries: SiteEntry[];
  private readonly abort = new AbortController();

  constructor(private readonly input: ManagedBatchInput) {
    this.entries = input.targets.flatMap(target => [...target.siteIds].sort((a, b) => a - b).map(siteId => ({
      key: siteKey(target.alias, siteId),
      facilityId: target.facilityId,
      alias: target.alias,
      ppuId: null,
      siteId,
      run: null,
      note: null,
      state: "ready" as ServerBatchSiteState,
      pass: false,
    })));
  }

  /** Stop queuing. A run already submitted is never cancelled from the Console. */
  stop(): ServerBatchSnapshot {
    if (!this.finishedAt) {
      this.stopRequested = true;
      this.stopReason ??= "operator_abort";
    }
    return this.snapshot();
  }

  /** The Console view is going away: stop queuing and stop observing. */
  dispose(): void {
    if (!this.finishedAt) {
      this.stopRequested = true;
      this.stopReason ??= "console_closed";
    }
    this.abort.abort();
  }

  records(): ManagedSiteRecord[] {
    return this.entries.map(({ key, alias, ppuId, siteId, run, note }) => ({ key, alias, ppuId, siteId, run, note }));
  }

  private failures(): number {
    return this.entries.filter(entry => entry.state === "faulted" || entry.state === "error").length;
  }

  private close(entry: SiteEntry, state: ServerBatchSiteState, note: string | null): void {
    entry.state = state;
    entry.note = note;
  }

  private skipRemaining(filter: (entry: SiteEntry) => boolean, state: ServerBatchSiteState, note: string): void {
    for (const entry of this.entries) {
      if (entry.state === "ready" && filter(entry)) this.close(entry, state, note);
    }
  }

  /** Strictly sequential; resolves when no Site is left to start. */
  async execute(): Promise<void> {
    const preflight = new Map<string, { ppu: ManagedPpu | null; routes: ProgrammingRoute[] | null; block: string | null }>();
    for (const entry of this.entries) {
      if (entry.state !== "ready") continue;
      if (this.stopRequested) {
        this.skipRemaining(() => true, "cancelled",
          this.stopReason === "operator_abort" ? "Not started: the operator aborted the batch." : `Not started: ${this.stopReason}.`);
        break;
      }
      // Each PPU is admitted on its own, fresh observation: availability,
      // Platform admission and Routes of one PPU never stand in for another.
      let admitted = preflight.get(entry.alias);
      if (!admitted) {
        admitted = await this.admit(entry.alias);
        preflight.set(entry.alias, admitted);
      }
      entry.ppuId = admitted.ppu?.ppuId ?? null;
      if (admitted.block) {
        this.close(entry, "error", `BLOCKED before any Job: ${admitted.block}`);
        this.applyThreshold();
        continue;
      }
      const site = admitted.ppu?.sites.find(item => item.site_id === entry.siteId);
      const capability = site ? siteCapability(site, admitted.routes, this.input.icpn) : null;
      if (!capability?.programmable) {
        this.close(entry, "error", `BLOCKED before any Job: ${capability?.reason ?? "the Site is not reported by the PPU."}`);
        this.applyThreshold();
        continue;
      }
      entry.state = "running";
      try {
        const run = await runManagedProgramming({
          alias: entry.alias, siteId: entry.siteId, icpn: this.input.icpn,
          operation: this.input.operation, source: this.input.source, file: this.input.file,
        }, { onRun: next => { entry.run = next; } }, this.abort.signal);
        entry.run = run;
        const { verdict, reason } = runVerdict(run);
        if (verdict === "PASS") {
          entry.pass = true;
          this.close(entry, "success", null);
        } else if (verdict === "FAIL") {
          this.close(entry, "faulted", reason);
        } else if (verdict === "OUTCOME_UNKNOWN") {
          this.close(entry, "error", `OUTCOME UNKNOWN (${reason ?? "unknown"}); nothing was resubmitted`);
          this.latch(entry.alias);
        } else {
          this.close(entry, "error", `${verdict}: ${reason ?? "not completed"}`);
        }
      } catch (reason) {
        if (reason instanceof ManagedProgrammingBlocked) {
          this.close(entry, "error", `BLOCKED before any Job: ${describeBlocked(reason)}`);
        } else if (reason instanceof ManagedStartOutcomeUnknown) {
          this.close(entry, "error", `OUTCOME UNKNOWN: ${reason.message}`);
          this.latch(entry.alias);
        } else {
          this.close(entry, "error", reason instanceof Error ? reason.message : "Programming failed");
        }
      }
      this.applyThreshold();
    }
    this.finishedAt = new Date().toISOString();
  }

  private async admit(alias: string) {
    try {
      const [topology, platform, routes] = await Promise.all([
        loadManagedTopology(), loadPlatformAvailability(alias), loadProgrammingRoutes(alias),
      ]);
      const ppu = topology.ppus.find(item => item.alias === alias) ?? null;
      const block = !ppu ? "the PPU is not a commissioned Manager Registry entry"
        : !ppu.availability.ready ? `${ppu.availability.label} · ${ppu.availability.reason}`
        : !platform.ready ? `${platform.label} · ${platform.reason}`
        : !routesAvailability(routes).ready ? `ROUTES UNAVAILABLE · ${routes.error ?? ""}`
        : null;
      return { ppu, routes: routes.routes, block };
    } catch (reason) {
      return { ppu: null, routes: null, block: reason instanceof Error ? reason.message : "Manager unavailable" };
    }
  }

  /** An unknown outcome on one PPU stops every later Site of that PPU only. */
  private latch(alias: string): void {
    this.skipRemaining(entry => entry.alias === alias, "stopped",
      `Not started: PPU ${alias} has an unresolved OUTCOME UNKNOWN run. Reconcile and acknowledge it first.`);
  }

  private applyThreshold(): void {
    const threshold = this.input.failedSiteStopThreshold;
    if (threshold == null || this.stopRequested || this.failures() < threshold) return;
    this.stopRequested = true;
    this.stopReason = "failed_site_threshold";
    this.skipRemaining(() => true, "stopped", `Not started: Stop Policy reached ${threshold} failed Site(s).`);
  }

  private batchState(): ServerBatchState {
    if (!this.finishedAt) return this.stopRequested ? "stopping" : "running";
    const passed = this.entries.filter(entry => entry.pass).length;
    if (passed === this.entries.length) return "success";
    if (this.stopReason === "operator_abort") return "cancelled";
    return passed > 0 ? "partial" : "error";
  }

  snapshot(): ServerBatchSnapshot {
    const counts = { ready: 0, running: 0, success: 0, faulted: 0, error: 0, stopped: 0, cancelled: 0 };
    const sites: BatchSiteSnapshot[] = this.entries.map(entry => {
      counts[entry.state] += 1;
      const started = entry.run != null || entry.state === "running";
      const finalFailure = entry.state === "faulted" ? 1 : 0;
      return {
        facility_id: entry.facilityId,
        ppu_id: entry.alias,
        site_id: entry.siteId,
        key: entry.key,
        state: entry.state,
        current_round: started ? 1 : 0,
        completed_rounds: entry.pass ? 1 : 0,
        current_operation: null,
        current_job_id: entry.run?.job?.job_id ?? null,
        // PPU-reported progress only.
        progress_percent: entry.run ? runProgressPercent(entry.run) ?? 0 : 0,
        total_attempts: entry.run?.job_submission_count ?? 0,
        retry_count: 0,
        final_failures: finalFailure,
        faulted_round: finalFailure ? 1 : null,
        faulted_operation: null,
        last_failure_source: entry.state === "faulted" || entry.state === "error" ? "manager_programming_run" : null,
        error: entry.note && entry.state !== "success" ? { message: entry.note } : null,
        operation_statistics: {},
      };
    });
    const state = this.batchState();
    return {
      batch_id: this.batchId,
      state,
      created_at: this.createdAt,
      started_at: this.createdAt,
      finished_at: this.finishedAt,
      operations: [],
      execution_policy: {
        repeat_count: 1,
        site_retry_limit: 0,
        failed_site_stop_threshold: this.input.failedSiteStopThreshold,
      },
      target_device: null,
      asset: null,
      read: { scope: "main_flash" },
      cancel_requested: this.stopRequested,
      stop_reason: this.stopReason,
      error: null,
      faulted_site_count: this.failures(),
      site_counts: counts,
      operation_statistics: {},
      sites,
    };
  }
}
