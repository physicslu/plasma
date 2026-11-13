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
const router = await read("app/engineering/programming-workspace-v2.tsx");
const api = await read("app/engineering/bundle-programming-api.ts");
const bff = await read("app/api/manager/bootstrap-bff.ts");
const panel = await read("app/operator-ui/programming-job-panel.tsx");
const selector = await read("app/operator-ui/programming-source-selector.tsx");
const view = await read("app/operator-ui/programming-run-view.tsx");

test("formal Console routes EMode Programming to the Manager backend, never the Mock runtime", () => {
  assert.match(router, /apiMode === "managed" \? <ManagedProgrammingWorkspace \/> : <StandaloneProgrammingWorkspace \/>/);
  assert.match(router, /if \(!hydrated\) return null;/);
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
  // Two entry points, each with exactly one plan and one start: the Batch
  // programming Job and the independent Read Memory Job.
  assert.equal((core.match(/planProgramming\(/g) ?? []).length, 2);
  assert.equal((core.match(/startProgramming\(/g) ?? []).length, 2);
  assert.match(core, /export async function runManagedRead\(/);
  // EMode starts one Manager Batch; PMode keeps the single-run entry point.
  assert.equal((emode.match(/runManagedBatch\(/g) ?? []).length, 1);
  assert.doesNotMatch(emode, /planProgramming\(|startProgramming\(/);
  // The only loops are the read-only status polls (run, Batch).
  assert.equal((core.match(/\bwhile \(/g) ?? []).length, 2);
  assert.match(core, /while \(run\.outcome == null\)/);
  assert.match(core, /while \(batch\.outcome == null\)/);
  assert.doesNotMatch(core, /for \(let (retry|attempt)/);
  assert.match(core, /MANAGED_JOB_POLICY = Object\.freeze\(\{ attempts: 1, auto_retry: "DISABLED" as const \}\)/);
  assert.match(core, /status != null && status >= 400 && status < 500/);
  assert.match(core, /throw new ManagedStartOutcomeUnknown\(/);
});

test("Start is double-click safe and the manual Prepare step is gone from EMode", () => {
  assert.match(emode, /if \(startLock\.current \|\| !readiness\.ready/);
  assert.match(emode, /startLock\.current = true;\s*const policy = \{ retryLimit, stopPolicy \};\s*const started = \[\.\.\.siteIds\];\s*const request: ManagedBatchRequest =/);
  assert.doesNotMatch(emode, /Prepare Programming|Confirm programming|confirmedPlanId/);
  assert.match(emode, /startLabel="START PROGRAMMING"/);
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
  assert.match(core, /startId = await issueBatchStart\(\);[\s\S]*startProgrammingBatch\(input, startId\)/);
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
  assert.match(core, /plan = await planProgramming\(request\.alias, input\)/);
  assert.match(emode, /\[PLAN\] \$\{planned\.plan_id\} · Route/);
  assert.match(emode, /Resource SHA256 \$\{planned\.resource\.resource_set_sha256\} · Job Binding SHA256/);
});

test("EMode Batch Policy: Repeat disabled; Retry / Stop Policy are decided by the Manager, never the Browser", () => {
  assert.match(emode, /repeatValue: String\(MANAGED_JOB_POLICY\.attempts\),\s*repeatDisabled: true/);
  // One Batch request; the Browser has no retry loop and no plan / start of its own.
  assert.equal((emode.match(/runManagedBatch\(/g) ?? []).length, 1);
  assert.equal((core.match(/startProgrammingBatch\(/g) ?? []).length, 1);
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

test("UI PASS needs the Manager receipt, single submission, verified SAFE_OFF and matching identities", () => {
  assert.match(core, /if \(run\.outcome !== "PASS"\) return \{ verdict: run\.outcome, reason: run\.reason \}/);
  for (const reason of ["RECEIPT_MISSING", "SAFE_OFF_NOT_VERIFIED", "JOB_SUBMISSION_COUNT_NOT_ONE",
    "JOB_BINDING_NOT_CONFIRMED", "RESOURCE_SET_NOT_CONFIRMED", "READBACK_SHA256_MISMATCH"]) {
    assert.match(core, new RegExp(reason));
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

test("PMode on a Managed Control Station reads Registry / Fleet / Routes, not the Engineering provider", () => {
  assert.match(factory, /const managed = apiMode === "managed";/);
  assert.match(factory, /if \(managed\) \{\s*const topology = await loadManagedTopology\(\);/);
  assert.match(factory, /nextCatalog = managedFactoryCatalog\(topology\);/);
  assert.match(factory, /managed \? managedPpuStatus\(await loadManagedTopology\(\), alias\) : await getPPUStatus\(targetBase\)/);
  assert.match(factory, /const stored = managed \? null : readStoredBatch\(\);/);
  assert.match(factoryBackend, /ppu_id: ppu\.alias,\s*display_name: `\$\{ppu\.alias\} · PPU ID \$\{ppu\.ppuId \?\? "unknown"\}`/);
});

test("PMode never relabels unavailable Programming as ready: capability is route- and Site-proven", () => {
  assert.match(factoryBackend, /label: "PROGRAMMING UNAVAILABLE"/);
  assert.match(factoryBackend, /siteCapability\(site, routes, icpn\)/);
  assert.match(factory, /const blocker = managedBatchBlocker\(managedTopology, managedRoutes\.routes, icpn,/);
  // site_count alone never makes a Site programmable.
  assert.doesNotMatch(factoryBackend, /site_count[^\n]*programmable|siteCount[^\n]*programmable/);
});

test("PMode production batch is a sequence of independent Manager runs: no second engine, no retry", () => {
  assert.equal((factoryBackend.match(/runManagedProgramming\(/g) ?? []).length, 1);
  assert.doesNotMatch(factoryBackend, /planProgramming\(|startProgramming\(|\/api\/jobs|createServerBatch|Promise\.all\(this\.entries/);
  assert.doesNotMatch(factoryBackend, /retry_count: [1-9]|site_retry_limit: [1-9]/);
  assert.match(factoryBackend, /repeat_count: 1,\s*site_retry_limit: 0,/);
  assert.match(factoryBackend, /for \(const entry of this\.entries\) \{/);
  assert.match(factory, /if \(managed\) \{\s*await executeManagedBatch\(\);\s*return;\s*\}/);
  assert.match(factory, /if \(!catalog \|\| batchRunning \|\| managedStartLock\.current\) return;/);
});

test("PMode isolates PPUs: per-PPU admission, per-PPU OUTCOME_UNKNOWN latch, stop only prevents starts", () => {
  assert.match(factoryBackend, /admitted = await this\.admit\(entry\.alias\);/);
  assert.match(factoryBackend, /this\.skipRemaining\(entry => entry\.alias === alias, "stopped",/);
  assert.match(factoryBackend, /A run already submitted is never cancelled from the Console/);
  assert.match(factoryBackend, /this\.stopReason = "failed_site_threshold";/);
  assert.match(factoryBackend, /completed_rounds: entry\.pass \? 1 : 0,/);
  assert.match(factoryBackend, /if \(verdict === "PASS"\) \{\s*entry\.pass = true;/);
});

test("PMode shares the Source selector and policy with EMode", () => {
  assert.match(factory, /useState<ProgrammingSource>\("image"\)/);
  assert.match(factory, /source=\{managed \? \{ value: programmingSource, disabled: batchRunning, onChange: changeProgrammingSource \} : undefined\}/);
  assert.match(factory, /function changeProgrammingSource\(next: ProgrammingSource\) \{\s*if \(batchRunning \|\| next === programmingSource\) return;\s*setProgrammingSource\(next\);\s*setManagedFile\(null\);/);
  assert.match(factory, /repeatDisabled: managed \|\| batchRunning/);
  assert.match(factory, /retryValue: managed \? "0" : siteRetryLimit/);
  assert.match(factory, /executionInterface: record\.siteInterface/);
});

test("PMode keeps sequential readiness and does not render a standing qualification banner", () => {
  assert.match(factoryBackend, /readyLabel: "SEQUENTIAL BATCH READY"/);
  assert.doesNotMatch(factory, /data-testid="managed-production-mode"/);
  assert.doesNotMatch(factory, /factoryProductionMode/);
  assert.match(factory, /label: MANAGED_PRODUCTION_MODE\.readyLabel, ready: true/);
  assert.doesNotMatch(factory + factoryBackend, /PRODUCTION READY|Production Ready/);
  // A reload must never resume or resubmit an in-flight managed batch.
  assert.doesNotMatch(factoryBackend, /sessionStorage|localStorage|writeStoredBatch/);
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
  assert.match(factory, /programmingRunLogLines\(record\.run, \{ executionInterface: record\.siteInterface \}\)/);
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
  assert.match(core, /plan = await planProgramming\(request\.alias, input\)/);
  assert.match(emode, /async function reconcileStartHold/);
  assert.match(emode, /managed-start-hold/);
  assert.match(emode, /managed-unresolved/);
  assert.match(factoryBackend, /OUTCOME UNKNOWN \(\$\{reason \?\? "unknown"\}\); nothing was resubmitted/);
  assert.match(factoryBackend, /records\(\): ManagedSiteRecord\[\]/);
  // PMode still logs every Site outcome, including the ones that never ran.
  assert.match(factory, /\[SITE\] \$\{site\} · \$\{record\.note\}/);
});

// --------------------------------------------------------------------- PR-C
// The Batch and its start are Manager-owned resources, and EMode covers many
// Sites of one PPU as ONE Batch the Manager schedules sequentially.

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
  assert.match(bff, /for \(const alias of aliases\) \{\s*if \(!hasMaintenanceCapability\(request, alias\)\) return maintenanceCapabilityRequired\(\);/);
  assert.match(bff, /if \(!maintenanceMutationOriginAllowed\(request\)\) return maintenanceCapabilityRequired\(\);/);
});

test("PR-C: EMode selects many Sites of one PPU and sends one Target Set", () => {
  assert.match(emode, /const \[chosenSiteIds, setChosenSiteIds\] = useState<number\[\]>\(\[\]\);/);
  assert.match(emode, /const next = chosenSiteIds\.includes\(id\)/);
  assert.match(api, /targets: \[\{ ppu_alias: input\.alias, site_ids: \[\.\.\.input\.siteIds\] \}\]/);
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
  // The aggregate is necessary but not sufficient: every Site must pass too.
  assert.match(core, /for \(const unit of batch\.units\) \{\s*const judged = batchSiteVerdict\(batch, unit, runOfUnit\(batch, unit\)\);/);
  // A Site is judged on the Manager's record of it, and on the full receipt
  // whenever the Browser still holds that Site's run.
  assert.match(core, /const attempt = unit\.attempts\[unit\.attempts\.length - 1\];/);
  assert.match(core, /attempt\.safe_off !== true \? "SAFE_OFF_NOT_VERIFIED"/);
  assert.match(core, /run\.run_id !== attempt\.run_id\) return null;/);
  // The Site row shows that Site's verdict, not the Batch aggregate.
  assert.match(emode, /const rowVerdict = batch && unit\s*\? batchSiteVerdict\(batch, unit, runOfUnit\(batch, unit\)\)\.verdict : null;/);
  // Sequential execution: the run the Browser holds belongs to one Site.
  assert.match(emode, /run\.site_id === site\.site_id && run\.ppu_alias === ppu\?\.alias \? run : null/);
  // A lost Start answer holds every Site it was for.
  assert.match(emode, /const siteRefusal = holdSites\(held\)\.map\(id => \{/);
});
