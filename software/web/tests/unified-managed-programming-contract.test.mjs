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
  assert.equal((core.match(/planProgramming\(/g) ?? []).length, 1);
  assert.equal((core.match(/startProgramming\(/g) ?? []).length, 1);
  assert.equal((emode.match(/runManagedProgramming\(/g) ?? []).length, 1);
  assert.doesNotMatch(emode, /planProgramming\(|startProgramming\(/);
  // The only loop is the read-only status poll.
  assert.equal((core.match(/\bwhile \(/g) ?? []).length, 1);
  assert.match(core, /while \(run\.outcome == null\)/);
  assert.doesNotMatch(core, /for \(let (retry|attempt)/);
  assert.match(core, /MANAGED_JOB_POLICY = Object\.freeze\(\{ attempts: 1, auto_retry: "DISABLED" as const \}\)/);
  assert.match(core, /status != null && status >= 400 && status < 500/);
  assert.match(core, /throw new ManagedStartOutcomeUnknown\(/);
});

test("Start is double-click safe and the manual Prepare step is gone from EMode", () => {
  assert.match(emode, /if \(startLock\.current \|\| !readiness\.ready/);
  assert.match(emode, /startLock\.current = true;\s*const request =/);
  assert.doesNotMatch(emode, /Prepare Programming|Confirm programming|confirmedPlanId/);
  assert.match(emode, /startLabel="START PROGRAMMING"/);
});

test("Retry / Repeat / Stop Policy and ABORT are disabled for formal Flash Jobs", () => {
  assert.match(emode, /repeatDisabled: true/);
  assert.match(emode, /retryValue: "0",\s*retryDisabled: true/);
  assert.match(emode, /stopDisabled: true/);
  assert.match(emode, /abortDisabled\s/);
  assert.doesNotMatch(emode, /siteRetryLimit|site_retry_limit|repeat_count/);
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
