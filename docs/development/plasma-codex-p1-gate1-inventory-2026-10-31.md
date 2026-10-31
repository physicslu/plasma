# PLASMA Repository Documentation Reorganization — P1 Gate 1 Inventory

**Scope:** Repository-wide documentation governance, de-duplication, canonical authority and historical cleanup (Host-only source audit). Codex/Path 3 are only examples, not the project boundary. **Pinned main:** `833a0f577c3697d891629c405d91267c05c2b476`. PR #1227 was closed without merge; this is a separate, minimal audit, not a revival of that PR.

## P1-A: AGENTS.override.md decision

- Root `AGENTS.md` is 22,818 characters at the pinned main; it explicitly delegates relevant full-contract sections on demand.
- No root `AGENTS.override.md` exists in the checked root listing.
- **Decision: do not add a shared root override.** An override could supersede repository safety/authorization instructions and cause divergence across Desktop and Path 3. Its actual load precedence and behavior must be verified against the pinned Codex CLI version before any local experiment.
- Use task-specific, scoped prompts and the existing AGENTS on-demand rule. Never instruct Codex to skip required privileges, hardware, deployment, electrical safety, Root Guard, or architecture clauses.

## P1-B: Historical documents, ADR, and duplication

- Canonical shared entrypoint: `AGENTS.md`; full detailed contract: `docs/development/plasma-autonomous-development-contract-full.md`; Path-specific clauses: `plasma-codex-path2-execution.md` and `plasma-codex-path3-execution.md`.
- The existing ADR index is `docs/adr/README.md`; the observed directory has ADR-0001, ADR-0002 and ADR-0003. Do not infer that other ADR numbers do not exist elsewhere; inspect references before declaring authority.
- `plasma-path3-cross-job-resume-gate1.md` and `plasma-path3-session-resume-host-only-poc.md` explicitly label retired/historical mechanisms. `plasma-legacy-codex-issue981-trigger-retirement.md` is a historical trigger-retirement record.
- **Decision: no file deletion, relocation, or replacement authority map in this Gate 1.** Audit inbound references and paragraph-level overlap first; the canceled PR #1227 is not a basis for new edits.
- Existing `docs/README.md` still describes merged PR #1226 entries as “Gate 1 Draft”; correct those labels only after reference review in a separate focused change.

## P1-C: Device Catalog CI consolidation feasibility — DEFERRED BY OWNER

**Owner scope update:** The 245 Device Catalog workflows are explicitly **out of scope** for this PR and current P1 work. Retain the following counts as historical inventory only; do not inspect workflow internals, propose Matrix conversion, change CI or create a separate workflow task without new Owner approval.


At the pinned `main`, GitHub `.github/workflows/` directory listing shows:
- **321** YAML workflow files in total.
- **245** filenames beginning with `device-catalog-`.
- **21** filenames containing `phase` (not a count of active jobs or triggers).

These are **filename counts only**, not execution frequency, redundancy, cost, or safe matrix-compatibility evidence. The uploaded guide's “~141 workflows” estimate is not current repository inventory.

**No bulk matrix rewrite is authorized from filename counts.** Before proposing a Matrix Workflow:
1. Classify `on` triggers, required-check names, permissions, secrets, concurrency, runner and path filters.
2. Group only semantically identical workflows; retain PR-required status-check compatibility.
3. Compare baseline and proposed positive/negative fixtures, duration, and GitHub Actions minutes.
4. Preserve vendor/ICPN evidence isolation, source locks, non-production qualification and Gate 2 controls.
5. Deliver a separate source-only PR with an explicit migration/rollback plan; no CI edits in this audit.

## Repository-wide document reorganization: authority and information architecture

- **Shared governance:** AGENTS.md and the detailed development contract; identify normative clauses, their canonical owner and safe cross-references.
- **Architecture:** ADRs, architecture specifications, and current implementation documents; distinguish accepted decisions from proposals and historical experiments.
- **Execution paths:** Path 1, Path 2, Path 3 and Desktop tooling; route-specific detail stays on demand, without making Path 3 the primary organizing axis.
- **Product and IC support:** catalog/provider/qualification and raw evidence documents; distinguish runtime authority, qualification evidence, research notes and retired snapshots.
- **Operational documentation:** deployment, FPGA/PS, programming, CI and HIL runbooks; avoid duplicated procedures and stale links while retaining safety invariants.
- **Archive:** mark retired/obsolete documents as historical before any move; verify inbound links, GitHub references and CI/tests. Do not delete based on age alone.

**Deliverables:** document inventory and classification, source-of-truth ownership matrix, overlap/conflict and inbound-link report, prioritized move/merge/deprecate plan, link validation and regression evidence. This Gate 1 does not itself authorize wholesale deletion or migration.

## Document-only next actions

1. Inventory inbound links to current AGENTS, full contract, Path 2/3 rules, ADRs and retired documents; classify authoritative vs historical references.
2. Build a paragraph-level duplicate/contradiction list, separating shared safety requirements from Path-specific or device-specific implementation detail.
3. Correct stale PR #1226 Draft labels and broken references only after verifying their targets; retain the two Owner gates and actual runtime safeguards.
4. Do not add a shared AGENTS.override.md or make any runtime/CI changes without evidence and separate authorization.

## Acceptance and exclusions

This inventory records evidence and defers unsafe transformations. No Codex run, new Runner, override file, Workflow modification, merge, deployment, SWPC/Z2/DUT/FPGA operation, or measured Token reduction is claimed. Actual changes require their own Gate 1 scope and Gate 2 approval.

## Gate 1 repository document inventory — first verified pass

This section records direct GitHub directory-listing counts at pinned `main`; these are **not** recursively aggregated totals and do not establish whether a document is active, obsolete, or duplicative.

| Directory | Immediate entries | Immediate Markdown files | Subdirectories |
| --- | ---: | ---: | --- |
| `docs/architecture/` | 95 | 94 | none |
| `docs/development/` | 90 | 89 | `evidence/` |
| `docs/deployment/` | 25 | 25 | none |
| `docs/adr/` | 4 | 4 | none |
| `handover/` | 34 | 34 | none |
| `docs/operator/` | 1 | 1 | none |
| `docs/testing/` | 1 | 1 | none |
| `docs/evidence/` | 13 | 0 | 13 evidence subdirectories |
| `docs/archive/` | 1 | 0 | `ci-workflows/` |
| `docs/engineering/` | 1 | 0 | `ci/` |

**Verified minimum:** 248 immediate Markdown files across the seven flat/direct document locations listed above (94+89+25+4+34+1+1); not the repository-wide total. Nested evidence, engineering and archive contents require separate classification. Do not treat YAML/JSON evidence as obsolete documentation.

### First-pass authority candidates and ambiguity

- `docs/adr/README.md` indexes three immediate ADR decision files (0001–0003). Audit cross-references to other ADR-like identifiers before declaring the index complete.
- `docs/architecture/` contains `openocd-software-qualification-v1.md` through `v7.md`. **Seven versioned files are a review candidate, not proof of seven redundant contracts**: determine supersession, inbound references and whether each contains immutable qualification evidence.
- `docs/architecture/device-catalog-ci-coverage-map.md` is a likely large reference, but workflow consolidation is explicitly out of scope.
- `docs/evidence/` is a structured collection of device-specific evidence folders; preserve raw evidence and receipts, even if a current guide links to them.
- `docs/archive/ci-workflows/` contains archived workflow subtrees. Do not re-enable, delete, or migrate them in this PR.

### Required next evidence before any move or deletion

1. Recursive tracked-file inventory, including `docs/evidence/`, `docs/engineering/`, `docs/archive/`, root Markdown, and `specs/`.
2. For each candidate: current authority classification, duplicate/supersession proof, backlinks, ADR/CI/test references, and proposed replacement URL.
3. Resolve conflicts by explicit owner approval and source precedence; retain immutable evidence and signed/hash-locked material.
4. Perform link-integrity and documentation CI after each bounded change. No bulk archival move based on title/version alone.
