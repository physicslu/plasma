# Development Mode — Three Shared BLOCKING Decisions (current Path 2 / Path 3)

Paths 2 and 3 share owner/SHA-gated trusted Dispatcher admission and may
share the SWPC Runner, but **do not share a mandatory hardware Stage Transport
or fixed Stage allowlist**. Path 2 guarded-hardware Work Orders use
`operator-cli`; Path 3 Codex directly chooses native CLI/Sigrok/SSH tools
within its authorized task. `plasma_development_stage_transport.py` and the
Protected Z2 Root Entry remain separate, guarded lower-level mechanisms for
explicit operations, not automatic Dispatcher capabilities. A Work Order or
Codex prompt never grants Linux Root, sudo or physical safety clearance.

1. **B1 — Authorization and source**: only a bounded owner-approved Work Order and immutable reviewed executable/source may run. The live Dispatcher rejects `z2-root-operation` as a Work Order Capability.
2. **B2 — Current hardware safety and recovery**: before applicable physical actions, verify actual OS privileges, device/driver exclusivity, legal electrical state, current-boot identity, image/Manifest provenance and safe recovery. Protected FPGA Manager/MMIO operations additionally require their existing Root guards and locks.
3. **B3 — Real result and fail-closed progression**: evaluate authentic native command/driver output and exact exit status; for a protected Root operation require its validated Root receipt and stage semantics. Stop on SIGBUS, timeout, unreaped child, unknown in-flight state or uncertain restoration; never promote an `operator-cli` exit 0 alone to hardware PASS.

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

Existing Z2 firmware/image, root-owned source, Manager status, UIO/MMIO
ownership, protected Root operation selection, restore, durable UNKNOWN state
and native read32/SIGBUS/reaping guards remain enforceable **when those
protected operations are explicitly invoked**. A historical fixed Stage
allowlist is not a new Work Order admission requirement. Hosted tests do
not establish actual hardware qualification.

Run: https://github.com/physicslu/plasma/actions/runs/39573288065

## Current Development runtime boundaries (after Path 3 #1181 and Path 2 retirement)

The active Owner Issue #981 `issue_comment` route uses a trusted-main
Dispatcher, immutable source/PR HEAD checks, Work Order SHA256 and bounded
capability admission (B1). A caller-provided SHA, Runner label, optional
monitor summary or Codex prompt is not authorization. Candidate source is
verified against the exact same-repository PR and its current HEAD; it is
not imported into the trusted Dispatcher. The special A2 one-shot claim
remains separate, not a generic execution gate.

**Current Path 2 Capability selection:**

- `cpu-only` — reviewed Python under `scripts/`, Host-only Bubblewrap with
  no network/devices, bounded argv/timeout and stdout-digest or explicit
  exit-code verification. Process exit 0 is not physical evidence.
- `vivado-host-build` — a trusted-event-main or PR-HEAD-pinned Host build for a project with a
  reviewed `host-build.json`, build Tcl and project-specific artifact/HWH
  verifier. A syntactically valid project path alone is insufficient. The
  two legacy fixed Registry Build tasks remain F1-B-only compatibility
  routes. Neither route grants Z2 download or Root authority.
- `operator-cli` — owner-approved `scope: guarded-hardware` with a checked-in
  Python `script`, `argv` and bounded `timeout_seconds`. The existing
  non-root SWPC Runner executes that script directly, **not** a fixed
  `operation: download|test|restore` Dispatcher Stage. Required physical
  B2/B3 and privilege checks belong to the reviewed script and any
  independently invoked protected tool. Exit 69/77 is a failed job with an
  explicit NOT_RUN reason; exit 0 is evidence for review, not hardware PASS.

**Retired Path 2 Work Order:** `z2-root-operation` is rejected by the live
Dispatcher (`RETIRED_PATH2_ROOT_OPERATION`). The historical
`plasma_path2_runtime_integration.direct_root_operation()` helper and
`plasma_development_stage_transport.py` remain for compatibility/offline
tests and explicitly scoped lower-level protected use. Neither is a
mandatory intermediary for `operator-cli`. The independent two-argument
Z2 Protected Root Entry retains its OS/sudo, source-commit SHA, companion
Image/Manifest, ownership, current-boot, receipt and recovery checks.
Scripts do not inherit Root authority from Work Order approval.

**Current Path 3:** The owner/SHA-gated generic Codex Job directly invokes
native SWPC CLI, Sigrok, USB/TTY and enrolled Z2 SSH tools within the
approved objective and its effective Linux permissions. Ordinary Codex
execution pins `workspace-write`; exact Owner hardware Work Orders may
select `guarded-hardware-no-sandbox`. Path 3 has no Host Supervisor,
fixed Stage/Profile/Probe intermediary, Cross-Job Resume Job or automatic
post-Codex hardware Stage. Its direct privileged Z2 actions still require
actual OS authorization and the same applicable B1/B2/B3 checks; no Path 2
Work Order or Stage Transport is implicitly inserted.

The shared Workflow records the actual process exit and bounded evidence.
For CPU-only work, stderr diagnostics are compatible with stdout-digest
verification. For Vivado, actual BIT/HWH/report/log qualification still
applies. Report completeness is review metadata, not a hardware permission
check. No source-level or hosted test implies current SWPC deployment,
FPGA image load, DUT access or physical HIL PASS.

**When the retained protected Stage Transport is explicitly used**, its
`SAFE_FAILURE_CODES` classify enrollment, SSH host key/authentication,
invalid Root receipts, timeouts and uncertain child ownership. Existing
lower-level `Blocked` codes remain distinct; unknown exception text becomes
`UNKNOWN`, not a successful receipt. Protected-source diagnostics such as
`F1B_IMAGE_NOT_LOADED` are failure categories, not verified current hardware
state. Arbitrary stderr, nonzero exits, malformed/duplicate receipt markers,
SIGBUS or unreaped children never authorize progression. A timeout requires
manual state review; no failure code authorizes an automatic retry. These
transport semantics apply to explicit protected calls, **not** to every
Path 2/3 native CLI operation.
