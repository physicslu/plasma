# Path 3 Cross-Job Resume — CPU-only special fixture (historical Gate 1)

**Historical status (as written 2026-10-23):** The original proposal was an unmerged Draft with real SWPC two-Job acceptance deferred/NOT_RUN and a one-time Gate 1 sequencing exception. **Do not treat that historical PR state as the current `main` status.** A conditional `development-codex-resume` Job and `scripts/plasma_path3_cross_job_resume.py` were subsequently installed but are **retired by the 2026-10-27 Path 3 Gate 1 PR**; the rest of this file documents the old experiment only and must not be used as current operational instructions. The historical CPU-only fixture was never general hardware authorization. Consult live GitHub runs for actual acceptance.

This change reuses Issue #981, the existing reusable runtime-dispatch Workflow,
the existing SWPC-plasma-codex Runner, trusted main dispatcher, and dynamic
Work Order. It introduces NO new workflow, runner, registry ID, hardware
capability, deployment, or additional owner approval gate.

## Exact two-Job contract

The one approved owner Issue command opts into the fixed
page-boundary-off-by-one fixture by specifying:

- execution_path = path3-codex; capability = codex-workspace
- scope = host-only; session_resume = page-boundary-off-by-one
- Pre-merge candidate: pr_number > 0, exact immutable source_sha, and a live
  same-repository **Open** PR at that HEAD; closed/merged PRs stay denied.
- One-time post-merge: pr_number = 0 and **explicit source_sha** equal to the
  trusted main event GITHUB_SHA (the actual merge commit). Missing or stale
  source SHA, non-main ref, non-issue event or broader scope must fail closed.

Job 1 (development-codex) launches a fresh real Codex CLI session under an
explicit Bubblewrap filesystem/device namespace. It requires an initially
failing page-boundary unittest, a still-failing test after the diagnosis-only
turn, and no first-turn file fix. The **test** result is expected FAIL but the
GitHub Job succeeds only if this expected failure was independently observed.

Job 2 (development-codex-resume) runs only after Job 1 successfully recorded
its expected failing test. It uses a second Job in the SAME existing Workflow,
same trusted main, the same immutable candidate or post-merge main SHA,
and the existing Runner. It rechecks the
Work Order digest, GitHub Run ID, attempt=1, source/trusted SHA, UID/Runner,
checkout path and test hash. A mismatched, missing, unsafe or already-consumed
private Session refuses Resume; there is no automatic NEW fallback or retry.
A resumed Codex must produce the same Thread ID, pass the unchanged test and
write the exact synthetic first-turn-only challenge.

## State and evidence isolation

The private persistent SWPC state directory is owner-only (0700), its single
JSON resume record is 0600 and includes the raw Thread ID plus only the
SHA-256 of the synthetic first-turn challenge. Job 2 atomically consumes the
record before starting Codex. Codex rollouts and model authentication stay
under the private isolated Codex home; neither enters GitHub artifacts.
Public receipts expose only a Thread ID SHA-256, a bounded numeric per-turn
Token Usage, non-secret identifiers and test exit codes. Neither raw prompt,
session rollout, challenge, credential nor stderr is archived.

Bubblewrap mounts the exact candidate Git checkout **read-only**, including
its Git metadata; only the dedicated Page-boundary fixture directory and
the Run-specific private Codex home are writable. The pre- and post-Model
unittest subprocesses apply the same read-only checkout / writable scratch
split, synthetic /dev and an isolated network namespace. The Codex CLI must
retain model API connectivity, so its namespace does not claim network egress
isolation. Bubblewrap also uses read-only system mounts and no host /sys or
broad host-home binding. It is a filesystem/device
boundary, NOT a proven network egress firewall. An unavailable isolation tool
or Codex credential causes fail-closed NOT_RUN/FAIL. No Z2, FPGA, USB, MMIO,
Power, DUT, real programming or physical hardware is authorized.

## Owner-approved deferred-acceptance exception (PR #1134 only)

The trusted Issue #981 Dispatcher and optional second Job are now present
in current `main` for the exact CPU-only fixture. An unmerged candidate
cannot replace the trusted `main` controller. Hosted fake-Codex tests cannot
prove real SWPC Session Resume. Normally real Path 3 SWPC acceptance belongs to Gate 1
**before Gate 2**. The owner explicitly approved a one-time deferral on
2026-10-23 for this fixed CPU-only fixture, not generic Resume support.

1. **Historical Gate 1 before merge (not a current gating requirement):** Hosted positive/negative tests, all relevant CI,
   isolation and code review, Rulesets/Reviews/Threads and exact HEAD checks.
   Keep explicit `SWPC_E2E=DEFERRED_NOT_RUN`; do not invent Run IDs, real
   Runner evidence, Usage or continuity proof. Maintain Draft until ready.
2. **Historical Gate 2 decision:** The owner must explicitly accept
   the specific reviewed HEAD and the missing SWPC evidence. Recheck main,
   HEAD, CI, Reviews, Threads, Rulesets, dependencies and mergeability.
   If a merge is explicitly authorized, verify merge SHA, both parents and
   Git tree. Gate 1 revision alone authorizes no merge.
3. **Optional CPU-only post-merge Work Order:** A separate explicit owner Issue #981
   command pins `pr_number=0`, `source_sha=<actual main merge SHA>` and
   `session_resume=page-boundary-off-by-one`. The event's trusted main
   GITHUB_SHA must equal source_sha. This is existing Dispatcher/Workflow/
   SWPC-plasma-codex Runner only, with no new workflow or privilege.
4. **Authentic acceptance:** Job #1 must report `NEW_EXPECTED_TEST_FAIL`
   (the unittest FAIL is expected; GitHub Job succeeds on verified evidence).
   Job #2 must report `RESUME_FIX_PASS`. Review genuine Run ID, distinct
   Job IDs, same trusted/source/work-order SHA, Runner UID/name, workspace,
   hashed Thread continuity, recovered first-turn challenge, unchanged
   test, before/after test exits and both numerical token usages.
5. **Any failure:** FAIL or NOT_RUN; never soften Bubblewrap, expand
   device/home access, auto-retry consumed Session, deploy, operate
   Z2/FPGA/USB/MMIO/Power/DUT, force-rewrite or silently reset main.
   Use an independent reviewed repair PR and normal Gate 2 if necessary.

### Deferred risk register

| Risk | Residual impact | Required boundary |
|---|---|---|
| Untested SWPC behavior reaches main | HIGH | Specific Gate 2 deferral acceptance and owner-only opt-in |
| Host Bubblewrap/Codex/auth incompatibility | MEDIUM-HIGH | Real E2E; fail closed, not hosted PASS |
| Main moves before Issue #981 event | MEDIUM | Explicit source_sha equals event GITHUB_SHA |
| Model API network egress | MEDIUM-HIGH | Synthetic devices/read-only checkout; no claim of egress firewall |
| E2E failure after merge | MEDIUM | Separate PR/ordinary Gate 2; no automatic rollback |

Pre-merge PR-based mode still requires an OPEN live PR with the exact
HEAD. The main-only route is limited to the fixed host-only Page-boundary
experiment, and does NOT qualify general Resume or grant hardware authority.
The two existing owner approval Gate types are unchanged.
