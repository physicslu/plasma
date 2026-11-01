# PLASMA Codex Context and Documentation Governance — Gate 1 Audit

**Status:** DRAFT, host-only, documentation-only.  
**Pinned main:** `c58621afe896e6a6f57fe712c27ffcbc06a6f0e8`.  
**Applies to:** Desktop/local Codex CLI and trusted GitHub Path 3 Codex.

## Current evidence

- Root `AGENTS.md` is the primary instruction entrypoint (~30 KB in pinned main). The detailed contract (~69 KB) remains normative, read on demand. Neither file size proves actual model context loading.
- PR #1128 previously reduced AGENTS and introduced on-demand detailed clauses. Do not repeat or reverse that migration; see `plasma-path3-token-optimization-rca-closure-2026-10-23.md`.
- `docs/development/codex-benchmark-usage.md` and `scripts/plasma_codex_benchmark_usage.py` already provide an offline, allowlisted numeric telemetry extractor for a selected local rollout. The historical Direct comparison ran on Linux, not independently verified Mac Desktop.
- Path 3 dispatcher already collects Codex token usage; model request count and effective model/effort remain NOT_AVAILABLE without verified runtime evidence.
- Cross-job session resume PoC is retired by PR #1181. Do not restore intermediate supervisor/relay/adapter layers.
- Historical documentation is not necessarily obsolete or safe to delete. Archive changes require link, authority, and evidence-dependency review.

## Authority model

| Document class | Authority | Action |
| --- | --- | --- |
| Root AGENTS.md | Current mandatory instruction entrypoint | Audit redundancy while preserving approval and safety requirements |
| Detailed autonomous-development contract | Normative on demand | Preserve domain-specific rules and stable references |
| Current ADRs, Root Guard, deployment/hardware contracts | Normative when applicable | Validate against latest main before changes |
| Historical resume PoC and retired triggers | Historical evidence only | Retain retirement labels and traceability |
| Unclassified phase docs, catalog and CI workflows | Unverified | No deletion or consolidation before dependency audit |

## Common optimization work

1. Map current authority and duplicate sections; prefer one normative source with links instead of repeated clauses.
2. Add concise relevant-module and acceptance-test guidance to task prompts, without restricting native tools or bypassing relevant safety clauses.
3. Preserve full raw test/evidence artifacts; use concise excerpts for model reasoning when sufficient.
4. Compare tokens per accepted work order on matched host-only tasks; track non-cached input separately and never double-count cached input.
5. Keep all local Codex rollouts, prompt text, credentials, session identifiers and raw logs private; only allowlisted numeric summaries may be shared after review.

## Environment-specific work

**Desktop Codex CLI:** reuse existing offline extractor; verify actual local host, CLI version, selected rollout, model and reasoning effort when supported; do not edit personal CODEX_HOME or create a global AGENTS.override.md.

**Path 3:** extend existing usage receipts with supported numeric per-turn deltas, bounded tool-event counters and elapsed time; explicitly mark unsupported metrics NOT_AVAILABLE; avoid extra Codex retries or new middleware.

## Gate 1 acceptance and boundaries

- This PR changes documentation only; no executable code, CI workflows, permissions, runtime or hardware.
- Preserve exactly two owner approval gates and existing Owner/SHA, Root Guard, Linux permissions and recovery requirements.
- No Codex invocation, SWPC/Z2/DUT/FPGA access, deployment, workflow consolidation or automatic document deletion.
- Before implementation, prepare precise diffs and host-only positive/negative tests; no claimed token savings without controlled measurements.
- Keep Draft pending Gate 2 review; do not merge automatically.

## Next work packages

- WP1: Read-only inbound-link/duplicate audit for AGENTS, full contract, ADRs and historical docs.
- WP2: Minimal documentation authority index and references, preserving normative semantics.
- WP3: Host-only telemetry improvements in a separate scoped implementation PR.
- WP4: Local Desktop-vs-Path3 matched task benchmark after approval and quota availability.


## WP1 initial evidence: root AGENTS size concentration

Read-only section inventory at pinned main: `AGENTS.md` has 165 physical lines and ~30,001 UTF-8 characters. The largest section, `## 1A. Prototype-first engineering policy (normative)`, is ~12,035 characters (~40% of the entrypoint); `## 1. Project purpose and canonical domain` is ~3,225; `## 11. Autonomous task execution contract` is ~2,837. Section 1A includes owner-approved Path 2/3 sandbox, hardware, Root Guard, FPGA image handling, native tools and real safety conditions. **Do not truncate or archive it merely because it is long.**

Prior repo-first reduction in PR #1128 shrank AGENTS from 62,093 to 17,285 bytes; present ~30 KB indicates subsequent growth, not proof of duplication. Next audit must compare added clauses since #1128 against normative contract and current code before proposing any text removal.

### Candidate safe-first document changes (not yet applied)

- Add a small task-to-authority navigation table; verify it introduces no new approval or privilege semantics.
- Replace only demonstrably identical repeated explanatory passages with links to one normative source. Do not replace critical safety guards with vague pointers.
- Keep all explicit retirement banners for cross-job resume and historical Issue #981 entrypoints.
- Keep Desktop and Path 3 entrypoint instructions aligned in the repository; do not add a global AGENTS.override.md.

### Host-only acceptance cases for subsequent implementation

1. Desktop task with no hardware scope: required AGENTS and task-relevant detailed clauses remain discoverable.
2. Path 3 owner-bound hardware task: sandbox, owner SHA/digest, device ownership, Root Guard and rollback rules remain intact.
3. Negative: an outdated session-resume document cannot authorize a new Path 3 middleware/job.
4. Negative: a short prompt cannot override mandatory privileges, safety, deployment or electrical constraints.
5. Telemetry: duplicate cumulative snapshots are not double-counted; cached input remains a subset of input; missing request-count/model evidence stays NOT_AVAILABLE.
