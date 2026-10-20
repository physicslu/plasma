# STM32 Historical Governance Shadow Dispatcher — Gate 1

Tracking: [CI architecture #622](https://github.com/physicslu/plasma/issues/622).

## Boundary

This is **shadow-only**. The following original workflows remain live, unmodified and independently responsible for their checks:

- `.github/workflows/device-catalog-post-u5-frontier-selection-validation.yml` (Git Blob `e4f95807c08c4c10858fb8084fc8206902b11989`)
- `.github/workflows/device-catalog-stm32h7-partitioned-scope-selection-validation.yml` (Git Blob `56b50b27536d05552b4413d55b31d0ca2dcf4aea`)
- `.github/workflows/device-catalog-stm32h7rs-evidence-accessibility-validation.yml` (Git Blob `e2b6a1e03b7269f52ec2765651685849d23b27d1`)

New shadow files:
- `.github/workflows/device-catalog-stm32-governance-shadow.yml`
- `scripts/ci/icpn_stm32_governance_shadow.py`
- `scripts/tests/test-icpn-stm32-governance-shadow.py`

The original 18 trigger-path entries have **15 distinct patterns** and **three paths shared between two validators**. The shadow PR/main-push union adds its own three control paths; changes to control paths conservatively run all three validators. Its independent detection job is intentional Gate 1 overhead, **not** an optimization claim.

Runner: `ubuntu-24.04`; Python: `3.12`; each replay timeout: 10 minutes; `contents: read`; no `workflow_dispatch`. Source Git blob hash, trigger union, command, cwd, runner, permissions and timeout are all fail-closed contracts.

## Gate 1 acceptance evidence

1. Run `python scripts/ci/icpn_stm32_governance_shadow.py self-test`.
2. Run `python scripts/tests/test-icpn-stm32-governance-shadow.py` for shared-path positive and unsafe source/trigger/runner/permissions mutation negative controls.
3. Confirm hosted CI executes `detect` plus `shadow-validate (post_u5 / h7_scope / h7rs_evidence)` when the Shadow code changes.
4. Record exact PR SHA, main SHA, CI run IDs, and Git diff; original source files must have **zero diff**.
5. Review Rulesets, unresolved reviews, original workflow required-check and external trigger/dependency implications before any future retirement.

**No Gate 2 authorization**: this Draft PR does not merge or retire any workflow. No hardware, SWPC, HIL, external vendor acquisition, Production writes, deployment, or manual Actions dispatch.
