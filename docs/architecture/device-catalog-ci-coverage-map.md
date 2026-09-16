# Device Catalog CI Coverage Map

Status: **Phase 2 inventory in progress — no workflow retirement is authorized by this document yet**

Baseline: `main` at `9aca1bb7bcb2c61105e56b195990e1ebbbeed9db`.

Tracking: issue #622.

## 1. Purpose

This map records Device Catalog CI authority before any workflow consolidation or retirement.

The governing rule is:

> Consolidate orchestration, not validation coverage.

Workflow count is not itself the optimization target. Changes must preserve dependency ownership, fail-closed deterministic validation, failure-domain isolation, reproducibility, and auditability. Runner minutes and PR critical-path latency are secondary optimization metrics after coverage is proven equivalent.

## 2. Lifecycle classes

| Class | Meaning | Default treatment |
|---|---|---|
| `core-regression` | Broad historical/current catalog regression | Keep unless validator-level equivalence is proven |
| `family-dispatch` | Affected-family deterministic orchestration | Preferred consolidation primitive |
| `stage-deterministic` | Family/stage-specific retained-evidence, policy, admission, or publication contract | Candidate for consolidation only after command/trigger parity is proven |
| `manual-live` | Network/browser/external-source acquisition | Keep outside ordinary PR critical path |
| `security-hil` | Security state, HIL provenance/readiness, runtime enforcement | Preserve as a distinct authority unless a replacement gate proves the same boundary |
| `governance-campaign` | Selection, prioritization, frontier, requalification, or campaign-specific governance | Review lifecycle; do not treat as permanent core by default |
| `production-contract` | Production manifest/document/runtime-load invariants | Keep as product-facing catalog boundary |
| `inventory-pending` | Workflow is present but exact trigger/validator mapping has not yet been audited in this phase | No retirement permitted |

## 3. Core and production authority

| Workflow | Authority | Trigger | Validator / coverage | Overlap | Lifecycle |
|---|---|---|---|---|---|
| `device-catalog-validation.yml` | Historical/broad Device Catalog regression | PR + `main`, catalog-related paths | Historical/generic evidence, policy, admission and family regressions | Some assertions overlap current/family gates; not proven equivalent | `core-regression` |
| `device-catalog-current-validation.yml` | Current catalog regression | PR + `main`, catalog-related paths | Current retained-evidence and post-admission replay | Different body from historical gate | `core-regression` |
| `device-catalog-production-doc-contract.yml` | Production documentation/manifest single-source contract | PR + `main`, narrow production-doc paths | `validate_readme_contract.py` | No proven duplicate authority | `production-contract` |
| `device-catalog-production-invariants.yml` | Canonical Production graph invariants | PR + `main`, production/research publication paths | `scripts/ci/device-catalog-production-invariants.py` | Reused by family publication gates by design | `production-contract` |
| `device-catalog-stm32-family-validation.yml` | Affected-family deterministic dispatcher | PR + `main`, explicit family/shared paths | `scripts/device-catalog-family-ci.py` detect/self-test/run | Intentionally overlaps family-specific deterministic gates where both still exist | `family-dispatch` |

## 4. STM32 family dispatcher: verified scope

The dispatcher implementation currently defines deterministic profiles for:

```text
STM32F0
STM32F2
STM32F3
STM32F7
STM32G0
STM32G4
STM32U0
STM32C0
```

The workflow trigger currently covers the F0/F2/F3/F7/G0/G4/C0 family paths plus shared catalog infrastructure, but **does not include normal STM32U0 paths** even though the dispatcher has a U0 profile.

This is a coverage defect, not a consolidation opportunity: before the dispatcher can be considered authoritative for U0, its path filter must be brought into parity with the implementation.

The workflow also contains references to old family workflow filenames and a C0 live workflow filename that are not present in the current workflow directory. These are stale trigger references to classify during cleanup; removing them is not authorized by this inventory alone.

## 5. STM32C0 overlap pilot

C0 is the first family where duplicate orchestration can be measured precisely because both the family dispatcher and stage-specific workflows are active.

| Workflow | Stage authority | Trigger | Stage-only or extra behavior relative to dispatcher | Current disposition |
|---|---|---|---|---|
| `device-catalog-stm32c0-c01-foundation-validation.yml` | C0.1 foundation | PR + `main`, C0.1 paths | Replays `stm32c0_phase_c0_1_foundation.py --check` in addition to tests/validator | Consolidation candidate, **not retireable yet** |
| `device-catalog-stm32c0-c02-discovery-validation.yml` | C0.2 deterministic discovery/retained evidence | PR + `main`, C0.2 paths | Explicit deterministic target-manifest replay plus retained-evidence validation | Consolidation candidate, **not retireable yet** |
| `device-catalog-stm32c0-c03-metadata-validation.yml` | C0.3 metadata/policy | PR + `main`, C0.3 paths | Explicit C0.2 prerequisite replay before policy test/replay | Largely covered by dispatcher sequence; parity still must be proven |
| `device-catalog-stm32c0-c04-admission-validation.yml` | C0.4 read-only admission | PR + `main`, C0.4 paths | Explicit retained-evidence and C0.3 prerequisite replay before admission tests | Largely covered by dispatcher sequence; parity still must be proven |
| `device-catalog-stm32c0-c05-publication-validation.yml` | C0.5 publication | PR + `main`, C0.5 paths | Admission-plan validation plus publication script `--verify` | Consolidation candidate, **not retireable yet** |

Required before C0 retirement:

1. Move every stage-only deterministic check into the family command profile or an explicitly owned replacement gate.
2. Prove trigger parity for all C0 research/evidence/publication paths.
3. Run negative controls showing the replacement fails when each stage contract is broken.
4. Only then retire the five stage YAML files in a separate PR.

## 6. Manual live acquisition

The following workflows are verified as manual external-source acquisition and must remain outside the ordinary PR critical path unless product dependency ownership changes:

| Workflow | Coverage | Trigger | Lifecycle |
|---|---|---|---|
| `device-catalog-stm32l0-l02-live-discovery.yml` | STM32L0 bounded live commercial discovery | `workflow_dispatch` | `manual-live` |
| `device-catalog-stm32l4-l42-live-discovery.yml` | STM32L4 bounded live commercial discovery | `workflow_dispatch` | `manual-live` |
| `device-catalog-stm32u0-u02-live-discovery.yml` | STM32U0 bounded live commercial discovery | `workflow_dispatch` | `manual-live` |

These workflows intentionally acquire external manufacturer data and retain evidence artifacts. They are evidence-generation gates, not deterministic PR regression gates.

## 7. Family/stage inventory still to audit

The workflows below are present on the baseline and are now explicitly in the Phase 2 inventory. Until their exact trigger and validator parity is recorded, their lifecycle is `inventory-pending` and they must not be retired.

### STM32L0

- `device-catalog-stm32l0-l01-foundation-validation.yml`
- `device-catalog-stm32l0-l02-discovery-validation.yml`
- `device-catalog-stm32l0-l03-metadata-validation.yml`
- `device-catalog-stm32l0-l04-admission-validation.yml`
- `device-catalog-stm32l0-l05-publication-validation.yml`

### STM32L1

- `device-catalog-stm32l1-l11-foundation-validation.yml`
- `device-catalog-stm32l1-l12-retained-validation.yml`
- `device-catalog-stm32l1-l13-metadata-policy-validation.yml`
- `device-catalog-stm32l1-l14-admission-plan-validation.yml`
- `device-catalog-stm32l1-l15-publication-validation.yml`
- `device-catalog-stm32l1-requalification-validation.yml`

### STM32L4

- `device-catalog-stm32l4-l41-foundation-validation.yml`
- `device-catalog-stm32l4-l42-discovery-validation.yml`
- `device-catalog-stm32l4-l43-metadata-validation.yml`
- `device-catalog-stm32l4-l44-admission-validation.yml`
- `device-catalog-stm32l4-l45-publication-validation.yml`

### STM32L5 security/HIL/publication chain

- `device-catalog-stm32l5-canonical-admission-plan-validation.yml`
- `device-catalog-stm32l5-hil-fixture-acquisition-provenance-validation.yml`
- `device-catalog-stm32l5-hil-fixture-inventory-binding-validation.yml`
- `device-catalog-stm32l5-hil-observer-debug-readiness-validation.yml`
- `device-catalog-stm32l5-manufacturer-identity-discovery-validation.yml`
- `device-catalog-stm32l5-metadata-policy-validation.yml`
- `device-catalog-stm32l5-production-publication-validation.yml`
- `device-catalog-stm32l5-runtime-enforcement-admission-gate-validation.yml`
- `device-catalog-stm32l5-security-scope-foundation-validation.yml`
- `device-catalog-stm32l5-security-state-admission-gate-validation.yml`
- `device-catalog-stm32l5-security-state-observer-debug-validation.yml`

Default classification for this chain is `security-hil` or `stage-deterministic`, not bulk-consolidation. Security-state and HIL authority must stay explicit even if common YAML mechanics are later extracted.

### STM32U3 security/publication chain

- `device-catalog-stm32u3-canonical-admission-plan-validation.yml`
- `device-catalog-stm32u3-hil-observer-debug-readiness-validation.yml`
- `device-catalog-stm32u3-manufacturer-identity-discovery-validation.yml`
- `device-catalog-stm32u3-metadata-policy-validation.yml`
- `device-catalog-stm32u3-production-publication-validation.yml`
- `device-catalog-stm32u3-runtime-enforcement-admission-gate-validation.yml`
- `device-catalog-stm32u3-security-scope-foundation-validation.yml`
- `device-catalog-stm32u3-security-state-admission-gate-validation.yml`
- `device-catalog-stm32u3-security-state-observer-debug-validation.yml`

Verified sample: the U3 security-state admission workflow is PR/path-scoped plus manual dispatch and runs `validate_stm32u3_security_state_admission_gate.py`. It is therefore a distinct security authority, not evidence that the entire U3 chain can be flattened into a generic matrix.

### STM32U5 security/publication chain

- `device-catalog-stm32u5-canonical-admission-plan-validation.yml`
- `device-catalog-stm32u5-catalog-runtime-governance-correction-validation.yml`
- `device-catalog-stm32u5-exact-orderable-identity-probe.yml`
- `device-catalog-stm32u5-manufacturer-identity-discovery-validation.yml`
- `device-catalog-stm32u5-metadata-authority-delta-resolution-validation.yml`
- `device-catalog-stm32u5-metadata-policy-validation.yml`
- `device-catalog-stm32u5-production-publication-validation.yml`
- `device-catalog-stm32u5-runtime-enforcement-admission-gate-validation.yml`
- `device-catalog-stm32u5-security-scope-foundation-validation.yml`
- `device-catalog-stm32u5-security-state-admission-gate-validation.yml`
- `device-catalog-stm32u5-security-state-observer-debug-validation.yml`

Verified samples:

- `device-catalog-stm32u5-exact-orderable-identity-probe.yml` is PR/path-scoped plus manual dispatch and explicitly enforces retained/offline evidence only.
- `device-catalog-stm32u5-production-publication-validation.yml` is PR + `main` and also validates Production invariants plus runtime catalog loading.

These own different authority and must not be merged merely because they share a family name.

## 8. Governance / selection / frontier inventory

The following workflows are campaign/governance candidates rather than ordinary product-runtime gates. Exact lifecycle must be audited before any trigger change:

- `device-catalog-post-u5-frontier-selection-validation.yml`
- `device-catalog-stm32-cross-family-prioritization-validation.yml`
- `device-catalog-stm32-evidence-accessibility-validation.yml`
- `device-catalog-stm32-post-c0-selection-validation.yml`
- `device-catalog-stm32-post-l0-selection-validation.yml`
- `device-catalog-stm32-post-u0-selection-validation.yml`
- `device-catalog-stm32-trustzone-cohort-gate1-validation.yml`
- `device-catalog-stm32-trustzone-cohort-succession-after-l5-blocker-validation.yml`
- `device-catalog-stm32h7-partitioned-scope-selection-validation.yml`
- `device-catalog-stm32h7rs-evidence-accessibility-validation.yml`

The likely optimization is lifecycle/trigger normalization (`workflow_dispatch`, retained deterministic replay, or retirement after campaign closure), not loss of the evidence itself.

## 9. First consolidation sequence

No workflow is retired in this inventory PR. The next implementation sequence should be:

1. **Repair U0 dispatcher trigger parity** so the implementation and workflow trigger describe the same managed-family set.
2. **Complete C0 command parity** by moving stage-only checks into the deterministic family profile or another explicit replacement gate.
3. Prove C0 replacement coverage with negative controls.
4. Retire only the proven-redundant C0 stage workflow files in a separate PR.
5. Audit L0/L1/L4 next; add family profiles only where semantics are deterministic and truly equivalent.
6. Treat L5/U3/U5 security/HIL chains separately from ordinary family stage consolidation.
7. Audit governance/frontier workflows for lifecycle closure after deterministic/security authority is stable.

## 10. Exit criteria for Phase 2

Phase 2 is complete only when:

- every Device Catalog workflow has Authority / Trigger / Validator / Coverage / Overlap / Lifecycle recorded;
- all `inventory-pending` entries are resolved;
- historical, current, production, family, security/HIL, and live-source boundaries remain explicit;
- every retired workflow points to a tested replacement authority or a documented closed campaign;
- non-catalog PRs gain no new Device Catalog jobs;
- live external acquisition remains non-mandatory for ordinary PRs;
- CI architecture documentation is updated to the final authority model.
