# PLASMA Path 3 — Controlled Codex Session Resume Host-only PoC

**Gate 1 / Path 1, Host-only.** This document and the associated CPU-only probe **do not enable cross-Job resume in the trusted Path 3 Dispatcher**. Production Path 3 still launches exactly one fresh `codex exec` invocation per authorized Job. No SWPC Runner, Z2, DUT, FPGA, USB, power, deployment, model credential or real programming access is added.

## Engineering decision

There are two distinct kinds of debug continuity:

1. **Within one Path 3 Job (already supported):** Codex independently iterates Code → Test → Fix → Retest within the same `exec` process. Its context is continuous for that process; no extra Dispatcher retry job is created.
2. **Across two independent Codex processes / Jobs (not yet production-supported):** `codex exec resume <thread-id>` may restore the same dialogue. Simply recording the first `thread.started.thread_id` does not prove resume succeeded. Git source pin, task/owner binding, sandbox policy and working files must remain valid.

**This Gate 1 only demonstrates the host-side probe contract**, using deterministic offline fake-CLI tests and an opt-in real local CLI entrypoint. Real Codex CLI resume on the owner's machine, and real cross-Job SWPC Path 3 qualification, are **NOT_RUN** until separately observed and authorized. Synthetic tests are not proof that upstream Codex restored memory.

## Continuous debugging example: Page-boundary off-by-one

The disposable `.plasma-path3-resume-probe/` directory contains:

- `mock_page_chunks.py`: pure CPU byte-array page splitting with an intentionally wrong `range(0, len(data) - 1, page_size)`. A trailing one-byte page is silently dropped. This is **mock image slicing**, not real IC programming or electrical control.
- `test_mock_page_chunks.py`: Python standard-library `unittest` checks 0, 1, 7, 8, 9, 15, 16, 17, 24, 25 byte lengths and invalid page size. Initially FAIL.
- `resume-proof.txt`: written only during the second turn. It must contain a random synthetic 128-bit challenge first shown **only in the first turn prompt**, not in any on-disk file. The resume prompt does not repeat the challenge.

Expected test flow:

| Stage | Command / action | Expected evidence |
| --- | --- | --- |
| Preflight | exact pinned Git HEAD, clean isolated checkout, fixture baseline unittest | baseline **FAIL**, no preexisting probe directory |
| NEW (turn 1) | `codex exec --json --sandbox workspace-write`, review bug **without editing files** | valid UUID `thread.started`, `turn.completed` usage, code still FAIL, challenge not written to files |
| RESUME (turn 2) | `codex exec --json resume <exact UUID>`, same cwd; explicit sandbox and network restrictions | **same** `thread.started` UUID; source fixes off-by-one; original `unittest` PASS; proof contains exact first-turn challenge |
| Admission verdict | independent subprocess/unit tests + challenge check + Git status | **PASS only if all above succeed**, otherwise FAIL; raw prompts/transcripts are never saved |

Strict negatives: new thread after resume → `RESUMED_THREAD_MISMATCH`; fixed code but challenge missing → `CHALLENGE_NOT_RECOVERED`; altered test → `TEST_MODIFIED`; first turn unexpectedly fixes issue → `FIRST_TURN_PREMATURE_FIX`; changed Git ref or edits outside scratch directory → `UNAUTHORIZED_WORKSPACE_CHANGE`; expired/missing ID/usage → explicit failure. No automatic retries, new Session fallback, or hardware/privilege escalation.

### Why the one-time challenge matters

A second **fresh** agent could simply inspect the file and repair a trivial bug. That would not show dialogue continuity. The second prompt therefore does not contain the synthetic challenge and the first turn may not persist it. Both **same resumed UUID and the exact previous-turn challenge** are necessary; a successful Python test alone is insufficient. This is evidence of first-turn context carryover, *not* proof of any specific hidden reasoning mechanism.

## Offline test and real Host-only invocation

The existing GitHub-hosted `plasma-engineering-runtime-dispatch.yml` PR contract job runs `scripts/tests/test_plasma_development_dispatch.py`; its new `Path3SessionResumeHostOnlyProbe` suite injects a **fake Codex subprocess**. It asserts NEW → FAIL → RESUME → PASS, UUID mismatch, challenge missing, premature success, first-turn failure, dirty source and missing telemetry. **No model is called during CI**. Host-only CI success must be labeled `SIMULATED_PASS`, not `SWPC_RESUME_PASS`.

A future owner who wants a *real* local CPU-only CLI test can use an **independent clean isolated checkout** with exact SHA, never the production SWPC workspace. This executes Codex twice and consumes model Tokens; it is **not run as part of this PR**:

~~~bash
# Only in an explicitly authorized disposable local checkout, after reviewing the CLI version:
python3 scripts/plasma_path3_session_resume_probe.py \
  --manual-host-only \
  --repo "$PWD" \
  --expected-head "$(git rev-parse HEAD)"
~~~

Running it creates a fresh untracked `.plasma-path3-resume-probe/` directory and owner-only `receipt.json`, does not commit or push, and refuses to overwrite an existing probe. The caller must review the local source, stdout hashes and receipt; never commit raw Codex rollout data. A failed attempt remains auditable rather than triggering a hidden retry. A nonzero exit or missing real `thread.started` is FAIL, not automatically recovered with `--last`.

**Sandbox caution:** Some Codex releases do not accept `--sandbox` on `exec resume` and may not preserve the original explicit policy when resuming. The probe sets `sandbox_mode="workspace-write"` **again for both processes**, keeps `sandbox_workspace_write.network_access=false`, and never requests full access. This CLI sandbox is not an OS-level guarantee for physical device/host access. Do not place the experiment on a privileged SWPC/HIL worker.

## Future production-admission prerequisites (not implemented here)

An independently approved Gate 1 would be required for wiring Resume into the trusted Dispatcher across GitHub Jobs. It must verify session provenance and storage availability **for the exact Worker owner**, task/work-order digest, Git source SHA/PR HEAD, Git tree/working-diff identity, consistent sandbox/permissions, lease/ownership and timeout/failure semantics. Persistent Runner may erase or relocate original Session rollouts; an ID without matching stored context cannot be trusted. Never load the private session rollout into GitHub Artifacts or put credentials/prompts into receipts. Even with valid Resume, any new hardware stage needs its existing effective owner/guard authorization.

Suggested policy: resume only an **unfinished, still-approved Work Order** whose exact immutable source, task and owner match; start fresh on unrelated tasks or after a closed/merged work item. Maintain bounded numeric total/cached/noncached/output Token telemetry to understand context growth. No third owner approval gate.
