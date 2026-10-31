# PLASMA Codex Token Optimization — P1 Gate 1 Inventory

**Scope:** Host-only source audit of P1 items. **Pinned main:** `833a0f577c3697d891629c405d91267c05c2b476`. PR #1227 was closed without merge; this is a separate, minimal audit, not a revival of that PR.

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

## Document-only next actions

1. Inventory inbound links to current AGENTS, full contract, Path 2/3 rules, ADRs and retired documents; classify authoritative vs historical references.
2. Build a paragraph-level duplicate/contradiction list, separating shared safety requirements from Path-specific or device-specific implementation detail.
3. Correct stale PR #1226 Draft labels and broken references only after verifying their targets; retain the two Owner gates and actual runtime safeguards.
4. Do not add a shared AGENTS.override.md or make any runtime/CI changes without evidence and separate authorization.

## Acceptance and exclusions

This inventory records evidence and defers unsafe transformations. No Codex run, new Runner, override file, Workflow modification, merge, deployment, SWPC/Z2/DUT/FPGA operation, or measured Token reduction is claimed. Actual changes require their own Gate 1 scope and Gate 2 approval.
