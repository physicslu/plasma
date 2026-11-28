// Batch Statistics v1: ONE statistics contract for EMode and PMode.
//
// The Manager owns the counters (Batch `cycles` / `counts`, cumulative and
// journalled); this module only names and formats them. It is pure (no
// runtime imports) so both Consoles and the Host-only tests use the same code.
//
// Vocabulary - never mixed:
//   Site            a selected PPU Site (topology).
//   Cycle           one ordered E/P/V flow on one IC placement. PASS / FAIL
//                   settles it; OUTCOME_UNKNOWN / BLOCKED never do.
//   Job Attempt     one Manager-planned PPU Job attempt; Retries are extra
//                   attempts inside one Cycle and never add a Cycle.
//   Physical IC     declared by the operating mode, never identified:
//                   Replace IC each Cycle -> one IC per planned Cycle;
//                   Same-IC Debug        -> one IC per Site.

export type StatisticsMode = "REPLACE_IC" | "SAME_IC_DEBUG";

export type BatchStatistics = {
  mode: StatisticsMode;
  /**
   * Built-in Mock PPU Batch: simulated Cycles on Virtual Flash. Labelled MOCK
   * everywhere and never a production quantity, PASS/FAIL or YIELD (D4).
   */
  mock: boolean;
  sites: number;
  repeat: number;
  /** Declared by the mode (see above); never a physical identification. */
  physicalIc: number;
  plannedCycles: number;
  settledCycles: number;
  passCycles: number;
  failCycles: number;
  remainingCycles: number;
  /** Cumulative over every Cycle of every Site; null before a Batch exists. */
  jobAttempts: number | null;
  retryAttempts: number | null;
  /** Sites whose every planned Cycle settled; null before a Batch exists. */
  sitesCompleted: number | null;
};

export type CycleTally = { settled: number; pass: number; fail: number };

/**
 * One Site's settled Cycles: the Manager's Cycle counters (U9). Only a record
 * from a Manager older than Batch Statistics v1 (no counters) falls back to
 * its one final outcome.
 */
export function unitCycleTally(
  cycle: { planned: number; settled: number; pass: number; fail: number } | null | undefined,
  siteOutcome: string,
): CycleTally {
  if (cycle && typeof cycle.settled === "number") {
    return { settled: cycle.settled, pass: cycle.pass, fail: cycle.fail };
  }
  const pass = siteOutcome === "PASS" ? 1 : 0;
  const fail = siteOutcome === "FAIL" ? 1 : 0;
  return { settled: pass + fail, pass, fail };
}

export function batchStatistics(input: {
  mock?: boolean;
  sites: number;
  repeat: number;
  replaceIc: boolean;
  tally?: CycleTally | null;
  jobAttempts?: number | null;
  retryAttempts?: number | null;
  sitesCompleted?: number | null;
}): BatchStatistics {
  const sites = Math.max(0, input.sites);
  const repeat = Math.max(0, input.repeat);
  const planned = sites * repeat;
  const tally = input.tally ?? { settled: 0, pass: 0, fail: 0 };
  const mode: StatisticsMode = input.replaceIc ? "REPLACE_IC" : "SAME_IC_DEBUG";
  return {
    mode, mock: input.mock === true, sites, repeat,
    physicalIc: mode === "REPLACE_IC" ? planned : sites,
    plannedCycles: planned,
    settledCycles: tally.settled,
    passCycles: tally.pass,
    failCycles: tally.fail,
    remainingCycles: Math.max(0, planned - tally.settled),
    jobAttempts: input.jobAttempts ?? null,
    retryAttempts: input.retryAttempts ?? null,
    sitesCompleted: input.sitesCompleted ?? null,
  };
}

/**
 * Batch Statistics v1 of a PMode Site snapshot (Manager projection or the
 * Standalone runtime): the same definitions, summed per Site.
 */
export function snapshotStatistics(input: {
  mock?: boolean;
  sites: readonly {
    completed_rounds: number; pass_rounds?: number; final_failures: number;
    total_attempts: number; retry_count: number;
  }[];
  repeat: number;
  replaceIc: boolean;
}): BatchStatistics {
  const tally = { settled: 0, pass: 0, fail: 0 };
  let attempts = 0, retries = 0, completed = 0;
  for (const site of input.sites) {
    const pass = Math.max(0, site.pass_rounds ?? site.completed_rounds);
    const fail = Math.max(0, site.final_failures);
    tally.pass += pass;
    tally.fail += fail;
    tally.settled += pass + fail;
    attempts += Math.max(0, site.total_attempts);
    retries += Math.max(0, site.retry_count);
    if (pass + fail >= input.repeat) completed += 1;
  }
  return batchStatistics({
    mock: input.mock, sites: input.sites.length, repeat: input.repeat, replaceIc: input.replaceIc,
    tally, jobAttempts: attempts, retryAttempts: retries, sitesCompleted: completed,
  });
}

/** PASS / (PASS + FAIL); N/A without a settled Cycle, never 100%. */
export function passRate(pass: number, fail: number): string {
  const settled = pass + fail;
  return settled > 0 ? `${((pass / settled) * 100).toFixed(1)}%` : "N/A";
}

export type StatisticsKpi = {
  key: string;
  label: string;
  value: string | number;
  tone?: "neutral" | "info" | "pass" | "fail";
};

/**
 * Dashboard KPIs of either mode. Replace IC: IC-oriented, with manufacturing
 * YIELD. Same-IC Debug: Cycle-oriented, with CYCLE PASS RATE and no YIELD -
 * repeated PASS Cycles on one IC are never physical IC output.
 */
export function statisticsKpis(
  stats: BatchStatistics, batchTime: string, sitesKey = "sites",
): StatisticsKpi[] {
  const kpis = productionKpis(stats, batchTime, sitesKey);
  if (!stats.mock) return kpis;
  // D4: a Mock Batch keeps its numbers but never under production names, so
  // no MOCK count can be read (or copied) as IC output, PASS IC or YIELD.
  return [
    { key: "source", label: "SOURCE", value: "MOCK", tone: "info" },
    ...kpis.map(kpi => kpi.key === sitesKey || kpi.key === "batch-time"
      ? kpi : { ...kpi, key: `mock-${kpi.key}`, label: `MOCK ${kpi.label}` }),
  ];
}

function productionKpis(
  stats: BatchStatistics, batchTime: string, sitesKey: string,
): StatisticsKpi[] {
  const sites = { key: sitesKey, label: "SITES", value: stats.sites };
  const time = { key: "batch-time", label: "BATCH TIME", value: batchTime };
  if (stats.mode === "REPLACE_IC") {
    return [
      sites,
      { key: "total-ic", label: "TOTAL IC", value: stats.plannedCycles },
      { key: "processed-ic", label: "PROCESSED IC", value: stats.settledCycles },
      { key: "pass", label: "PASS IC", value: stats.passCycles, tone: "pass" },
      { key: "fail", label: "FAIL IC", value: stats.failCycles, tone: "fail" },
      { key: "yield", label: "YIELD", value: passRate(stats.passCycles, stats.failCycles), tone: "info" },
      time,
    ];
  }
  return [
    sites,
    { key: "physical-ic", label: "PHYSICAL IC", value: stats.physicalIc },
    { key: "total-cycles", label: "TOTAL CYCLES", value: stats.plannedCycles },
    { key: "settled-cycles", label: "SETTLED CYCLES", value: stats.settledCycles },
    { key: "pass", label: "PASS CYCLES", value: stats.passCycles, tone: "pass" },
    { key: "fail", label: "FAIL CYCLES", value: stats.failCycles, tone: "fail" },
    { key: "cycle-pass-rate", label: "CYCLE PASS RATE", value: passRate(stats.passCycles, stats.failCycles), tone: "info" },
    time,
  ];
}

/** The Batch Summary meta line: attempts and progress, in both modes. */
export function statisticsMeta(stats: BatchStatistics): string {
  const parts = [
    ...(stats.mock ? ["MOCK PPU · not production"] : []),
    `${stats.sites} Site${stats.sites === 1 ? "" : "s"}`,
    stats.mode === "REPLACE_IC" ? "Replace IC each Cycle" : "Same-IC Debug",
    `Cycles ${stats.settledCycles}/${stats.plannedCycles} settled · ${stats.remainingCycles} remaining`,
  ];
  if (stats.sitesCompleted != null) parts.push(`Sites completed ${stats.sitesCompleted}/${stats.sites}`);
  if (stats.jobAttempts != null) parts.push(`Job Attempts ${stats.jobAttempts}`);
  if (stats.retryAttempts != null) parts.push(`Retry ${stats.retryAttempts}`);
  return parts.join(" · ");
}

/** The `[STATISTICS]` Log line: the same numbers as the Dashboard. */
export function statisticsLogLine(stats: BatchStatistics): string {
  const rate = passRate(stats.passCycles, stats.failCycles);
  const ic = stats.mode === "REPLACE_IC"
    ? `IC ${stats.physicalIc} (operator-replaced, not identified) · YIELD ${rate}`
    : `Physical IC ${stats.physicalIc} (same IC per Site) · Cycle PASS rate ${rate} · no YIELD`;
  return `[STATISTICS] ${stats.mock ? "MOCK (simulated, not production) · " : ""}${
    stats.mode === "REPLACE_IC" ? "Replace IC" : "Same-IC Debug"} · Sites ${stats.sites}`
    + `${stats.sitesCompleted != null ? ` (completed ${stats.sitesCompleted})` : ""}`
    + ` · Cycles PASS ${stats.passCycles} · FAIL ${stats.failCycles} · settled ${stats.settledCycles}/${stats.plannedCycles}`
    + ` · remaining ${stats.remainingCycles} · Job Attempts ${stats.jobAttempts ?? "—"} · Retry ${stats.retryAttempts ?? "—"}`
    + ` · ${ic}`;
}

// ------------------------------------------------------------ Cycle History

/** One record of the Manager's Cycle History (`/batches/{id}/cycles`). */
export type CycleHistoryAttempt = {
  attempt: number;
  cycle_index?: number;
  run_id: string | null;
  job_id: string | null;
  outcome: string | null;
  reason: string | null;
  safe_off: boolean | null;
  safe_off_state?: SafeOffState | null;
  retry?: { decision: string; reason: string } | null;
};

/**
 * The Site's end state as the Manager receipt states it, kept apart from the
 * programming result: VERIFIED (SAFE_OFF observed), NOT_TOUCHED (a trusted
 * refusal before any hardware access) or NOT_VERIFIED (nothing proves it).
 */
export type SafeOffState = "VERIFIED" | "NOT_TOUCHED" | "NOT_VERIFIED";

/** The Manager reason of a Job the Site Worker refused before any hardware access. */
export const SITE_DENIED_BEFORE_HARDWARE = "SITE_DENIED_BEFORE_HARDWARE";

/**
 * SAFE_OFF as every Console Log and view writes it. Only the Manager's own
 * statement is quoted: never inferred from a PASS, a reason or a code.
 */
export function safeOffLabel(
  state: SafeOffState | string | null | undefined,
  safeOff: boolean | null | undefined,
  finished = true,
): string {
  if (state === "NOT_TOUCHED") return "N/A · hardware not touched";
  if (safeOff === true || state === "VERIFIED") return "VERIFIED";
  return finished ? "NOT VERIFIED" : "—";
}

export type CycleHistoryRecord = {
  seq: number;
  type: "cycle" | "continue" | "blocked_dispatch" | string;
  ppu_alias: string;
  site_id: number;
  cycle_index?: number;
  cycle_id?: string | null;
  outcome?: string;
  reason?: string | null;
  attempts?: CycleHistoryAttempt[];
  receipt?: {
    run_id: string | null; job_id: string | null; job_state: string | null;
    safe_off: boolean | null; job_binding_confirmed: boolean;
    safe_off_state?: SafeOffState | null;
    site_safety?: { class: string; code: string } | null;
    readback_sha256?: string | null; job_binding_sha256?: string | null;
    resource_set_sha256?: string | null; elapsed_ms?: number | null;
  } | null;
  continue_seq?: number;
  after_cycle_index?: number | null;
  wait_reason?: string | null;
};

export type CycleHistoryPage = {
  total: number;
  offset: number;
  next_offset: number;
  records: CycleHistoryRecord[];
};


/**
 * Log lines of one History record. Evidence is quoted from the Manager
 * record (Run / Job / SAFE_OFF / Readback / Job Binding), never inferred.
 */
export function cycleHistoryLogLines(
  record: CycleHistoryRecord, repeat: number, siteLabel: string,
  /** Which attempts get their own line; by default only Retries. */
  attemptLine: (attempt: CycleHistoryAttempt) => boolean = attempt => attempt.attempt > 1 || attempt.retry != null,
): { text: string; failed: boolean }[] {
  if (record.type === "continue") {
    return [{ text: `[CONTINUE] ${siteLabel} · after Cycle ${record.after_cycle_index ?? "—"} · ${record.wait_reason ?? "—"} · seq ${record.continue_seq ?? "—"}`, failed: false }];
  }
  if (record.type === "blocked_dispatch" && record.reason === SITE_DENIED_BEFORE_HARDWARE) {
    // A submitted Job the Site Worker refused before any hardware access:
    // BLOCKED, not a FAIL, and no Cycle result. It waits for the operator.
    const receipt = record.receipt ?? null;
    return [{ text: `[BLOCKED] Cycle ${record.cycle_index ?? "—"}/${repeat} ${siteLabel} · denied before hardware`
      + `${receipt?.site_safety?.code ? ` · ${receipt.site_safety.code}` : ""} · Run ${receipt?.run_id ?? "—"} · Job ${receipt?.job_id ?? "—"}`
      + ` · SAFE_OFF ${safeOffLabel(receipt?.safe_off_state, receipt?.safe_off)} · not counted as a Cycle · press Start to re-run admission`,
    failed: true }];
  }
  if (record.type === "blocked_dispatch") {
    return [{ text: `[CYCLE ${record.cycle_index ?? "—"}/${repeat}] ${siteLabel} · NEXT CYCLE BLOCKED · ${record.reason ?? "—"} · nothing submitted`, failed: true }];
  }
  if (record.type !== "cycle") return [];
  const receipt = record.receipt ?? null;
  const attempts = record.attempts ?? [];
  const failed = record.outcome !== "PASS";
  const lines = attempts.filter(attemptLine).map(attempt => ({
    text: `[ATTEMPT ${attempt.attempt}] Cycle ${record.cycle_index}/${repeat} ${siteLabel} · ${attempt.outcome ?? "—"}${attempt.reason ? ` · ${attempt.reason}` : ""} · Run ${attempt.run_id ?? "—"} · Job ${attempt.job_id ?? "—"} · SAFE_OFF ${safeOffLabel(attempt.safe_off_state, attempt.safe_off)}${attempt.retry ? ` · ${attempt.retry.decision === "RETRY" ? "RETRY" : "NO RETRY"} (${attempt.retry.reason})` : ""}`,
    failed: attempt.outcome !== "PASS",
  }));
  lines.push({
    text: `[CYCLE ${record.cycle_index}/${repeat}] ${siteLabel} · ${record.outcome ?? "—"}${record.reason && failed ? ` · ${record.reason}` : ""} · Run ${receipt?.run_id ?? "—"} · Job ${receipt?.job_id ?? "—"} · SAFE_OFF ${safeOffLabel(receipt?.safe_off_state, receipt?.safe_off)} · attempts ${attempts.length}`,
    failed,
  });
  lines.push({
    text: `[RECEIPT] Cycle ${record.cycle_index}/${repeat} ${siteLabel} · Job ${receipt?.job_id ?? "—"} · state ${receipt?.job_state ?? "—"} · Readback SHA256 ${receipt?.readback_sha256 ?? "—"} · Job Binding ${receipt?.job_binding_confirmed ? "confirmed" : "NOT confirmed"} ${receipt?.job_binding_sha256 ?? "—"}`,
    failed,
  });
  return lines;
}

/**
 * Incremental reader of one Batch's Cycle History. It keeps a cursor (the
 * Manager's `seq`) and never re-reads what it already has; a record is
 * delivered once, in order, however often `sync` runs. A new reader for the
 * same Batch (browser refresh) starts from 0 and rebuilds the same history.
 */
export function cycleHistoryReader(
  load: (offset: number, limit: number) => Promise<CycleHistoryPage>,
  deliver: (record: CycleHistoryRecord) => void,
  limit = 200,
) {
  let cursor = 0;
  // At most one drain runs and at most one waits behind it, so a sync that
  // arrives mid-read (e.g. the terminal poll) is never answered by a read
  // that started before it.
  let chain: Promise<void> = Promise.resolve();
  let waiting: Promise<void> | null = null;
  async function drain(): Promise<void> {
    for (;;) {
      const page = await load(cursor, limit);
      for (const record of page.records) {
        if (record.seq < cursor) continue;   // never twice
        deliver(record);
      }
      if (page.next_offset <= cursor) return;
      cursor = page.next_offset;
      if (cursor >= page.total) return;
    }
  }
  return {
    /** Read every record appended since the last sync. Serialised. */
    sync(): Promise<void> {
      if (waiting) return waiting;
      const next = chain.then(() => { waiting = null; return drain(); });
      waiting = next;
      chain = next.catch(() => undefined);
      return next;
    },
    get cursor() { return cursor; },
  };
}
