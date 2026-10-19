# ICPN Catalog workflow rationalization — Gate 1, batch 1 (2026-10-19)

> **DRAFT PR ONLY — not an authorization to merge, dispatch Actions, deploy, or operate hardware.** This is an initial source-level inventory, **not** a completed run-history and dependency audit of all workflows.

## Gate 1 update — five proposed archive candidates, observed historical runs (2026-10-19)

Static trigger triage is **262/262**, but only the **five archive candidates** have now received branch/event-scoped historical run evidence. GitHub's repository Actions run listing returned all seven `push` runs for `agent/microchip-bulk-coverage-discovery-v1`, and two for `agent/microchip-research-recovery-v2`. Two of the former were separate *live canary* runs, **not** archive candidates; exactly **7 candidate runs** remain, with **4 successful and 3 failed**.

| Proposed archive Workflow | Observed candidate Push runs | Last observed conclusion | Important distinction |
|---|---|---|---|
| `microchip-all-lanes-sweep-once-v1` | [38357332332](https://github.com/physicslu/plasma/actions/runs/38357332332) FAIL; [38357451545](https://github.com/physicslu/plasma/actions/runs/38357451545) PASS | PASS, 12/12 sharded jobs, 12 raw artifacts | Does not certify complete Microchip denominator |
| `microchip-bulk-research-once-v1` | [38348043707](https://github.com/physicslu/plasma/actions/runs/38348043707) PASS | PASS | Workflow log explicitly says 7/16 batches partial/failed; only 137 queries independently replayed, 3,061 unreplayed/unattempted. **Success ≠ full coverage** |
| `microchip-live-evidence-10-replay` | [38348231778](https://github.com/physicslu/plasma/actions/runs/38348231778) FAIL | FAIL | Original replay failed; subsequent [crosslane Recovery Run 38348398967](https://github.com/physicslu/plasma/actions/runs/38348398967) successfully verified its ten queries |
| `microchip-crosslane-recovery-v1` | [38348398967](https://github.com/physicslu/plasma/actions/runs/38348398967) PASS | PASS | 10 source-backed queries and 151 exact-prefix research orderings; not Production admission |
| `microchip-recovery-v2` | [38373094121](https://github.com/physicslu/plasma/actions/runs/38373094121) FAIL; [38373429583](https://github.com/physicslu/plasma/actions/runs/38373429583) PASS | PASS, 8/8 source-pinned jobs, 8 raw artifacts | Retain partial/failed predecessor in audit trail |

Supporting structured evidence: `docs/engineering/ci/icpn-workflow-archival-run-evidence-2026-10-19.csv`. Relevant artifacts on these seven runs were non-expired at verification time; GitHub retention policy may cause future expiry. The historical evidence belongs to the **original GitHub-hosted research execution**, not this Gate 1 audit; no Workflow dispatch occurred during the audit.

**Archival proposition remains conditional**: all five YAMLs use exclusively old-branch/self-YAML `push` triggers, no `workflow_dispatch`, and no default-branch indexed callers beyond each YAML itself. Before Gate 2, still verify classic branch-protection required checks and off-repository/scheduled callers. Archive status does not constitute manufacturer coverage approval, ADR-0002 L1/L2 admission, hardware qualification, or production-write authority.

## Frozen baseline

- Repository: `physicslu/plasma`; branch: `main`; base commit `17382d889a7643dd9986639ab50601d65b4cbf12`.
- 336 total workflow YAMLs; 262 with `catalog` in their filename, of which 260 start with `device-catalog-`.
- Breakdown: ST/STM32 171, OpenOCD 31, NXP 30, Microchip 20, cross-cutting 10.
- Exact 262-row manifest: `docs/engineering/ci/icpn-workflow-inventory-2026-10-19.csv`. Each row records the immutable Git blob SHA and triage state.
- `.github/ci-workstreams.json` identifies four ICPN core workflows. `.github/device-catalog-ci-trigger-debt.json` limits Production-wide path ownership to four named validators and reports zero existing exceptions.
- Active branch Ruleset `Protect Plasma main` (20964250) has pull-request and review-thread restrictions, but no `required_status_checks` rule in the ruleset response. **Classic branch-protection checks could not be verified** (HTTP 403); no claim is made that none exist.
- The repository Actions runs endpoint supports branch/event-filtered listing. All returned `push` runs of the **five proposed archive candidates** have now been verified against their former source branches; the complete run histories and required check usage of the other 257 workflow definitions remain unverified.

## Batch 1: non-runnable one-shot workflows proposed for archive

| Workflow | Trigger | Static reference check | Rationale |
|---|---|---|---|
| `device-catalog-microchip-all-lanes-sweep-once-v1.yml` | `push` only on `agent/microchip-bulk-coverage-discovery-v1`, and only when its own file changes | GitHub code search finds only its source file; branch search finds no matching branch | Dormant original-run one-shot research |
| `device-catalog-microchip-bulk-research-once-v1.yml` | Same branch and own-file-only `push` | GitHub code search finds only its source file; branch search finds no matching branch | Dormant original-run one-shot research |
| `device-catalog-microchip-live-evidence-10-replay.yml` | Same branch and own-file-only `push` | GitHub code search finds only its source file; branch search finds no matching branch | Dormant 10-query evidence replay |

- The original YAML blob bytes are retained unchanged under `docs/archive/ci-workflows/microchip/`.
- This PR does **not** touch source IC catalog data, Programming Route, qualification, ADR-0002, hardware drivers, tests, or release materials.
- Archiving these files removes them from the GitHub Actions workflow root **only if this PR is later separately approved and merged**.
- Prior run record `38338847345` is referenced by these workflows; original Git history and Actions run history are not deleted by moving the definitions.
- Further confirmation needed before Gate 2: PR workflow checks, branch-protection scope, repository-wide caller cross-check, possible external callers, run-history/business ownership confirmation, and replacement evidence if any.

## Remaining inventory: explicit stop gate

- **KEEP_CORE (4):** `device-catalog-validation.yml`, `device-catalog-current-validation.yml`, `device-catalog-stm32-family-validation.yml`, `device-catalog-production-doc-contract.yml`.
- **KEEP_GOVERNANCE (3):** `device-catalog-production-invariants.yml`, `catalog-promotion-framework.yml`, `icpn-catalog-admission-separation-validation.yml`.
- **ARCHIVE_PROPOSED (5):** three historical Microchip YAMLs from batch 1, plus the two strictly branch-bound recovery candidates below.
- **PENDING_DEEP_AUDIT (0) for static trigger screening:** no original Workflow remains unclassified at the source/trigger layer. **Historical Runs, external callers, required checks and parity remain unverified and are not retired by this result.**

For each remaining workflow, collect: trigger events, paths/branches, manually dispatchable status, callers (`workflow_call`, `workflow_run`, `gh workflow run`), consumed/produced artifacts, active PR check contexts, last runs and business owner, successor test coverage, hardware/system integration impact, and archival restore plan. Do not convert `PENDING_DEEP_AUDIT` to `ARCHIVE_PROPOSED` without evidence.

## Batch validation gates

1. Compare base HEAD and three original blobs against the archived copies.
2. Verify only three workflow definitions are removed from `.github/workflows`, and three byte-identical archival copies added.
3. Validate `scripts/ci/device-catalog-trigger-governance.py` and repository contracts on GitHub-hosted runners; do not trigger any hardware workflow.
4. Obtain current PR checks, full required-check configuration (including classic protection), and reviewer response.
5. Request explicit **Gate 2 approval** before merge. No auto-merge.

### Risk note

Filename version age alone is **not** proof a Workflow is obsolete. An `on: workflow_dispatch` research or live-evidence workflow may remain strategically valuable even with no recent runs. Preserve immutable source/evidence and reconcile all callers before retiring it.

## Gate 1 continuation: reconcile documented lifecycle vs 262-row inventory

- Existing baseline `docs/architecture/device-catalog-ci-coverage-map.md` defines **71** workflow lifecycle rows, of which **70** are inside the 262-name Catalog scope and **one** (`stm32f1-live-acquisition-pilot.yml`) is outside that filename filter.
- The CSV now records each of those 70 baseline lifecycles and its documented disposition; **192** Catalog workflows remain not covered by that pre-existing map. `UNMAPPED` means unclassified, **not obsolete**.
- Breakdown of mapped Catalog entries: `core-regression` 2; `domain-contract` 1; `family-dispatch` 1; `governance-campaign` 12; `manual-live` 2; `production-contract` 5; `security-hil` 27; `stage-deterministic` 20.
- Mapping is **not** run-history verification, dependency proof or authorization to archive. Each mapped entry still needs exact current triggers, callers, artifacts and required-check review before retirement.
- Separately in [Draft PR #1044](https://github.com/physicslu/plasma/pull/1044), STM32U0 trigger-parity remediation exposed a **historical U0.3 prestate regression**: `STM32F0: Production source drifted relative to U0.3 prestate`. Draft PR #1044 now preserves eight original manifest-pinned CSV Git blobs as immutable fixtures, enforces SHA-256/Git-blob verification and negative tests, and its latest head `d54f935cb14f22f5ce50829f3b2af12d2905cb11` passed 16 checks (2 skipped, 0 failed). It remains Draft and requires independent Gate 2 approval.
- `main` advanced after #1042 was opened. Recheck the exact base HEAD, mergeability, run history and all required checks before any future Gate 2 request; do not merge in Gate 1.

## Gate 1 continuation: third Microchip one-shot archival proposal

- **Additional proposed archive**: `device-catalog-microchip-live-evidence-10-replay.yml`. Its only trigger is `push` on former `agent/microchip-bulk-coverage-discovery-v1` when *that YAML itself* changes; no such branch was returned by branch search.
- Default-branch indexed code search found only its own YAML reference; the source links to original evidence-run IDs `38338847345` and `38347572588`, but moving the YAML neither deletes Git history nor the original artifacts.
- It is moved as a **byte-identical Git Blob** with the other two *proposed* one-shot archive candidates, not deleted from repository history. The archived file does not execute as a normal Actions Workflow.
- Historical stage-1 triage: **ARCHIVE_PROPOSED 3**, **KEEP_CORE 4**, **KEEP_GOVERNANCE 3**, **PENDING_DEEP_AUDIT 252** (total 262). All three still require historical-run, caller/external-scheduler, Ruleset and classic required-check verification before Gate 2. The `ARCHIVE_PROPOSED` label does **not** authorize merge.

## Gate 1 continuation — static trigger review of OpenOCD and Microchip (48 definitions)

At this checkpoint the 262-row manifest has **five ARCHIVE_PROPOSED**, **43 RETAIN_ACTIVE_VALIDATOR**, **three RETAIN_MANUAL_DISPATCH**, **seven KEEP core/governance**, and **204 PENDING_DEEP_AUDIT**. These are source-level trigger/lifecycle decisions, not a complete per-workflow run-history audit.

| Reviewed cohort | Findings | Decision |
|---|---|---|
| **OpenOCD (31)** | All 31 definitions include path-scoped `pull_request` validation; the versioned-provider-registry also supports `push` and `workflow_dispatch`. All observed runners are GitHub-hosted `ubuntu-24.04`. | **Retain all 31.** Version suffix does not prove a validator's unique test coverage is redundant. |
| **Microchip PR validators (12)** | Path-filtered PR validators; most also support manual dispatch. One bulk coverage owner has PR and push. | **Retain all 12** pending path/test parity proof. |
| **Microchip manually dispatchable (3)** | `microchip-api-probe-v1` and `microchip-mcp-batch-v1` are manual only; `microchip-live-canary-v1` has manual dispatch in addition to old-branch push. | **Retain all 3**; old push branch alone does not make a manual operation obsolete. |
| **Microchip old-branch-only recovery (2)** | `microchip-crosslane-recovery-v1.yml` only triggers on self-YAML push to missing `agent/microchip-bulk-coverage-discovery-v1`; `microchip-recovery-v2.yml` only triggers on self-YAML push to missing `agent/microchip-research-recovery-v2`. Default-branch indexed code search returned only the corresponding Workflow source. No manual dispatch in either. | **Propose byte-identical archives**; still blocked from merge by unknown historical run contexts and external callers. |

For the two additional archival proposals, preserve original Git blobs under `docs/archive/ci-workflows/microchip/` and remove only their live Workflow path on the PR branch. Their downstream evidence is **not** accepted automatically: the older referenced Microchip canary run `38347572588` failed, even though its relevant artifact remains available. Both must be screened against external automation and required status checks before Gate 2.

### Strict decision boundary

- `RETAIN_*` means **no archival authorization**, even if multiple workflows test similar phases.
- `ARCHIVE_PROPOSED` means a *Draft* change with rollback copy, **not** an approved retirement.
- `PENDING_DEEP_AUDIT` remains the 204 definitions that still require source inspection; all 262 continue to require complete Actions run-history / required-check proof for retirement decisions.
- This continuation neither enables the Engineering Runtime Dispatcher nor changes SWPC/PS/PL/HIL execution authority.

## Gate 1 continuation — all 262 original workflows source-trigger screened

**Source-only triage completed for the original 262 definitions. This is NOT an exhaustive historical run / dependency / required-check audit, and is NOT Gate 2 acceptance.**

| Retention disposition | Count | Scope |
|---|---:|---|
| KEEP_CORE | 4 | Permanent registered core validation owners |
| KEEP_GOVERNANCE | 3 | Explicit Production / admission governance owners |
| RETAIN_ACTIVE_VALIDATOR | 244 | Triggered by path-scoped `pull_request` (some also allow `push` or manual dispatch); retain independent checks |
| RETAIN_MANUAL_DISPATCH | 6 | Three Microchip manual research/canary workflows and three STM32 L0/L4/U0 Live Discovery workflows |
| ARCHIVE_PROPOSED | 5 | Five no-dispatch, stale-branch/self-YAML-only Microchip one-shots; preserved byte-identically in `docs/archive/ci-workflows/microchip/` |
| PENDING_DEEP_AUDIT (source-only) | 0 | Means every original YAML was screened for *triggers*, **not** that its run history or callers have been validated |
| **Total original cohort** | **262** | Historical 2026-10-19 snapshot; archived files no longer count as live Actions workflows only after Gate 2 merge |

### Cohort-specific retention decisions

- **NXP (30)**: all 30 retain path-scoped PR validation. The Kinetis/KL25, LPC81x/82x and cross-vendor Phase admission tests remain distinct domain contracts, even if many also permit manual dispatch.
- **Cross-cutting and ST backbone (26)**: all 26 retain PR validation, including backend provenance, ST commercial-gap and ST H5 host/ARMv7 build/flash-matrix tests. Do not infer real HIL coverage from `ubuntu-24.04` build job names.
- **STM32-marked definitions (149 including the shared family core)**: 146 have PR validation (the shared core counts in KEEP_CORE), **three** are manual-only Live Discovery: `stm32l0-l02-live-discovery`, `stm32l4-l42-live-discovery`, `stm32u0-u02-live-discovery`. Preserve staged L0/L1/L4 and TrustZone/security/HIL evidence owners until explicit parity proof.
- **Microchip (20)**: 5 static archive candidates, 12 PR validators and 3 manually dispatchable workflows; see prior section.
- **OpenOCD (31)**: all retain PR validation; keep exact production/route/metadata boundary gates.

### Incomplete Gate 1 verification (must remain explicit)

1. **Per-workflow historical Actions runs:** no API-wide exhaustively paginated run history available through the connected GitHub interface. Certain known Runs and Artifacts have been checked individually; this does not complete the 262-run history.
2. **External callers:** GitHub indexed default-branch code search is not exhaustive over scripts, off-repository automation, retired branches or scheduled external dispatch.
3. **Required checks:** active Ruleset reads do not establish classic branch-protection required status contexts (connector returned 403 previously). No required-check equivalence is asserted for any archive.
4. **Validator parity:** retaining a PR validator is conservative. Consolidating or retiring PR stages requires explicit identical test/trigger/evidence/release contract coverage, not a filename or age heuristic.
5. **Source change vs current state:** 262 is the original baseline; do not reinterpret it as the live workflow count after the five proposed archives. Recheck current main and PR diff before Gate 2.

Nothing in this audit authorizes production catalog mutation, software/runtime activation, self-hosted operation, hardware tests, or merge.
