# PLASMA Path 3 — Cross-GitHub-Job Session Resume, Gate 1 candidate

**Status: Gate 1 candidate, unmerged. GitHub-hosted tests simulate the Codex call; two real SWPC GitHub Jobs have not yet been observed.** This supplements [PR #1131 direct Host-only Resume evidence](plasma-path3-session-resume-host-only-poc.md). A real Direct CLI two-process test is not an acceptance of a cross-GitHub-Job mechanism.

## Problem and minimum change

The trusted Development Mode dispatcher originally ran exactly one fresh Codex CLI invocation per authorized Path 3 Job. A new Actions Job checks out a clean candidate repository and cannot assume prior uncommitted files, Codex Session rollout or prompt context survive. Merely reusing an old thread UUID is not a proof of coherent recovery.

This candidate **reuses** Issue #981, the existing generic dynamic Work Order, original `plasma-engineering-runtime-dispatch.yml`, `SWPC-plasma-codex` Runner and the trusted-main Worker Admission, without a new workflow file, runner, registry task ID, external database, or human approval gate. It adds:

- One exact, opt-in `continuity_probe: "page-boundary-v1"` on the dynamic `path3-codex` Work Order, **only with `scope: "host-only"`**. Other Path 3 tasks run with the unchanged one-Job Codex command.
- A trusted CPU-only stage adapter (`scripts/plasma_path3_cross_job_resume.py`) that creates a private, per-GitHub-run fixture on SWPC. It does not execute candidate-supplied Python, use sudo/SSH, access physical devices or change Git refs.
- One additional **job within the same shared workflow run** (`development-codex-resume`, with `needs: [development-authorize, development-codex]`). This is a **different GitHub Actions Job**, scheduled only after the first Job succeeded in recording its intentionally failing diagnostic turn, and using the existing Runner label.

The public Work Order must specify a bounded objective/acceptance and may optionally pin the open Owner PR HEAD by `pr_number` and `source_sha`. The exact same Issue comment, `comment_id`, Work Order digest, candidate SHA, trusted-main SHA and GitHub run ID are revalidated independently in both Jobs, avoiding a second comment with a different immutable request. The second Job does not run if the first fails.

**Example conceptual Work Order fields** (not a ready-to-post GitHub comment; source SHA / PR must be pinned to the actual live candidate):
~~~json
{
  "schema": "plasma.development.work_order.v1",
  "execution_path": "path3-codex",
  "capability": "codex-workspace",
  "scope": "host-only",
  "continuity_probe": "page-boundary-v1",
  "objective": "Diagnose the CPU-only byte-array page-boundary bug without fixing it in the first Job.",
  "acceptance": "In the second Job resume the original thread, fix the byte-array bug, recover the first-turn-only challenge, and pass unittest."
}
~~~

## Private state and exact continuation

The trusted adapter writes the following to an owner-private, local SWPC directory under the Runner account's user state root. This path is **not** a checked-out repository path, GitHub Artifact, model log, or untrusted candidate-supplied location:

| Item | First Job | Second Job |
| --- | --- | --- |
| Identity | Owner, original Issue comment ID, `GITHUB_RUN_ID`, `RUNNER_NAME`, trusted SHA, candidate SHA, Registry SHA256 and Work Order SHA256 | Exact equality required |
| Original fixture | Known `mock_page_chunks.py` with final-page off-by-one and unmodified `test_mock_page_chunks.py` | Same data verified before Resume |
| Codex context | Dedicated private `CODEX_HOME` with Session rollout; raw thread UUID stored in private manifest | Exact `codex exec resume <UUID>` from **the same mount-visible working directory** |
| Challenge | Random 128-bit hex provided in first prompt, only SHA256 retained in private manifest | Second prompt lacks the challenge; recovered proof must hash identically |
| Token usage | Valid `thread.started` and `turn.completed`; per-Job Input/Cached/Output | Same event validation, separate per-Job counters |
| Private manifest | `READY_FOR_RESUME` after expected diagnostic FAIL | Mark `RESUME_STARTED` **before invoking** the second Codex process; `RESUME_VERIFIED` only after all checks |

The adapter requires non-root execution, a clean exact-SHA candidate checkout in **each** Job, private state-directory permissions, a matching immutable metadata identity and source/test bytes. The model runs in a Bubblewrap mount namespace with a new `/dev`, no host repository mount and no host `/sys` tree. Only the private fixture and dedicated Codex Home are writable. Existing model authentication may be exposed **read-only** to the isolated CLI; never upload it or the raw session to GitHub. The model service needs network connectivity, so **do not claim a full network egress isolation policy**; Codex also explicitly requests `workspace-write` with workspace tool network disabled on both turns.

Failure codes are category-only (for example `RESUME_BINDING_MISMATCH`, `RESUME_WORKSPACE_HASH_MISMATCH`, `RESUME_THREAD_MISMATCH`, `RESUME_CONTEXT_NOT_RESTORED`). Any source/runner/run-id/comment-id mismatch, tampered test, changed Session ID, missing challenge, missing state, second attempt, nonzero Codex process or invalid telemetry fails closed; **no silent Fresh Session fallback and no retry**. The private state is retained for manual review rather than self-deleted on partial failures.

## Expected CPU-only end-to-end acceptance

| Job / Test | Evidence required | Result |
| --- | --- | --- |
| GitHub-hosted candidate CI | Contract, negative tests, module compilation, Workflow conditions and hosted simulator | **SIMULATED_PASS** — 94/94 dispatcher/resume unit tests on reviewed candidate; check latest PR HEAD before Gate 2 |
| GitHub Actions Job #1 `development-codex` | `NEW`, deliberate unittest exit 1 before and after diagnosis, valid UUID, `READY_FOR_RESUME`, real Run/Job ID and counters | **NOT_RUN** |
| GitHub Actions Job #2 `development-codex-resume` | `RESUME` same UUID, correct first-turn challenge, unchanged test, fixed source, unittest exit 0 and real Job ID | **NOT_RUN** |
| State / source negatives | Wrong original Work Order or Registry SHA, PR HEAD movement, Runner mismatch, dirty candidate, state missing, corrupted fixture, duplicate Resume | Pending |
| Hardware activity | All device/FPGA/USB/MMIO/Power/DUT work prohibited | **NOT_RUN** |

A genuine PASS requires **two different GitHub Actions Job IDs in one owner-authorized workflow run**, with the actual self-hosted Runner and sanitized receipts. Do not infer real SWPC results from the existing PR #1131 manual command or from synthetic tests.

## Pre-merge trusted-main activation constraint — blocking unless resolved

**The shared Development Workflow and the trusted Dispatcher execute from `main` for owner Issue #981 events**. An unmerged PR can supply a pinned candidate Work Order/source, but it cannot replace the trusted Dispatcher or activate a changed Workflow. Therefore even all-green PR CI alone **cannot** start the newly proposed second SWPC Job or stage adapter. Running the PR's candidate Dispatcher on SWPC by manually bypassing trusted-main admission is **not** an acceptable substitute.

The implementation can be reviewed in a Draft PR and GitHub-hosted CI now. **Real pre-merge cross-Job SWPC execution remains NOT_RUN unless a safe pre-merge trusted execution path is demonstrated that does not relax source/owner controls.** Do not merge without owner Gate 2, do not silently claim two real Jobs completed, and do not trigger a generic unbounded Path 3 Job as a workaround. This is a deployment/acceptance circularity, not a need for a third human Gate.

## Next engineering acceptance

1. Review the exact candidate delta and complete host-only tests, including both positive and adversarial cases. Do not start a SWPC Runner from PR CI.
2. Determine whether a currently trusted owner-approved pre-merge entrypoint can execute the vetted candidate stage without bypassing trusted-main authority. If none exists, report `SWPC_CROSS_JOB_NOT_RUN` as a Gate 1 blocker.
3. Only after an authorized genuine Run #1/#2 with both real Job IDs, sanitized evidence, and Code Review should this PR be assessed for Gate 2. Merge authorization is separate.
