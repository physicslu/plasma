# PLASMA Path 3 — historical offline Codex Session Resume PoC

> **RETIRED FROM PATH 3 RUNTIME — OFFLINE RESEARCH FIXTURE ONLY (#1181).**
> **Do not use this document or `plasma_path3_session_resume_probe.py` as a
> Path 3 middleware, Dispatcher/Work Order contract, CI runtime entrypoint,
> or hardware operating procedure.** The probe is manual, CPU-only research;
> its synthetic tests do not authorize SWPC Runner, Z2, DUT, FPGA, USB, power
> or deployment access.

**Historical Gate 1 / Path 1, host-only PoC.** A later `page-boundary-off-by-one` conditional `development-codex-resume` Job was installed on `main`, then removed by [PR #1181](https://github.com/physicslu/plasma/pull/1181) on 2026-10-27. Only the standalone offline research fixture and its fake-Codex unit tests remain. Ordinary Path 3 uses one owner-authenticated Codex Job with native tools; [the current contract](plasma-path3-direct-hardware-tools.md) is authoritative.

## Engineering decision

There are two distinct kinds of debug continuity:

1. **Within one Path 3 Job (already supported):** Codex independently iterates Code → Test → Fix → Retest within the same `exec` process. Its context is continuous for that process; no extra Dispatcher retry job is created.
2. **Across two independent Codex processes / Jobs (historical CPU-only experiment, now retired from Runtime):** `codex exec resume <thread-id>` may restore the same dialogue. Simply recording the first `thread.started.thread_id` does not prove resume succeeded. Git source pin, task/owner binding, sandbox policy and working files must remain valid in any separate research experiment.

**This historical Gate 1 demonstrated the host-side probe contract** using deterministic offline fake-CLI tests and, after the Owner's explicit SWPC-specific Gate 1 scope revision, **one real SWPC interactive-user Codex CLI NEW → FAIL → RESUME → PASS execution** (Owner-provided output; see evidence below). That reported test covered two consecutive Codex processes in one manual wrapper, **not** resumption across GitHub Actions Jobs. The later exact CPU-only Cross-Job workflow fixture was removed by #1181; neither it nor general-purpose Cross-Job Resume is a current Path 3 Runtime capability.

## Continuous debugging example: Page-boundary off-by-one

The disposable `.plasma-path3-resume-probe/` directory contains:

- `mock_page_chunks.py`: pure CPU byte-array page splitting with an intentionally wrong `range(0, len(data) - 1, page_size)`. A trailing one-byte page is silently dropped. This is **mock image slicing**, not real IC programming or electrical control.
- `test_mock_page_chunks.py`: Python standard-library `unittest` checks 0, 1, 7, 8, 9, 15, 16, 17, 24, 25 byte lengths and invalid page size. Initially FAIL.
- `resume-proof.txt`: written only during the second turn. It must contain a random synthetic 128-bit challenge first shown **only in the first turn prompt**, not in any on-disk file. The resume prompt does not repeat the challenge.

Expected test flow:

| Stage | Command / action | Expected evidence |
| --- | --- | --- |
| Preflight | exact pinned Git HEAD, clean isolated checkout, fixture baseline unittest | baseline **FAIL**, no preexisting probe directory |
| NEW (turn 1) | `codex exec --json -` under the separately checked historical operator isolation; review bug **without editing files** | valid UUID `thread.started`, `turn.completed` usage, code still FAIL, challenge not written to files |
| RESUME (turn 2) | `codex exec --json resume <exact UUID> -`, same cwd; operator must independently verify sandbox/network restrictions | **same** `thread.started` UUID; source fixes off-by-one; original `unittest` PASS; proof contains exact first-turn challenge |
| Admission verdict | independent subprocess/unit tests + challenge check + Git status | **PASS only if all above succeed**, otherwise FAIL; raw prompts/transcripts are never saved |

Strict negatives: new thread after resume → `RESUMED_THREAD_MISMATCH`; fixed code but challenge missing → `CHALLENGE_NOT_RECOVERED`; altered test → `TEST_MODIFIED`; first turn unexpectedly fixes issue → `FIRST_TURN_PREMATURE_FIX`; changed Git ref or edits outside scratch directory → `UNAUTHORIZED_WORKSPACE_CHANGE`; expired/missing ID/usage → explicit failure. No automatic retries, new Session fallback, or hardware/privilege escalation.

### Why the one-time challenge matters

A second **fresh** agent could simply inspect the file and repair a trivial bug. That would not show dialogue continuity. The second prompt therefore does not contain the synthetic challenge and the first turn may not persist it. Both **same resumed UUID and the exact previous-turn challenge** are necessary; a successful Python test alone is insufficient. This is evidence of first-turn context carryover, *not* proof of any specific hidden reasoning mechanism.

## Offline test and real Host-only invocation

The retained `Path3SessionResumeHostOnlyProbe` suite in `scripts/tests/test_plasma_development_dispatch.py` injects a **fake Codex subprocess**. It checks NEW → FAIL → RESUME → PASS and negative cases including UUID mismatch, missing challenge, premature success, first-turn failure, dirty source and missing telemetry. **No model is called by these unit tests**, and the probe is not a workflow or Dispatcher entrypoint. Host-only CI success is synthetic evidence, **not** `SWPC_RESUME_PASS`.

**Historical manual invocation example (not a current Path 3 procedure):** The Owner executed this once on SWPC as an unprivileged interactive user inside a restricted Bubblewrap mount namespace with an isolated clean Git Worktree, rather than as the SWPC GitHub Actions Runner. Do **not** run the raw CLI example below on a privileged or unisolated SWPC host; the actual Owner-approved SWPC run used a separate outer Bubblewrap launcher and a dedicated Codex session store. This command is only the underlying inner probe:

~~~bash
# Only in an explicitly authorized disposable local checkout, after reviewing the CLI version:
python3 scripts/plasma_path3_session_resume_probe.py \
  --manual-host-only \
  --repo "$PWD" \
  --expected-head "$(git rev-parse HEAD)"
~~~

Running it creates a fresh untracked `.plasma-path3-resume-probe/` directory and owner-only `receipt.json`, does not commit or push, and refuses to overwrite an existing probe. The caller must review the local source, stdout hashes and receipt; never commit raw Codex rollout data. A failed attempt remains auditable rather than triggering a hidden retry. A nonzero exit or missing real `thread.started` is FAIL, not automatically recovered with `--last`.

**Sandbox caution:** Some Codex releases do not accept `--sandbox` on `exec resume` and may not preserve the original explicit policy when resuming. **The retained probe does not set `--sandbox` or network policy in either Codex command**; its effective policy depends on the invoking operator's configuration and any separate outer isolation. For the reported historical SWPC run, the Owner separately checked Bubblewrap OS-level mount isolation (`bubblewrap 0.6.1`), with no real device nodes or primary project tree visible in that namespace. These checks do **not** prove a complete host or network security boundary: model connections remained possible and a read-only model authentication file was available to the isolated process. No privileged SWPC GitHub Runner/HIL worker was invoked. The current Path 3 Runtime instead explicitly pins its own Codex sandbox policy per the [current contract](plasma-path3-direct-hardware-tools.md).

## Real SWPC Codex Direct evidence — Owner-reported 2026-10-23 (Asia/Taipei)

**Evidence status: OWNER_REPORTED / NOT_INDEPENDENTLY_VERIFIED.** After reviewing the SWPC preflight (interactive UID 1000, `codex-cli 0.163.0`, Bubblewrap 0.6.1 available, inspected isolation namespace) and a Git-HTTPS fetch of the exact candidate commit, the Owner ran **one** manual CPU-only probe in an isolated detached Worktree. This was **not** a GitHub Actions Path 3 job or an automatic SWPC dispatch. The reviewer has the complete sanitized console receipt supplied in conversation but **has not independently read the host files, private Codex sessions, model API telemetry or raw source output**. This changes real CLI status from `NOT_RUN` to **OWNER_REPORTED_PASS**; it does not certify all actual hardware/network isolation properties or cross-Job functionality.

| Evidence field | Owner-reported value |
| --- | --- |
| PR candidate Git HEAD | `e63d44efe6d56ed4a6edd0fdf5c2fc2ce660c6d9` |
| Codex CLI / Bubblewrap | `codex-cli 0.163.0` / `bubblewrap 0.6.1` |
| Execution scope | SWPC unprivileged interactive shell + detached Worktree + restricted Bubblewrap; **not** self-hosted Runner |
| Preflight host check | `FILESYSTEM_AND_DEVICE_ISOLATION=PASS` (Owner console) |
| Case | `page-boundary-off-by-one`; single NEW / one RESUME |
| Before / after NEW / after RESUME unittest exits | `1 / 1 / 0` (first two **expected FAIL**, final **PASS**) |
| Codex phases | `COMPLETE / COMPLETE` (both subprocess calls returned exit 0 as checked by probe) |
| Thread continuity | `same_thread=true` |
| First-turn-only challenge | `context_continuity=VERIFIED` |
| Thread identity SHA-256 (not raw UUID) | `66b8a1fa03529098eed44f05909b6c85e1238a43c262b08ebe0d7b78adfb2e72` |
| Probe result / program exit | `PASS` / `PROBE_EXIT_CODE=0` and `TEST_EXIT_CODE=0` |
| Failure reason | `null` |

**Token usage**, from two genuine `turn.completed` event receipts as reported by Owner; Input **already includes** Cached:

| Counter | NEW | RESUME | Total |
| --- | ---: | ---: | ---: |
| Input Tokens | 57,554 | 119,646 | **177,200** |
| Cached Input | 49,536 | 110,080 | **159,616** |
| Non-cached Input (Input − Cached) | 8,018 | 9,566 | **17,584** |
| Output | 319 | 763 | **1,082** |

**Acceptance rationale:** The probe's own checks require the same `thread.started` UUID in both processes, no premature repair, an unchanged test file, no out-of-probe Git edits, a failing test before and after the diagnosis-only turn, a repaired test after Resume, and byte-for-byte recovery of a 128-bit challenge that appears only in the first prompt. A **fresh second Session that merely fixes the obvious bug would not satisfy the challenge**. It is concrete evidence of reported cross-process conversation continuity, but not a controlled measure of context/cache causality and not evidence of resumption across separate GitHub Jobs. Second-turn cumulative input exceeded first-turn input; the 177,200 total is a two-turn cost, not a claim of savings versus an independent fresh-session repair.

**Source and evidence boundaries:** The sanitized JSON remains in the Owner's **isolated local Worktree** under `.plasma-path3-resume-probe/receipt.json`, with a separate Owner-local result log; neither is uploaded or independently verified. Do not publish operator-specific absolute paths or private hostnames. Do not archive actual UUID, secret challenge, `auth.json`, rollout JSONL, raw prompt or token. **Historical SWPC two-Job acceptance was NOT_RUN; that integration is now RETIRED from the trusted Dispatcher and workflow (#1181).** This historical evidence does not authorize more model runs or automatic retries.

## Historical considerations for any new proposal (not implemented or authorized here)

A separate historical Gate 1 applied to the subsequently retired exact CPU-only Cross-Job fixture. Any *new* general-purpose Resume proposal would require new owner authorization and implementation. It would need session provenance and storage checks **for the exact Worker owner**, task/work-order digest, Git source SHA/PR HEAD, Git tree/working-diff identity, consistent sandbox/permissions, lease/ownership and timeout/failure semantics. Persistent Runner may erase or relocate original Session rollouts; an ID without matching stored context cannot be trusted. Never load a private session rollout into GitHub Artifacts or put credentials/prompts into receipts. No historical Resume experiment supplies new hardware authority.

Suggested policy: resume only an **unfinished, still-approved Work Order** whose exact immutable source, task and owner match; start fresh on unrelated tasks or after a closed/merged work item. Maintain bounded numeric total/cached/noncached/output Token telemetry to understand context growth. No third owner approval gate.
