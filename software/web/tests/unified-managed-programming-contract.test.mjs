import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// Unified Programming Integration (Gate 1, 2026-11-11): EMode and PMode share
// one formal backend. Source contracts only; behaviour is covered by the
// Playwright and Manager Host-only suites.

const root = new URL("../", import.meta.url);
const read = path => readFile(new URL(path, root), "utf8");

const core = await read("app/programming/managed-programming.ts");
const emode = await read("app/engineering/managed-programming-workspace.tsx");
const page = await read("app/engineering/page.tsx");
const api = await read("app/engineering/bundle-programming-api.ts");
const bff = await read("app/api/manager/bootstrap-bff.ts");
const panel = await read("app/operator-ui/programming-job-panel.tsx");
const selector = await read("app/operator-ui/programming-source-selector.tsx");
const view = await read("app/operator-ui/programming-run-view.tsx");

test("formal Console routes EMode Programming to the Manager backend, never the Mock runtime", () => {
  // U10: the Console is Manager-managed only; there is no standalone router.
  assert.match(page, /import ManagedProgrammingWorkspace from "\.\/managed-programming-workspace";/);
  assert.match(page, /active === "programming" \? \(\s*<ManagedProgrammingWorkspace \/>/);
  assert.doesNotMatch(page, /StandaloneProgrammingWorkspace|programming-workspace-v2"|apiMode/);
});

test("managed Programming has no direct PPU Gateway client, Job router or Batch runtime", () => {
  for (const source of [core, emode, selector, view]) {
    assert.doesNotMatch(source, /from "\.\.\/plasma-api"|from "\.\/plasma-api"/);
    assert.doesNotMatch(source, /server-batch|engineering-server-batch|gateway-settings-api/);
    assert.doesNotMatch(source, /\/api\/jobs|\/api\/engineering\/targets|\/api\/manager\/ppu\/|:18080|:18081/);
    assert.doesNotMatch(source, /startJob|cancelJob|createServerBatch|apiBase/);
  }
  assert.match(core, /getManagerRegistry\(\)/);
  assert.match(core, /getManagerFleet\(\)/);
  assert.match(core, /getProgrammingRoutes\(alias\)/);
});

test("Manager Alias routes; the device PPU ID is display identity only", () => {
  assert.match(core, /alias: entry\.alias,\s*ppuId: view\?\.identity\.ppu_id \?\? null/);
  assert.match(core, /entry\.lifecycle !== "commissioned"\) continue/);
  assert.match(emode, /Manager Alias: \{ppu\?\.alias \?\? "—"\}/);
  assert.match(emode, /PPU ID: \{ppu\?\.ppuId \?\? "—"\}/);
});

test("ONLINE and Programming capability are judged separately with exact reasons", () => {
  assert.match(core, /online: view\?\.transport_state === "reachable" && view\.observation\.state === "current"/);
  for (const label of ["PPU OFFLINE", "PPU DEGRADED", "NOT AUTHORIZED", "RECOVERY REQUIRED", "RUNTIME NOT ACTIVE"]) {
    assert.match(core, new RegExp(label));
  }
  assert.match(core, /nothing is enrolled or rotated automatically/);
  assert.doesNotMatch(core + emode, /enrollManagerPpuBootstrap|recovery_action|\/enrollment|\/recovery/);
});

test("one Start: lock -> plan -> exactly one start -> observe; no retry of any write", () => {
  // U2: programming and Read Memory each submit one Manager Batch; the
  // Manager owns every Site plan/Job. The Browser never plans or starts a run.
  assert.doesNotMatch(core, /planProgramming\(|startProgramming\(/);
  assert.match(core, /export async function runManagedRead\(/);
  // Both modes use the canonical Manager Batch entry point.
  assert.equal((emode.match(/runManagedBatch\(/g) ?? []).length, 1);
  assert.doesNotMatch(emode, /planProgramming\(|startProgramming\(/);
  // The only loops are the read-only Batch status polls (programming, Read).
  assert.equal((core.match(/\bwhile \(/g) ?? []).length, 2);
  assert.equal((core.match(/while \(batch\.outcome == null\)/g) ?? []).length, 2);
  assert.doesNotMatch(core, /for \(let (retry|attempt)/);
  assert.match(core, /MANAGED_JOB_POLICY = Object\.freeze\(\{ attempts: 1, auto_retry: "DISABLED" as const \}\)/);
  assert.match(core, /status != null && status >= 400 && status < 500/);
  assert.match(core, /throw new ManagedStartOutcomeUnknown\(/);
});

test("Start is double-click safe and the manual Prepare step is gone from EMode", () => {
  assert.match(emode, /if \(startLock\.current \|\| !readiness\.ready/);
  assert.match(emode, /startLock\.current = true;\s*const policy = \{ retryLimit, stopPolicy, repeat: repeatValue, replaceIc \};\s*const started = \[\.\.\.siteIds\];\s*const request: ManagedBatchRequest =/);
  // Manual Repeat: START pressed while Sites wait is their Continue, nothing else.
  assert.match(emode, /if \(awaitingUnits\(batch\)\.length\) \{\s*await continueSites\(\);\s*return;\s*\}/);
  assert.doesNotMatch(emode, /Prepare Programming|Confirm programming|confirmedPlanId/);
  assert.match(emode, /: "START PROGRAMMING"\}/);
});

test("EMode Operations are E / P / V checkboxes sent as one operations list; Read is a separate Job", () => {
  // Three basic Operations, default all checked, one programming Job.
  assert.match(emode, /const ALL_OPERATIONS: Record<SequenceOperation, boolean> = \{ erase: true, program: true, verify: true \}/);
  assert.match(emode, /operations=\{SEQUENCE_OPERATIONS\.map\(/);
  assert.match(emode, /normalizeOperations\(selectedOperations\)/);
  assert.doesNotMatch(emode, /flash_cycle/);
  assert.doesNotMatch(emode, /code: "R"|label: "Read"/);
  // READ: one button per LIVE SITE STATUS row, its own Job, through the Manager only.
  assert.doesNotMatch(emode, /READ MEMORY|aria-label="Read Memory|data-testid="read-memory/);
  assert.match(emode, /aria-label=\{`Read SITE \$\{site\.site_id\} Flash`\}/);
  // The whole Flash of the Programming Route; the destination is chosen before any Job.
  assert.match(emode, /const address = route\.flash_base;\s*const length = route\.flash_size;/);
  assert.match(emode, /showSaveFilePicker/);
  // A lost Start answer (READ or Programming) holds the PPU until the operator
  // reconciles it; it is never a FAIL, never resent and never auto-acknowledged.
  assert.match(emode, /if \(unknown\) holdStart\(alias, \[id\], "READ", reason\.message, reason\.identity\);/);
  assert.match(emode, /holdStart\(context\.alias, context\.siteIds, "PROGRAMMING", reason\.message, reason\.identity\);/);
  assert.match(emode, /if \(startHold\) \{\s*return notReady\("OUTCOME UNKNOWN",/);
  assert.match(emode, /window\.localStorage\.setItem\(START_HOLD_KEY/);
  // The hold is released on the Manager's reconciliation of that exact start,
  // never on a Site being idle alone, and never from an effect.
  assert.doesNotMatch(emode, /releaseStartHold/);
  assert.doesNotMatch(emode, /useEffect\([^)]*reconcileStartHold/);
  const reconcile = emode.slice(emode.indexOf("async function reconcileStartHold"), emode.indexOf("async function acknowledge()"));
  // Reconciliation is Manager-owned: it names the start, never a PPU (PR-C).
  assert.match(reconcile, /getStartReconciliation\(hold\.startId\)/);
  assert.doesNotMatch(reconcile, /getStartReconciliation\(hold\.alias|voidStart\(hold\.alias/);
  assert.match(reconcile, /decideStartReconciliation\(held, answer\)/);
  assert.ok(reconcile.indexOf("decision.action !== \"RELEASE\"") < reconcile.indexOf("loadManagedTopology()"),
    "the Fleet idle check only follows a Manager answer that allows release");
  assert.ok(reconcile.indexOf("loadManagedTopology()") < reconcile.indexOf("delete next[hold.alias]"));
  // The two writes are explicit operator steps, sent only when the fresh answer asks for them.
  assert.match(reconcile, /step === "ACKNOWLEDGE_RUN" && decision\.action === "ACKNOWLEDGE_RUN"/);
  assert.match(reconcile, /step === "VOID" && decision\.action === "VOID"/);
  assert.match(reconcile, /if \(!hold\.startId\) \{[\s\S]*?return;/);
  // Core: a lost Start carries the Manager-issued start ID; a Batch gets one first.
  // The Manager issues the start under no PPU; the alias the Console passes
  // is the BFF's capability check and never reaches the Manager record.
  assert.match(core, /startId = await issueBatchStart\(request\.alias\);[\s\S]*startProgrammingBatch\(input, startId\)/);
  assert.doesNotMatch(core, /new ManagedStartOutcomeUnknown\("batch"/);
  assert.match(core, /export function decideStartReconciliation\(/);
  // A Batch start names no PPU until a Target Set is admitted with it; a
  // DIFFERENT PPU is still a mismatch.
  assert.match(core, /answer\.start_id !== hold\.startId\s*\|\| \(answer\.ppu_alias != null && answer\.ppu_alias !== hold\.alias\)/);
  assert.match(core, /hold\.jobBindingSha256 != null && identity\.job_binding_sha256 !== hold\.jobBindingSha256/);
  // The Browser reaches the canonical start resource through the BFF
  // allowlist only, and the retired alias-scoped one is not in it (PR-C).
  assert.match(bff, /PROGRAMMING_POST_RESOURCES = \[[\s\S]*\/\^starts\$\/[\s\S]*starts\/\$\{RUN_ID\}\/void\$/);
  assert.match(bff, /PROGRAMMING_GET_RESOURCES = \[[\s\S]*starts\/\$\{RUN_ID\}\$/);
  assert.doesNotMatch(bff, /programming\\\/batches|programming\/batches\/\$\{RUN_ID\}|programming\\\/starts/);
  assert.match(emode, /name === "AbortError"[\s\S]{0,200}no Job was submitted[\s\S]{0,80}return;/);
  assert.match(emode, /runManagedRead\(/);
  assert.match(core, /operation: "read",/);
  assert.doesNotMatch(emode, /\/api\/jobs|gateway-api|getReadOutput\(/);
  // The Erase + Verify refusal is explicit, never a silent different action.
  assert.match(emode, /Erase \+ Verify without Program is not supported/);
});

test("EMode sections are numbered 1 / 2 (2-1 … 2-4) / 3 / 4 and no current feature is removed for it", async () => {
  const logPanel = await read("app/engineering/engineering-log-panel.tsx");
  const jobControlsCss = await read("app/operator-ui/programming-job-controls.css");
  const sourceSelectorCss = await read("app/operator-ui/programming-source-selector.css");
  const icPickerCss = await read("app/devices/ic-picker-field.css");
  assert.match(emode, /<OperatorPanelHeader\s+number=\{1\}\s+title="SYSTEM SETUP & TARGETING"/);
  // One number per title: the shared header renders "1." … "4."; no title carries one.
  assert.match(emode, /title="PROGRAMMING JOB"/);
  assert.match(panel, /export const PROGRAMMING_JOB_SECTION = 2;/);
  assert.match(panel, /number=\{PROGRAMMING_JOB_SECTION\}/);
  // One source of the sub-item numbering: 2-1 … 2-4 in EMode and PMode alike.
  assert.match(panel, /const fieldNumber = \(index: number\) => `\$\{PROGRAMMING_JOB_SECTION\}-\$\{index\}\.`/);
  assert.doesNotMatch(panel, /mode === "engineering" \? `2-/);
  for (const [index, label] of [[1, "targetLabel"], [2, "imageLabel"], [3, "operationsLabel"], [4, "policyLabel"]]) {
    assert.ok(panel.includes(`<strong>{fieldNumber(${index})} {${label}}</strong>`));
  }
  assert.match(emode, /targetLabel="Target IC"/);
  assert.match(emode, /imageLabel="Programming Source"/);
  assert.match(emode, /operationsLabel="Operations"/);
  assert.match(emode, /policyLabel="Batch Policy"/);
  assert.match(emode, /<OperatorPanelHeader\s+number=\{3\}\s+title="LIVE SITE STATUS"/);
  assert.match(logPanel, /number=\{4\}/);
  // Compact aligned controls of the numbered Programming Job.
  assert.match(panel, /className="programmingJobImageContent"/);
  assert.match(jobControlsCss, /@container engineering-programming \(max-width: 700px\)/);
  assert.match(sourceSelectorCss, /width:\s*fit-content/);
  assert.match(sourceSelectorCss, /min-height:\s*var\(--operator-control-min-height\)/);
  // The IC picker keeps its own EMode size (40px / 12px); the Programming Job never shrinks it.
  assert.doesNotMatch(icPickerCss, /\.programmingJobGrid \.icPickerInput/);
  // Field padding and row gap stay the shared PMode / EMode values.
  assert.doesNotMatch(jobControlsCss, /data-programming-job-fields="engineering"\] \.programmingJobField\s*\{[^}]*(padding|row-gap)/);
  // The numbering never costs a feature: per-Site READ + Save File Picker,
  // Retry / Stop Policy and Start Outcome Reconciliation stay.
  assert.match(emode, /showSaveFilePicker/);
  assert.match(emode, /async function reconcileStartHold/);
  assert.match(emode, /async function stopQueuing/);
  assert.match(emode, /const ALL_OPERATIONS: Record<SequenceOperation, boolean> = \{ erase: true, program: true, verify: true \}/);
});

test("the standing PROGRAMMING PLAN panel is gone; the Backend plan still runs and is logged", () => {
  assert.doesNotMatch(emode, /PROGRAMMING PLAN|managed-plan|aria-label="Programming plan"/);
  assert.match(core, /batch = await startProgrammingBatch\(\{[\s\S]{0,200}operation: "read",/);
  assert.match(core, /batch = await startProgrammingBatch\(input, startId\)/);
  assert.match(emode, /\[PLAN\] \$\{planned\.plan_id\} · Route/);
  assert.match(emode, /Resource SHA256 \$\{planned\.resource\.resource_set_sha256\} · Job Binding SHA256/);
});

test("EMode Batch Policy: Repeat / Retry / Stop Policy are decided by the Manager, never the Browser", () => {
  // Manual Repeat (WP-02): an editable Cycle count and the replace-IC choice
  // (default Yes) are inputs only; the Browser never loops over Cycles.
  assert.match(emode, /repeatValue: repeatCount,\s*repeatDisabled: active,/);
  assert.match(emode, /const \[replaceIc, setReplaceIc\] = useState\(true\);/);
  assert.match(emode, /repeatParsed <= MAX_REPEAT/);
  assert.match(core, /export async function continueAwaitingSites\(/);
  assert.equal((core.match(/continueProgrammingBatch\(/g) ?? []).length, 1);
  assert.match(api, /continue_seq: unit\.continue_seq/);
  assert.doesNotMatch(api, /actor/);
  // One Batch request; the Browser has no retry loop and no plan / start of its own.
  assert.equal((emode.match(/runManagedBatch\(/g) ?? []).length, 1);
  // One Batch request each for programming and Read Memory (U2).
  assert.equal((core.match(/startProgrammingBatch\(/g) ?? []).length, 2);
  assert.doesNotMatch(emode, /runManagedProgramming\(|planProgramming\(|startProgramming\(/);
  assert.doesNotMatch(emode, /for \(let (retry|attempt)|while \(/);
  assert.match(emode, /retryMax: MAX_RETRY_LIMIT/);
  assert.match(emode, /\{ kind: "failed_sites", threshold \}/);
  // The stop control is "stop queuing": it is never labelled or wired as an abort / cancel.
  assert.match(emode, /"STOP QUEUING"/);
  assert.doesNotMatch(emode, /abortLabel="ABORT"|cancelJob|\/cancel/);
  assert.match(emode, /stopProgrammingBatch\(/);
  assert.doesNotMatch(emode, /siteRetryLimit|site_retry_limit|repeat_count/);
  // PASS is counted once per Batch, from the Batch verdict.
  assert.match(emode, /const verdict = batch \? batchVerdict\(batch\)\.verdict : null;/);
});

test("Image is the default Source; switching clears file, plan and validation state only", () => {
  assert.match(emode, /useState<ProgrammingSource>\("image"\)/);
  assert.match(emode, /function changeSource\(next: ProgrammingSource\) \{\s*if \(active \|\| next === source\) return;\s*setSource\(next\);\s*setFile\(null\);\s*clearRunState\(\);/);
  assert.match(selector, /role="radiogroup"/);
  assert.match(selector, /\{ value: "image", label: "Programming Image" \},\s*\{ value: "bundle", label: "Bundle" \}/);
  assert.match(panel, /imageInputRef\.current\.value = "";\s*source\.onChange\(next\);/);
});

test("Bundle source sends the user's bytes unchanged; the Browser builds nothing", () => {
  assert.match(api, /bundle_base64: bytesToBase64\(input\.bundle\)/);
  assert.match(api, /image_base64: bytesToBase64\(input\.image\)/);
  assert.doesNotMatch(core + emode + api, /manifest\.json|canonical_zip|owner_authorization/);
});

test("U9: the run verdict is the Manager's; the Browser keeps no second receipt check", () => {
  // The Manager accepts a PASS only with its own full receipt proof.
  assert.match(core, /export function runVerdict\(run: ProgrammingRun\): \{ verdict: RunVerdict; reason: string \| null \} \{\s*if \(run\.outcome == null\) return \{ verdict: "RUNNING", reason: null \};\s*return \{ verdict: run\.outcome, reason: run\.reason \};\s*\}/);
  for (const reason of ["RECEIPT_MISSING", "JOB_SUBMISSION_COUNT_NOT_ONE", "JOB_BINDING_NOT_CONFIRMED",
    "RESOURCE_SET_NOT_CONFIRMED", "READBACK_SHA256_MISMATCH", "LAST_ATTEMPT_NOT_PASS", "RUN_DOES_NOT_MATCH_BATCH"]) {
    assert.doesNotMatch(core, new RegExp(reason));
  }
  // Progress is the PPU-reported value or nothing: no synthetic percentage.
  assert.match(core, /const value = run\.job\?\.progress_percent;/);
  assert.doesNotMatch(core + emode, /Math\.random|fakeProgress|simulat/i);
});

test("the Source label is one product name everywhere and a Mock result is marked as such", async () => {
  const platform = await read("app/engineering/bundle-programming.tsx");
  assert.match(selector, /label: "Programming Image"/);
  assert.doesNotMatch(selector, /label: "Image"/);
  assert.match(platform, /<span>Programming Image \(\.bin\)<\/span>/);
  assert.match(view, /MOCK RESULT · Site interface mock · not hardware evidence/);
  assert.match(view, /data-run-evidence=\{executionInterface === "mock" \? "mock" : "ppu"\}/);
});

test("receipt keeps full Job ID and SHA256 identities for diagnosis", () => {
  for (const id of ["receipt-job", "receipt-readback", "receipt-resource-sha", "receipt-binding-sha", "receipt-safe-off"]) {
    assert.match(view, new RegExp(`data-testid="${id}"`));
  }
  assert.doesNotMatch(view, /\.slice\(0, 12\)/);
});

// ---------------------------------------------------------------- PMode
const factory = await read("app/fleet/factory-console-v2.tsx");
const factoryBackend = await read("app/fleet/managed-factory-backend.ts");

test("PMode discovers Manager Registry/Fleet and requires live Site interface admission", () => {
  // U10: PMode is Manager-managed only; there is no apiMode branch.
  assert.doesNotMatch(factory, /apiMode|const managed = /);
  assert.match(factory, /const nextCatalog: EngineeringTargetCatalog = managedFactoryCatalog\(restoredTopology\);/);
  assert.match(factoryBackend, /siteCapability\(site, routes, icpn\)/);
  assert.match(factory, /const blocker = managedBatchBlocker\(managedTopology, managedRoutes\.routes, icpn,/);
  assert.doesNotMatch(factoryBackend, /site_count[^\n]*programmable|siteCount[^\n]*programmable/);
});

test("PR-D PMode submits ONE canonical Manager Target Set instead of a Browser job queue", () => {
  assert.match(factory, /await runManagedBatch\(request, \{/);
  assert.match(factory, /const targets = batchTargets\.map\(active => \(\{/);
  assert.match(factory, /ppu_alias: active\.target\.ppu_id, site_ids: \[\.\.\.active\.siteIds\]/);
  assert.match(core, /request\.targets \? \{ targets: request\.targets \} : \{\}/);
  assert.match(api, /targets: input\.targets/);
  assert.doesNotMatch(factoryBackend, /class ManagedProductionBatch|runManagedProgramming\(/);
  assert.doesNotMatch(factory, /new ManagedProductionBatch/);
});

test("PR-D Manager controls Retry/Stop and the Browser restores durable Batch by ID", () => {
  assert.match(factory, /retryValue !== null && retryValue <= 5/);
  assert.match(factory, /repeatValue: repeatCount,/);
  assert.match(factory, /repeatValue !== null && repeatValue <= 10_000\s*&& retryValue !== null && retryValue <= 5/);
  assert.match(factory, /if \(waitingSites\.length\) \{\s*await continueManagedSites\(\);/);
  // P0: START continues ONLY the Sites marked "IC replaced" for their current
  // pause (or the single Site of a one-Site Session), never every waiting Site.
  assert.match(core, /if \(sessionSites === 1\) return \[\.\.\.waiting\];\s*return waiting\.filter\(site => marked\.has\(continueMarkKey\(site\.alias, site\.siteId, site\.continueSeq\)\)\);/);
  assert.match(core, /return `\$\{alias\}:\$\{siteId\}:\$\{continueSeq\}`;/);
  assert.match(factory, /const chosen = continuingSites;/);
  assert.match(emode, /continueAwaitingSites\(batch, replacedMarks\)/);
  assert.doesNotMatch(factory, /for \(const site of waiting\)/);
  assert.match(factory, /retryValue: siteRetryLimit/);
  assert.match(factory, /await stopProgrammingBatch\(activeBatchId\)/);
  assert.match(factory, /let managedId = readManagedBatch\(\);/);
  assert.match(factory, /getStartReconciliation\(pendingStart\)/);
  assert.match(factory, /await getProgrammingBatch\(batchId\)/);
  assert.match(factory, /writeManagedStart\(startId\)/);
  assert.match(factory, /reason instanceof ManagedStartOutcomeUnknown/);
  assert.match(factoryBackend, /export function managedProductionSnapshot/);
  assert.match(factoryBackend, /batch\.units\.map\(unit =>/);
  assert.doesNotMatch(factoryBackend, /startProgrammingBatch|runManagedProgramming|\/api\/jobs/);
});

test("PMode retains Factory UI and no Mock is presented as HIL acceptance", () => {
  assert.match(factory, /useState<ProgrammingSource>\("image"\)/);
  assert.match(factory, /source=\{\{ value: programmingSource, disabled: batchRunning, onChange: changeProgrammingSource \}\}/);
  assert.match(factory, /repeatDisabled: batchRunning,/);
  assert.match(factoryBackend, /readyLabel: "MANAGER BATCH READY"/);
  assert.doesNotMatch(factory, /data-testid="managed-production-mode"/);
  assert.match(factory, /MOCK RESULT/);
  // P1: a Repeat Site's rounds are its settled Cycles (PASS + FAIL); PASS,
  // FAIL and Retry stay separate, and same-IC Debug never reads as IC output.
  // Batch Statistics v1: the same per-Site Cycle tally as EMode, and the
  // cumulative Manager attempt counters - never the current attempt list.
  assert.match(factoryBackend, /const tally = unitCycleTally\(unit\.cycle, judged\.verdict\);/);
  assert.match(factoryBackend, /completed_rounds: tally\.settled,\s*pass_rounds: tally\.pass,/);
  assert.match(factoryBackend, /final_failures: tally\.fail,/);
  assert.match(factoryBackend, /total_attempts: unit\.cycle\?\.attempts \?\? unit\.attempts\.length,/);
  assert.doesNotMatch(factoryBackend, /total_attempts: unit\.attempts\.length,/);
  assert.match(factory, /const kpis = statisticsKpis\(statistics, formatBatchTime\(batchSnapshot, clockNow\), "production-sites"\);/);
  assert.match(factory, /const sameIcDebug = statistics\.mode === "SAME_IC_DEBUG";/);
});

// ------------------------------------------- EMode / PMode UI cleanup (Gate 1)

test("the duplicated result UI is removed from both modes, not hidden", async () => {
  const runLog = await read("app/programming/programming-run-log.ts");
  // EMode: no BATCH ATTEMPTS table and no standing ProgrammingRunView.
  assert.doesNotMatch(emode, /BATCH ATTEMPTS|batch-attempts|batch-attempt-|data-testid="batch-result"|data-testid="batch-policy"/);
  assert.doesNotMatch(emode, /ProgrammingRunView/);
  // PMode: no RECEIPTS & DIAGNOSTICS panel and no per-Site receipt card.
  assert.doesNotMatch(factory, /RECEIPTS & DIAGNOSTICS|factoryReceipts|data-receipt-site|receipt-note/);
  assert.doesNotMatch(factory, /ProgrammingRunView/);
  // Removed, never collapsed or hidden by CSS.
  for (const source of [emode, factory]) {
    assert.doesNotMatch(source, /display:\s*none[^}]*(receipt|attempt)/i);
  }
  // The shared run view itself stays: the Platform / Bundle Programming page owns it.
  const bundleUi = await read("app/engineering/bundle-programming.tsx");
  assert.match(bundleUi, /<ProgrammingRunView run=\{run\}/);
  // Both modes write the traceable run record to their Log instead.
  assert.match(runLog, /export function programmingRunLogLines/);
  for (const field of ["Run \\$\\{run.run_id\\}", "SAFE_OFF", "Job Binding SHA256", "Resource SHA256"]) {
    assert.match(runLog, new RegExp(field));
  }
  assert.match(emode, /programmingRunLogLines\(finishedRun, \{\s*executionInterface: interfaceOf\(finishedRun\.site_id\),\s*\}\)/);
  assert.match(factory, /programmingRunLogLines\(latestRun, \{ executionInterface: interfaceName \}\)/);
  // The Log summarises the Manager record; it never prints the whole JSON Receipt.
  assert.doesNotMatch(runLog, /JSON\.stringify/);
});

test("EMode and PMode number the same four chapters and the same Programming Job sub-items", async () => {
  const logPanel = await read("app/engineering/engineering-log-panel.tsx");
  const productionLog = await read("app/fleet/production-log-panel.tsx");
  // 1 / 2 / 3 / 4 in both modes, from the one shared header component.
  assert.match(emode, /<OperatorPanelHeader\s+number=\{1\}\s+title="SYSTEM SETUP & TARGETING"/);
  assert.match(emode, /<OperatorPanelHeader\s+number=\{3\}\s+title="LIVE SITE STATUS"/);
  assert.match(logPanel, /number=\{4\}/);
  assert.match(factory, /systemSetup: "SYSTEM SETUP & TARGETING"/);
  assert.match(factory, /number=\{1\}\s+title=\{text\.systemSetup\}/);
  assert.match(factory, /number=\{3\}\s+title=\{text\.liveStatus\}/);
  assert.match(factory, /<ProductionLogPanel number=\{4\}/);
  assert.match(productionLog, /number=\{number\}/);
  // PMode keeps its own Site presentation and its domain name in the meta line.
  assert.match(factory, /productionSelection: "PRODUCTION SITE SELECTION"/);
  assert.match(factory, /productionTree/);
  // 2-1 … 2-4 for both modes, from one rule in the shared panel.
  assert.match(panel, /const fieldNumber = \(index: number\) => `\$\{PROGRAMMING_JOB_SECTION\}-\$\{index\}\.`/);
  assert.doesNotMatch(panel, /`\$\{index\}\.`/);
});

test("removing the duplicated UI keeps the Manager evidence and the safety gates", () => {
  // Admission, Job Binding, Resource identity and Start reconciliation are untouched.
  assert.match(core, /batch = await startProgrammingBatch\(\{[\s\S]{0,200}operation: "read",/);
  assert.match(core, /batch = await startProgrammingBatch\(input, startId\)/);
  assert.match(emode, /async function reconcileStartHold/);
  assert.match(emode, /managed-start-hold/);
  assert.match(emode, /managed-unresolved/);
  assert.match(factory, /Manager Start \$\{managedStartHold\} is unresolved/);
  assert.match(factory, /runOfUnit\(batch, unit\)/);
  assert.match(factoryBackend, /unit\.outcome === "OUTCOME_UNKNOWN"/);
  assert.match(factory, /\[SITE\] \$\{label\} · \$\{verdict\.verdict\}/);
});

// --------------------------------------------------------------------- PR-C
// The Batch and its start are Manager-owned resources, and EMode covers many
// Sites of one PPU as ONE Batch the Manager runs in concurrent per-Site lanes.

test("PR-C: the Console reaches the canonical Batch resource, never an alias-scoped one", async () => {
  const route = await read("app/api/manager/programming/[...path]/route.ts");
  assert.match(api, /const PROGRAMMING = "\/api\/manager\/programming";/);
  for (const path of ["batches", "batches/\\$\\{batchId\\}", "batches/\\$\\{batchId\\}/stop",
    "starts", "starts/\\$\\{startId\\}", "starts/\\$\\{startId\\}/void"]) {
    assert.match(api, new RegExp(`\\$\\{PROGRAMMING\\}/${path}`));
  }
  // No Batch or start is addressed under a PPU any more.
  assert.doesNotMatch(api, /\$\{base\(alias\)\}\/(batches|starts)/);
  // The BFF route sits under /api/manager so the maintenance capability
  // cookie (Path=/api/manager) is still presented with it.
  assert.match(route, /const PROGRAMMING_BROWSER_PREFIX = "\/api\/manager\/programming";/);
  assert.match(route, /relayManagerProgrammingRequest\(request, resource\)/);
  // Starting a Batch submits Jobs: every Target PPU must be enrolled here.
  // EVERY canonical mutation carries the capability of every PPU it concerns,
  // which is what the alias-scoped routes it replaces required. Stop and void
  // resolve that PPU from the Manager's own record, so a caller's claim can
  // never widen them; a claim is used only where no PPU exists yet.
  assert.match(bff, /for \(const alias of aliases\) \{\s*if \(!hasMaintenanceCapability\(request, alias\)\) return maintenanceCapabilityRequired\(\);/);
  assert.match(bff, /if \(!maintenanceMutationOriginAllowed\(request\)\) return maintenanceCapabilityRequired\(\);/);
  assert.match(bff, /aliases = await authorizedAliases\(normalizedResource, body, declared\);/);
  assert.match(bff, /const stop = \/\^batches\\\/\(\[0-9a-f\]\{32\}\)\\\/\(\?:stop\|continue\)\$\/\.exec\(resource\);/);
  // Continue is audited under the BFF-verified identity; a Browser actor is refused.
  assert.match(bff, /"actor" in parsed/);
  assert.match(bff, /actor = maintenanceCapabilityActor\(request, parsed\.ppu_alias\);/);
  assert.match(bff, /const recorded = aliasesOfTargets\(view\?\.identity\?\.targets\);/);
  // Fail closed: an operation whose PPU cannot be established is refused.
  assert.match(bff, /if \(aliases === null \|\| aliases\.length === 0\)/);
  // The claim is never forwarded to the Manager.
  // Only the validated Cycle History cursor is forwarded as a query.
  assert.match(bff, /`\$\{managerApiBase\(\)\}\/api\/programming\/\$\{normalizedResource\}\$\{query\}`/);
  assert.match(bff, /const CYCLE_HISTORY_RESOURCE = new RegExp\(`\^batches\/\$\{RUN_ID\}\/cycles\$`\);/);
  assert.match(bff, /for \(const name of \["offset", "limit"\]\)/);
  assert.match(bff, /\/\^\\d\{1,9\}\$\/\.test\(value\)/);
});

test("PR-C: EMode selects many Sites of one PPU and sends one Target Set", () => {
  assert.match(emode, /const \[chosenSiteIds, setChosenSiteIds\] = useState<number\[\]>\(\[\]\);/);
  assert.match(emode, /const next = chosenSiteIds\.includes\(id\)/);
  assert.match(api, /targets: input\.targets[\s\S]*\? input\.targets\.map\(/);
  assert.match(api, /: \[\{ ppu_alias: input\.alias, site_ids: \[\.\.\.input\.siteIds\] \}\]/);
  // One PPU per Batch in EMode: the Target Set is built from one alias.
  assert.doesNotMatch(emode, /ppu_alias:|targets:/);
  // The Operations offered are the ones EVERY selected Site declares.
  assert.match(emode, /\.reduce\(\(shared, declared\) => shared\.filter\(item => declared\.includes\(item\)\)\)/);
  // An Erase Batch carries one range, so the Sites must agree on it.
  assert.match(emode, /const rangesAgree = /);
  assert.match(emode, /notReady\("RANGE DIFFERS"/);
  // The Stop Policy threshold never exceeds the Batch's own Site count.
  assert.match(emode, /\.\.\.siteIds\.map\(\(_id, index\) => \(\{/);
  assert.match(emode, /threshold >= 1 && threshold <= siteIds\.length/);
});

test("PR-C: every Site is judged on its own, and the Batch verdict never replaces a Site's", () => {
  assert.match(core, /export function batchSiteVerdict\(/);
  assert.match(core, /export function runOfUnit\(/);
  // U9: the Batch verdict is the Manager's aggregate; a Site's is the Manager's
  // record of THAT Site, refused only when it names another PPU / Site / Batch.
  assert.match(core, /export function batchVerdict\(batch: ProgrammingBatch\): \{ verdict: BatchVerdict; reason: string \| null \} \{\s*if \(batch\.outcome == null\) return \{ verdict: "RUNNING", reason: null \};\s*return \{ verdict: batch\.outcome, reason: batch\.reason \};/);
  assert.match(core, /const attempt = unit\.attempts\[unit\.attempts\.length - 1\];/);
  assert.match(core, /return \{ verdict: "FAIL", reason: "ATTEMPT_IDENTITY_MISMATCH" \};/);
  assert.match(core, /run\.run_id !== attempt\.run_id\) return null;/);
  // The Site row shows that Site's verdict, not the Batch aggregate.
  assert.match(emode, /const rowVerdict = batch && unit\s*\? batchSiteVerdict\(batch, unit, runOfUnit\(batch, unit\)\)\.verdict : null;/);
  // A Site row's progress is that Site's own, never another Site's run.
  assert.match(emode, /const stages = ownBatch \? unitStageStatuses\(batch, unit\)/);
  // A lost Start answer holds every Site it was for.
  assert.match(emode, /const siteRefusal = holdSites\(held\)\.map\(id => \{/);
});

// WP-07 (2026-11-16): the Manager runs Sites of one PPU in concurrent lanes but
// a Batch carries one current_run, so both pages read each Site's run by its
// run_id, and EMode keys each attempt by its Site.
test("concurrent lanes: each Site's run is read by run_id and each attempt is keyed by Site", async () => {
  assert.match(core, /export async function loadAttemptRun\(/);
  assert.match(core, /run\.run_id === runId && run\.ppu_alias === alias && run\.site_id === siteId \? run : null/);
  // Attempts are keyed by Site AND Repeat Cycle: attempt 1 recurs every Cycle.
  assert.match(emode, /const attemptKey = `\$\{attemptSite\}:\$\{attempt\.cycle_index \?\? 1\}:\$\{attempt\.attempt\}:\$\{attempt\.plan_id\}`;/);
  assert.match(emode, /loadAttemptRun\(next, request\.alias, attemptSite, attempt\.run_id\)/);
  assert.match(emode, /await Promise\.allSettled\(pendingRunLogs\);/);
  assert.match(factory, /loadUnitRun\(batch, unit\)/);
  // The Console never claims a sequential Batch any more.
  assert.doesNotMatch(emode, /· sequential/);
  // Each Site shows its own progress: the Manager's per-unit projection of
  // that Site's latest attempt, current_run only as an older-Manager fallback.
  assert.match(core, /export function unitStageStatuses\(/);
  assert.match(core, /if \(!last \|\| !own \|\| own\.attempt !== last\.attempt\) return null;/);
  assert.match(await read("app/fleet/managed-factory-backend.ts"), /progress_percent: passed \? 100 : unitProgressPercent\(batch, unit\) \?\? 0,/);
  // The TERMINAL line waits for Site run lines read by run_id.
  assert.match(factory, /unitLogsRef\.current = Promise\.allSettled\(\[unitLogsRef\.current, loaded\]\);/);
});

test("E Mode stage-only progress uses per-Site events and reduced-motion styling", async () => {
  const styles = await read("app/engineering/programming-workspace-v2.css");
  const factoryStyles = await read("app/fleet/factory-console-v2.css");
  assert.match(core, /const events = job\?\.stage_events \?\? \[\]/);
  assert.match(core, /verdict === "PASS" \? "completed"/);
  assert.match(emode, /<th>STAGES<\/th>/);
  assert.doesNotMatch(emode, /tableProgress|unitProgressPercent/);
  assert.match(emode, /stages\.map\(item => <span key=\{item\.name\}/);
  assert.match(factory, /site\.progress}%/);
  assert.match(factoryStyles, /factoryRunningPulse/);
  assert.match(core, /MANAGED_POLL_MS = 1000/);
  assert.match(factory, /const POLL_INTERVAL_MS = 250;/);
  assert.match(styles, /engineeringStagePulse 1s ease-in-out infinite/);
  assert.match(styles, /prefers-reduced-motion: reduce/);
});

// ------------------------------------------ Batch Statistics v1 (T16-T19, T10-T12)

const ts = (await import("typescript")).default;
const statisticsSource = await read("app/programming/batch-statistics.ts");
const stats = await import(`data:text/javascript;base64,${Buffer.from(ts.transpileModule(statisticsSource, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
}).outputText).toString("base64")}`);
const kpi = (items, key) => items.find(item => item.key === key)?.value;

test("T19 Replace IC: 2 Sites x Repeat 10 all PASS is IC-oriented with YIELD", () => {
  const s = stats.batchStatistics({ sites: 2, repeat: 10, replaceIc: true,
    tally: { settled: 20, pass: 20, fail: 0 }, jobAttempts: 20, retryAttempts: 0, sitesCompleted: 2 });
  const items = stats.statisticsKpis(s, "00:01:40");
  assert.deepEqual(items.map(item => item.label),
    ["SITES", "TOTAL IC", "PROCESSED IC", "PASS IC", "FAIL IC", "YIELD", "BATCH TIME"]);
  assert.deepEqual([kpi(items, "total-ic"), kpi(items, "processed-ic"), kpi(items, "pass"), kpi(items, "fail"),
    kpi(items, "yield")], [20, 20, 20, 0, "100.0%"]);
  assert.match(stats.statisticsMeta(s), /Job Attempts 20 · Retry 0/);
  assert.match(stats.statisticsLogLine(s), /operator-replaced, not identified/);
});

test("T18 Same-IC Debug: 2 Sites x Repeat 10 is Cycle-oriented and never shows YIELD", () => {
  const s = stats.batchStatistics({ sites: 2, repeat: 10, replaceIc: false,
    tally: { settled: 20, pass: 20, fail: 0 }, jobAttempts: 20, retryAttempts: 0, sitesCompleted: 2 });
  const items = stats.statisticsKpis(s, "00:01:40");
  assert.deepEqual(items.map(item => item.label), ["SITES", "PHYSICAL IC", "TOTAL CYCLES", "SETTLED CYCLES",
    "PASS CYCLES", "FAIL CYCLES", "CYCLE PASS RATE", "BATCH TIME"]);
  assert.deepEqual([kpi(items, "physical-ic"), kpi(items, "total-cycles"), kpi(items, "settled-cycles"),
    kpi(items, "pass"), kpi(items, "fail"), kpi(items, "cycle-pass-rate")], [2, 20, 20, 20, 0, "100.0%"]);
  assert.equal(items.some(item => /YIELD|TOTAL IC|PROCESSED IC/.test(item.label)), false);
  assert.match(stats.statisticsLogLine(s), /no YIELD/);
});

test("rates are N/A without a settled Cycle, never 100%", () => {
  for (const replaceIc of [true, false]) {
    const s = stats.batchStatistics({ sites: 2, repeat: 10, replaceIc });
    const items = stats.statisticsKpis(s, "00:00:00");
    assert.equal(kpi(items, replaceIc ? "yield" : "cycle-pass-rate"), "N/A");
  }
  assert.equal(stats.passRate(1, 1), "50.0%");
});

test("T06/T07 Stop after the first Cycle: PARTIAL keeps 2 PASS Cycles, 18 remaining, 0/2 Sites completed", () => {
  const s = stats.batchStatistics({ sites: 2, repeat: 10, replaceIc: true,
    tally: { settled: 2, pass: 2, fail: 0 }, jobAttempts: 2, retryAttempts: 0, sitesCompleted: 0 });
  assert.equal(s.passCycles, 2);
  assert.equal(s.remainingCycles, 18);
  assert.match(stats.statisticsMeta(s), /Cycles 2\/20 settled · 18 remaining · Sites completed 0\/2/);
  assert.match(stats.statisticsLogLine(s), /Cycles PASS 2 · FAIL 0 · settled 2\/20 · remaining 18/);
});

test("T03/T09 Cycles are the Manager's counters; OUTCOME_UNKNOWN never counts as PASS", () => {
  assert.deepEqual(stats.unitCycleTally({ planned: 1, settled: 1, pass: 1, fail: 0 }, "PASS"), { settled: 1, pass: 1, fail: 0 });
  // U9: the Manager's counters are the tally; the Browser never re-judges them.
  assert.deepEqual(stats.unitCycleTally({ planned: 1, settled: 1, pass: 0, fail: 1 }, "FAIL"), { settled: 1, pass: 0, fail: 1 });
  assert.deepEqual(stats.unitCycleTally({ planned: 1, settled: 0, pass: 0, fail: 0 }, "OUTCOME_UNKNOWN"), { settled: 0, pass: 0, fail: 0 });
  // A record from a Manager without counters falls back to its final outcome only.
  assert.deepEqual(stats.unitCycleTally(null, "PASS"), { settled: 1, pass: 1, fail: 0 });
  assert.deepEqual(stats.unitCycleTally(null, "OUTCOME_UNKNOWN"), { settled: 0, pass: 0, fail: 0 });
  // Repeat: the Manager's settled counters; an unknown Cycle is not settled.
  assert.deepEqual(stats.unitCycleTally({ planned: 3, settled: 1, pass: 1, fail: 0 }, "OUTCOME_UNKNOWN"), { settled: 1, pass: 1, fail: 0 });
});

test("T17 PMode snapshot statistics: same definitions, summed per Site, attempts cumulative", () => {
  const site = (pass, fail, attempts, retries) => ({
    completed_rounds: pass + fail, pass_rounds: pass, final_failures: fail, total_attempts: attempts, retry_count: retries });
  const s = stats.snapshotStatistics({ sites: [site(9, 1, 11, 1), site(10, 0, 10, 0)], repeat: 10, replaceIc: true });
  assert.deepEqual([s.settledCycles, s.passCycles, s.failCycles, s.jobAttempts, s.retryAttempts, s.sitesCompleted],
    [20, 19, 1, 21, 1, 2]);
  assert.equal(stats.passRate(s.passCycles, s.failCycles), "95.0%");
});

test("T10/T11/T12 Cycle History reader: cursor, order, no duplicate, catch-up and rebuild", async () => {
  const records = Array.from({ length: 25 }, (_, seq) => ({ seq, type: "cycle", ppu_alias: "z2", site_id: 1 + (seq % 2), cycle_index: 1 + (seq >> 1) }));
  let visible = 3;
  const loads = [];
  const load = async (offset, limit) => {
    loads.push([offset, limit]);
    const page = records.slice(offset, Math.min(visible, offset + limit));
    return { total: visible, offset, next_offset: offset + page.length, records: page };
  };
  const seen = [];
  const reader = stats.cycleHistoryReader(load, record => seen.push(record.seq), 4);
  await reader.sync();
  assert.deepEqual(seen, [0, 1, 2]);
  await Promise.all([reader.sync(), reader.sync(), reader.sync()]);   // repeated polls
  assert.deepEqual(seen, [0, 1, 2]);
  visible = 25;                                                       // many polls missed
  await reader.sync();
  assert.deepEqual(seen, [...Array(25).keys()]);
  assert.equal(reader.cursor, 25);
  assert.ok(loads.every(([, limit]) => limit === 4));                 // bounded pages only
  const rebuilt = [];
  await stats.cycleHistoryReader(load, record => rebuilt.push(record.seq), 10).sync();   // browser refresh
  assert.deepEqual(rebuilt, seen);
});

test("Cycle History lines carry Run / Job / SAFE_OFF / Readback / Job Binding and Retry history", () => {
  const lines = stats.cycleHistoryLogLines({
    seq: 4, type: "cycle", ppu_alias: "z2", site_id: 2, cycle_index: 3, outcome: "PASS",
    attempts: [
      { attempt: 1, run_id: "r1", job_id: "j1", outcome: "FAIL", reason: "VERIFY_MISMATCH", safe_off: true, retry: { decision: "RETRY", reason: "ELIGIBLE" } },
      { attempt: 2, run_id: "r2", job_id: "j2", outcome: "PASS", reason: null, safe_off: true, retry: null },
    ],
    receipt: { run_id: "r2", job_id: "j2", job_state: "completed", safe_off: true, job_binding_confirmed: true,
      readback_sha256: "ab".repeat(32), job_binding_sha256: "cd".repeat(32) },
  }, 10, "Site 2").map(line => line.text);
  assert.match(lines.join("\n"), /\[ATTEMPT 1\] Cycle 3\/10 Site 2 · FAIL · VERIFY_MISMATCH · Run r1 · Job j1 · SAFE_OFF VERIFIED · RETRY/);
  assert.match(lines.join("\n"), /\[CYCLE 3\/10\] Site 2 · PASS · Run r2 · Job j2 · SAFE_OFF VERIFIED · attempts 2/);
  assert.match(lines.join("\n"), new RegExp(`Readback SHA256 ${"ab".repeat(32)} · Job Binding confirmed ${"cd".repeat(32)}`));
});

test("T16 EMode: KPIs, Log totals and Cycle History come from the shared statistics, not the attempt list", () => {
  assert.match(emode, /const kpis = statisticsKpis\(statistics, formatElapsed\(elapsed\)\);/);
  assert.match(emode, /\? managedBatchStatistics\(batch\)/);
  assert.doesNotMatch(emode, /final\.attempts\.length|\{ key: "total-ic", label: "TOTAL IC", value: siteCount \}/);
  assert.match(emode, /cycle\?\.attempts \?\? unit\.attempts\.length\} attempt\(s\)/);
  assert.match(emode, /appendLog\(statisticsLogLine\(stats\)/);
  assert.match(emode, /managedCycleHistory\(next\.batch_id, record => logHistoryRecord/);
  assert.match(emode, /await history\.reader\?\.sync\(\)/);
  assert.match(core, /jobAttempts: batch\.cycles\?\.attempts \?\? batch\.counts\.attempts/);
  assert.match(api, /`\$\{PROGRAMMING\}\/batches\/\$\{batchId\}\/cycles\?offset=\$\{offset\}&limit=\$\{limit\}`/);
  assert.match(bff, /new RegExp\(`\^batches\/\$\{RUN_ID\}\/cycles\$`\),/);
});

test("T17 PMode: Factory Log reads the Cycle History by cursor and keeps TERMINAL after it", () => {
  assert.match(factory, /const reader = managedCycleHistory\(batch\.batch_id, record => \{/);
  assert.match(factory, /cycleHistoryLogLines\(record, repeat, label\)/);
  assert.match(factory, /unitLogsRef\.current = Promise\.allSettled\(\[unitLogsRef\.current, read\]\);/);
  assert.match(factory, /Job Attempts \$\{stats\.jobAttempts \?\? "—"\} · Retry \$\{stats\.retryAttempts \?\? "—"\}/);
  // P Mode's existing PASS / FAIL Cycle counters are kept, now via the shared tally.
  assert.match(factoryBackend, /unitCycleTally/);
  assert.match(factoryBackend, /: batch\.outcome === "PARTIAL" \? "partial"/);
});

// ------------------------------- Site safety evidence v1 (SAFE_OFF state vs result)

test("SAFE_OFF label quotes the Manager state and never confuses it with the result", () => {
  assert.equal(stats.safeOffLabel("VERIFIED", true), "VERIFIED");
  assert.equal(stats.safeOffLabel(undefined, true), "VERIFIED");  // older receipts
  assert.equal(stats.safeOffLabel("NOT_TOUCHED", null), "N/A · hardware not touched");
  assert.equal(stats.safeOffLabel("NOT_VERIFIED", null), "NOT VERIFIED");
  assert.equal(stats.safeOffLabel(null, null), "NOT VERIFIED");
  assert.equal(stats.safeOffLabel(null, null, false), "—");
  // A PASS-looking or reason-looking value never upgrades the state.
  assert.equal(stats.safeOffLabel("PASS", false), "NOT VERIFIED");
});

test("A pre-hardware denial is a BLOCKED history line, not a Cycle FAIL", () => {
  const [line] = stats.cycleHistoryLogLines({
    seq: 3, type: "blocked_dispatch", ppu_alias: "z2", site_id: 2, cycle_index: 15,
    reason: stats.SITE_DENIED_BEFORE_HARDWARE,
    attempts: [{ attempt: 1, run_id: "c5de59", job_id: "job-x", outcome: "BLOCKED",
      reason: stats.SITE_DENIED_BEFORE_HARDWARE, safe_off: null, safe_off_state: "NOT_TOUCHED" }],
    receipt: { run_id: "c5de59", job_id: "job-x", job_state: "error", safe_off: null,
      safe_off_state: "NOT_TOUCHED", job_binding_confirmed: true,
      site_safety: { class: "PRE_HARDWARE_DENIED", code: "ADMISSION_DENIED:PROC_SCAN_INCOMPLETE" } },
  }, 20, "Site 2");
  assert.match(line.text, /^\[BLOCKED\] Cycle 15\/20 Site 2 · denied before hardware · ADMISSION_DENIED:PROC_SCAN_INCOMPLETE/);
  assert.match(line.text, /SAFE_OFF N\/A · hardware not touched · not counted as a Cycle · press Start to re-run admission/);
  assert.doesNotMatch(line.text, /FAIL|NOT VERIFIED/);
  // The existing next-Cycle dispatch block keeps its own wording.
  const [next] = stats.cycleHistoryLogLines({ seq: 4, type: "blocked_dispatch", ppu_alias: "z2",
    site_id: 2, cycle_index: 3, reason: "EXECUTION_PPU_BUSY", attempts: [] }, 20, "Site 2");
  assert.match(next.text, /NEXT CYCLE BLOCKED · EXECUTION_PPU_BUSY · nothing submitted/);
});

test("Cycle and attempt lines show SAFE_OFF from the receipt state", () => {
  const lines = stats.cycleHistoryLogLines({
    seq: 0, type: "cycle", ppu_alias: "z2", site_id: 1, cycle_index: 1, outcome: "FAIL",
    reason: "JOB_NOT_SUCCESS",
    attempts: [{ attempt: 2, run_id: "r", job_id: "j", outcome: "FAIL", reason: "JOB_NOT_SUCCESS",
      safe_off: true, safe_off_state: "VERIFIED", retry: null }],
    receipt: { run_id: "r", job_id: "j", job_state: "error", safe_off: true,
      safe_off_state: "VERIFIED", job_binding_confirmed: true },
  }, 2, "Site 1");
  assert.ok(lines.every(entry => !/NOT VERIFIED/.test(entry.text)));
  assert.match(lines[1].text, /\[CYCLE 1\/2\] Site 1 · FAIL · JOB_NOT_SUCCESS .* SAFE_OFF VERIFIED/);
});

test("Console surfaces use the one SAFE_OFF label; READY stays the PPU Site capability", async () => {
  const core = await read("app/programming/managed-programming.ts");
  const runLog = await read("app/programming/programming-run-log.ts");
  const workspace = await read("app/engineering/managed-programming-workspace.tsx");
  const factory = await read("app/fleet/factory-console-v2.tsx");
  const view = await read("app/operator-ui/programming-run-view.tsx");
  assert.match(core, /cycle\.wait_reason === SITE_DENIED_BEFORE_HARDWARE\s*\? "BLOCKED · denied before hardware · not counted · press Start to re-run admission"/);
  assert.match(core, /`SAFE_OFF \$\{safeOffLabel\(receipt\?\.safe_off_state, receipt\?\.safe_off\)\}`/);
  assert.match(runLog, /return safeOffLabel\(state, safeOff, finished\);/);
  assert.match(workspace, /safeOffLogLabel\(attempt\.safe_off, true, attempt\.safe_off_state\)/);
  // A re-run Cycle restarts at attempt 1: its Log key includes the plan.
  assert.match(workspace, /`\$\{attemptSite\}:\$\{attempt\.cycle_index \?\? 1\}:\$\{attempt\.attempt\}:\$\{attempt\.plan_id\}`/);
  assert.match(factory, /SAFE_OFF \$\{safeOffLabel\(last\?\.safe_off_state, last\?\.safe_off\)\}/);
  assert.match(view, /\{safeOffLabel\(receipt\.safe_off_state, receipt\.safe_off\)\}/);
  for (const source of [core, workspace, factory, view]) {
    assert.doesNotMatch(source, /safe_off === true \? "VERIFIED" : "NOT VERIFIED"/);
  }
  // Site READY is the PPU's own idle Site + Profile, never a Batch or SAFE_OFF guess.
  assert.match(core, /if \(site\.current_job_id \|\| site\.state !== "idle"\) \{/);
  assert.match(core, /return \{ programmable: true, label: "READY", reason: "" \};/);
});

test("a Programming Image is bound only when Program or Verify is selected", () => {
  // Moved from the retired server-batch-api contract (U10): the managed
  // request carries a file only for P/V; Erase-only sends no Image.
  assert.match(api, /export function operationsTakeImage\(operations: readonly string\[\]\): boolean \{\s*return operations\.includes\("program"\) \|\| operations\.includes\("verify"\);/);
  assert.match(emode, /const needsImage = operations != null && operationsTakeImage\(operations\);/);
  assert.match(factory, /const managedNeedsFile = managedChosen != null && operationsTakeImage\(managedChosen\);/);
  assert.match(core, /operations: readonly \["erase"\]; operation\?: undefined; file: null;/);
});
