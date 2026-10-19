# ICPN Catalog workflow rationalization — Gate 1, batch 1 (2026-10-19)

> **DRAFT PR ONLY — not an authorization to merge, dispatch Actions, deploy, or operate hardware.** This is an initial source-level inventory, **not** a completed run-history and dependency audit of all workflows.

## Frozen baseline

- Repository: `physicslu/plasma`; branch: `main`; base commit `17382d889a7643dd9986639ab50601d65b4cbf12`.
- 336 total workflow YAMLs; 262 with `catalog` in their filename, of which 260 start with `device-catalog-`.
- Breakdown: ST/STM32 171, OpenOCD 31, NXP 30, Microchip 20, cross-cutting 10.
- Exact 262-row manifest: `docs/engineering/ci/icpn-workflow-inventory-2026-10-19.csv`. Each row records the immutable Git blob SHA and triage state.
- `.github/ci-workstreams.json` identifies four ICPN core workflows. `.github/device-catalog-ci-trigger-debt.json` limits Production-wide path ownership to four named validators and reports zero existing exceptions.
- Active branch Ruleset `Protect Plasma main` (20964250) has pull-request and review-thread restrictions, but no `required_status_checks` rule in the ruleset response. **Classic branch-protection checks could not be verified** (HTTP 403); no claim is made that none exist.
- API connector does not expose a complete per-workflow Actions run listing. Prior execution counts, last run, artifacts, and required check use remain `UNKNOWN` unless individually confirmed.

## Batch 1: non-runnable one-shot workflows proposed for archive

| Workflow | Trigger | Static reference check | Rationale |
|---|---|---|---|
| `device-catalog-microchip-all-lanes-sweep-once-v1.yml` | `push` only on `agent/microchip-bulk-coverage-discovery-v1`, and only when its own file changes | GitHub code search finds only its source file; branch search finds no matching branch | Dormant original-run one-shot research |
| `device-catalog-microchip-bulk-research-once-v1.yml` | Same branch and own-file-only `push` | GitHub code search finds only its source file; branch search finds no matching branch | Dormant original-run one-shot research |

- The original YAML blob bytes are retained unchanged under `docs/archive/ci-workflows/microchip/`.
- This PR does **not** touch source IC catalog data, Programming Route, qualification, ADR-0002, hardware drivers, tests, or release materials.
- Archiving these files removes them from the GitHub Actions workflow root **only if this PR is later separately approved and merged**.
- Prior run record `38338847345` is referenced by these workflows; original Git history and Actions run history are not deleted by moving the definitions.
- Further confirmation needed before Gate 2: PR workflow checks, branch-protection scope, repository-wide caller cross-check, possible external callers, run-history/business ownership confirmation, and replacement evidence if any.

## Remaining inventory: explicit stop gate

- **KEEP_CORE (4):** `device-catalog-validation.yml`, `device-catalog-current-validation.yml`, `device-catalog-stm32-family-validation.yml`, `device-catalog-production-doc-contract.yml`.
- **KEEP_GOVERNANCE (3):** `device-catalog-production-invariants.yml`, `catalog-promotion-framework.yml`, `icpn-catalog-admission-separation-validation.yml`.
- **ARCHIVE_PROPOSED (2):** the two original-run Microchip YAMLs listed above.
- **PENDING_DEEP_AUDIT (253):** *not* authorized for deletion or archival.

For each remaining workflow, collect: trigger events, paths/branches, manually dispatchable status, callers (`workflow_call`, `workflow_run`, `gh workflow run`), consumed/produced artifacts, active PR check contexts, last runs and business owner, successor test coverage, hardware/system integration impact, and archival restore plan. Do not convert `PENDING_DEEP_AUDIT` to `ARCHIVE_PROPOSED` without evidence.

## Batch validation gates

1. Compare base HEAD and two original blobs against the archived copies.
2. Verify only two workflow definitions are removed from `.github/workflows`, and two byte-identical archival copies added.
3. Validate `scripts/ci/device-catalog-trigger-governance.py` and repository contracts on GitHub-hosted runners; do not trigger any hardware workflow.
4. Obtain current PR checks, full required-check configuration (including classic protection), and reviewer response.
5. Request explicit **Gate 2 approval** before merge. No auto-merge.

### Risk note

Filename version age alone is **not** proof a Workflow is obsolete. An `on: workflow_dispatch` research or live-evidence workflow may remain strategically valuable even with no recent runs. Preserve immutable source/evidence and reconcile all callers before retiring it.
