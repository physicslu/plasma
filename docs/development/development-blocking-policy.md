# Development Mode — Three Shared BLOCKING Decisions

Paths 2 and 3 share the trusted Dispatcher and SWPC Runner. Authorized
hardware stages use the trusted-main `plasma_development_stage_transport.py`
and the protected Z2 root entry; a Codex prompt is not a privileged executor.

1. **B1 — Authorization and source**: only a bounded owner-approved Work Order and immutable reviewed executable/source may run.
2. **B2 — Current Z2 hardware safety and recovery**: lock, effective root, ownership of MMIO and drivers, same boot, pinned candidate/recovery image and durable restoration state must be valid before physical operations.
3. **B3 — Real result and fail-closed progression**: authentic root-sourced receipt, correct stage/return code, read-only native aligned MMIO, no unsafe retry, and stop on SIGBUS, timeout, unreaped child or uncertain restore.

These are three *policy decisions*, **not three total predicates**. Device integrity checks inside B1–B3 remain mandatory and cannot safely be removed.

## Historical PR #1097 runtime simplification evidence

At the time of GitHub Run 39573288065, Codex counted 233 explicit rejection
sites across seven sources, versus 212 after its original patch (21 fewer).
The historical candidate removed repeated workflow event/runner checks (14),
Z2 service-availability and descriptive risk-label assertions (2), a duplicate
environment acknowledgement (1), duplicate orchestration auto-stage assertions
(2), a repeated full-HIL aggregate result assertion (1), and a report-
completeness execution stop (1). SSH prompt-presence was also removed as an
atomic predicate, while verified remote exit and strict root receipts remained.

**Historical safety adjustment (PR #1097, since superseded):** that revision
retained a report-completeness stop for its then-existing staged hardware Path 3
branch, so the merged reduction was **20**, not 21. Subsequent consolidation
and PR #1108 removed the generic automatic post-Codex stage branch. This
paragraph documents the old measurement, **not** the current admission model.
Report completeness is now review metadata; it cannot authorize hardware.

All current Z2 firmware/image, root-owned source, Manager status, UIO/MMIO ownership, stage allowlists, protected restore, durable UNKNOWN state and native read32/SIGBUS/reaping checks remain enforceable. No actual hardware qualification is implied by hosted tests.

Run: https://github.com/physicslu/plasma/actions/runs/39573288065

## Current shared Development runtime consolidation

This consolidation supersedes the earlier report-completeness execution
stop described in the historical run above.

The active `issue_comment` Development route now treats B1 authorization as
an immutable owner event plus reviewed source/registry and exact action.
Runner/hostname labels, run-attempt numbers for ordinary Work Orders and
host builds, and an extra Path 3 environment acknowledgement do not add
execution authority. A2 retains its explicitly approved **one-shot** claim;
this is part of its action scope, not a general rerun policy.

The shared workflow routes by the authorized Path/capability. It does not
repeat the task catalogue or require an unrelated A2 claim job to be skipped.
The active generic Path 3 Workflow executes Codex and captures its evidence;
it has **no automatic post-Codex hardware stage job**. An owner-approved
physical operation still requires an available trusted Stage Transport route,
B1/B2/B3 checks and an authentic protected Z2 root receipt. Generic dynamic
Path 3 hardware delegation remains unimplemented; if the route is unavailable,
report `NOT_RUN`. Report completeness is review metadata, not stage authority.

A successful CPU-only command may write diagnostics to stderr. Its return
code and expected stdout digest still determine the result, and stderr is
preserved. Inert automation options do not block a single-stage adapter or
add stages. Build evidence no longer requires the decorative `m1=NO_GO`
label; actual BIT/HWH/report/log checks remain.

Development Path 2/3 use `scripts/plasma_development_stage_transport.py` from
trusted main dispatcher code. The installed SWPC bridge and approved-sha PIN
are unused; existing files are left untouched. `swpc_bridge_deployment` is
obsolete and rejected in Work Orders. No installer, PIN update, new credentials
or service is required. Event `GITHUB_SHA` authenticates trusted checkout;
worker admission verifies exact candidate checkout and Work Order digest.
For branch work the worker independently fetches live GitHub PR metadata and
checks exact HEAD, same repository, owner and base main before executing.
A caller-supplied SHA is not authorization. Both Paths use the same fixed
stage allowlist, enrolled private credentials and pinned host keys. Candidate
Python is never imported by the stage executor; this does not claim OS
isolation from other processes running as the same worker account.
The Z2 root entry and protected on-device source manifest remain mandatory.

Current Manager/driver/MMIO ownership, protected source and recovery,
native aligned read-only register access, durable UNKNOWN/crash state,
SIGBUS/timeout/reaping handling and unique real stage receipts remain
subordinate B1/B2/B3 requirements. Historical one-shot/qualification modules
are not silently activated by this Development change. Host regressions do
not prove deployment, Vivado execution or HIL acceptance.

Transport failures now cross the shared Path 2/3 adapter as exact codes from
`SAFE_FAILURE_CODES`, including local enrollment, SSH reachability/host key/
authentication, invalid receipts, timeout and uncertain child ownership.
Existing explicit lower-level `Blocked` codes remain distinct; unknown exception
text becomes `UNKNOWN`. No exception text, PTY output or connection identity is
exported. Exact protected-source failure diagnostics may categorize manifest
blocks or `F1B_IMAGE_NOT_LOADED`; these are failed-command diagnostic classes,
not verified current image or recovery state. Arbitrary remote stderr is never
a successful root receipt. Nonzero exit, malformed/duplicate markers, SIGBUS or
unreaped children cannot authorize a following stage. Root guards and the
exit-zero, stage-specific receipt requirement remain mandatory. A timeout needs
manual state review; a failure code never authorizes an automatic retry.
