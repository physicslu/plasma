# Device Catalog CI Coverage Map

Status: **Phase 2 inventory complete for the current workflow set; no workflow retirement is authorized by this document alone**

Baseline: `main` at `9aca1bb7bcb2c61105e56b195990e1ebbbeed9db`.

Tracking: issue #622.

## 1. Governing rule

> Consolidate orchestration, not validation coverage.

Workflow count is not itself the optimization target. A consolidation is acceptable only when dependency ownership, fail-closed deterministic validation, failure-domain isolation, reproducibility, and auditability remain explicit. Runner minutes and PR critical-path latency are optimization metrics after coverage parity is demonstrated.

## 2. Existing repository governance

The repository already enforces important CI boundaries:

- `.github/ci-workstreams.json` defines `ICPN` as the owner of exact commercial identity, canonical metadata, and the user-selectable Production catalog.
- The ICPN core workflow set is `device-catalog-validation.yml`, `device-catalog-current-validation.yml`, `device-catalog-stm32-family-validation.yml`, and `device-catalog-production-doc-contract.yml`.
- `scripts/ci/device-catalog-trigger-governance.py` scans every `device-catalog-*.yml` workflow and default-denies canonical Production-path triggers for family/research workflows.
- Only the historical/current/Production-document/Production-invariant workflows may own canonical Production triggers.
- `.github/device-catalog-ci-trigger-debt.json` currently has an empty violation set and is a shrink-only ratchet.

Therefore the current problem is primarily **specialized workflow lifecycle and orchestration sprawl**, not uncontrolled Production-path fan-out.

## 3. Lifecycle classes

| Class | Meaning | Default treatment |
|---|---|---|
| `core-regression` | Broad historical/current catalog regression | Keep unless validator-level equivalence is proven |
| `family-dispatch` | Affected-family deterministic orchestration | Preferred deterministic family consolidation primitive |
| `stage-deterministic` | Retained-evidence, metadata, admission, or publication stage contract | Consolidate only after command/trigger parity is proven |
| `manual-live` | Network/browser/external-source acquisition | Keep outside ordinary PR critical path |
| `security-hil` | Security state, HIL provenance/readiness, runtime enforcement | Preserve distinct authority; reusable mechanics are allowed |
| `governance-campaign` | Selection, prioritization, frontier, requalification, or frozen campaign decision | Candidate for a historical/governance replay authority after coverage migration |
| `production-contract` | Production manifest/document/runtime-load invariant | Keep as product-facing boundary |
| `domain-contract` | Cross-domain invariant such as catalog-selectability vs execution admission | Keep explicit unless moved to an equivalent repository/catalog contract gate |

## 4. Core and Production authority

| Workflow | Trigger | Authority / validator coverage | Overlap / disposition | Lifecycle |
|---|---|---|---|---|
| `device-catalog-validation.yml` | PR + `main`, catalog paths | Broad/historical evidence, policy, admission and family regressions | Not equivalent to current/family gates | `core-regression` |
| `device-catalog-current-validation.yml` | PR + `main`, catalog paths | Current retained-evidence and post-admission regression | Distinct body from historical gate | `core-regression` |
| `device-catalog-production-doc-contract.yml` | PR + `main`, narrow Production/doc paths | Production documentation/manifest single-source contract | No replacement identified | `production-contract` |
| `device-catalog-production-invariants.yml` | PR + `main`, Production/publication paths | Canonical Production graph invariants | Reused by publication gates by design | `production-contract` |
| `device-catalog-stm32-family-validation.yml` | PR + `main`, explicit family/shared paths | Detect affected families then run deterministic family profiles | Preferred family orchestration primitive; trigger defect noted below | `family-dispatch` |
| `icpn-catalog-admission-separation-validation.yml` | PR + `main`, catalog/policy paths | `validate-icpn-catalog-admission-separation.py`; proves catalog admission/selectability stays separate from execution support | Could eventually move into a core catalog/repository contract gate only if the same invariant remains independently visible | `domain-contract` |

## 5. STM32 family dispatcher

`scripts/device-catalog-family-ci.py` currently defines deterministic profiles for:

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

The dispatcher workflow covers F0/F2/F3/F7/G0/G4/C0 and shared catalog infrastructure, but **does not include normal STM32U0 research/evidence paths**. The implementation has a U0 profile, while the workflow trigger does not reliably invoke it for ordinary U0 changes. This is a coverage defect to repair before the dispatcher is considered authoritative for U0.

The workflow also carries path references to older family workflow filenames and a C0 live workflow filename that are no longer present. These are stale trigger references and should be removed in a hygiene PR only after the active trigger set is tested.

## 6. STM32C0 overlap pilot

| Workflow | Trigger | Authority / validator coverage | Overlap / disposition | Lifecycle |
|---|---|---|---|---|
| `device-catalog-stm32c0-c01-foundation-validation.yml` | PR + `main` | C0.1 negative controls, frozen foundation `--check`, hard-lock | Dispatcher overlaps tests/validator but not all replay behavior | `stage-deterministic` |
| `device-catalog-stm32c0-c02-discovery-validation.yml` | PR + `main` | C0.2 discovery tests, deterministic target-manifest replay, retained evidence | Partial dispatcher overlap | `stage-deterministic` |
| `device-catalog-stm32c0-c03-metadata-validation.yml` | PR + `main` | C0.3 metadata policy plus prerequisite replay | Substantial dispatcher overlap; parity not yet proven | `stage-deterministic` |
| `device-catalog-stm32c0-c04-admission-validation.yml` | PR + `main` | C0.4 admission plus retained-evidence/metadata prerequisites | Substantial dispatcher overlap; parity not yet proven | `stage-deterministic` |
| `device-catalog-stm32c0-c05-publication-validation.yml` | PR + `main` | C0.5 tests, admission-plan validation, publication `--verify` | Dispatcher lacks full publication replay parity | `stage-deterministic` |

C0 is the first safe consolidation target, but none of these five workflows is retireable yet. Replacement coverage must absorb every stage-only check, preserve trigger parity, and pass negative controls before deletion.

## 7. STM32L0, L1 and L4 deterministic stage chains

### STM32L0

| Workflow | Trigger | Authority / validator coverage | Overlap / disposition | Lifecycle |
|---|---|---|---|---|
| `device-catalog-stm32l0-l01-foundation-validation.yml` | PR + `main` | Foundation negative controls, baseline `--check`, hard-lock | Similar lifecycle shape to C0; no dispatcher profile | `stage-deterministic` |
| `device-catalog-stm32l0-l02-discovery-validation.yml` | PR + `main` | 99-Base-Device deterministic discovery replay + retained evidence | No family-dispatch replacement | `stage-deterministic` |
| `device-catalog-stm32l0-l03-metadata-validation.yml` | PR + dispatch | Frozen metadata policy, deterministic summary/assertions, artifact | Trigger/artifact semantics differ from C0/L1 | `stage-deterministic` |
| `device-catalog-stm32l0-l04-admission-validation.yml` | PR + dispatch | Frozen read-only admission plan, summary/assertions, artifact | No equivalent family profile | `stage-deterministic` |
| `device-catalog-stm32l0-l05-publication-validation.yml` | PR + dispatch | Publication tests, `--verify`, validator, Production boundary | Publication authority must remain explicit | `stage-deterministic` |
| `device-catalog-stm32l0-l02-live-discovery.yml` | dispatch only | External live commercial discovery and evidence capture | Must not become ordinary PR gate | `manual-live` |

### STM32L1

| Workflow | Trigger | Authority / validator coverage | Overlap / disposition | Lifecycle |
|---|---|---|---|---|
| `device-catalog-stm32l1-l11-foundation-validation.yml` | PR + `main` | Foundation hard-lock; forbids Production writes | No dispatcher profile | `stage-deterministic` |
| `device-catalog-stm32l1-l12-retained-validation.yml` | PR + `main` | Retained/sharded discovery evidence | Unique retained-evidence stage | `stage-deterministic` |
| `device-catalog-stm32l1-l13-metadata-policy-validation.yml` | PR + `main` + dispatch | Frozen metadata policy | No equivalent family profile | `stage-deterministic` |
| `device-catalog-stm32l1-l14-admission-plan-validation.yml` | PR + `main` + dispatch | Frozen admission plan | No equivalent family profile | `stage-deterministic` |
| `device-catalog-stm32l1-l15-publication-validation.yml` | PR + `main` + dispatch | Publication hard-lock and bounded Production delta | Publication authority must remain explicit | `stage-deterministic` |
| `device-catalog-stm32l1-requalification-validation.yml` | PR + `main` | Frozen requalification evidence/result; forbids Production writes | Not an ordinary lifecycle stage; keep separate unless moved to governance replay | `governance-campaign` |

### STM32L4

| Workflow | Trigger | Authority / validator coverage | Overlap / disposition | Lifecycle |
|---|---|---|---|---|
| `device-catalog-stm32l4-l41-foundation-validation.yml` | PR + `main` | Foundation negative controls, baseline `--check`, hard-lock, zero Production writes | No dispatcher profile | `stage-deterministic` |
| `device-catalog-stm32l4-l42-discovery-validation.yml` | PR + `main` | 138-Base-Device deterministic discovery replay + retained evidence | No dispatcher replacement | `stage-deterministic` |
| `device-catalog-stm32l4-l43-metadata-validation.yml` | PR + `main` + dispatch | Byte-for-byte policy reconstruction, hard-lock, pre-publication Production boundary | Trigger/replay semantics are stage-specific | `stage-deterministic` |
| `device-catalog-stm32l4-l44-admission-validation.yml` | PR + dispatch | Frozen admission plan, deterministic summary/assertions, artifact | No equivalent family profile | `stage-deterministic` |
| `device-catalog-stm32l4-l45-publication-validation.yml` | PR + dispatch | Publication `--verify`, validator, Production-boundary assertions | Publication authority must remain explicit | `stage-deterministic` |
| `device-catalog-stm32l4-l42-live-discovery.yml` | dispatch only | External live commercial discovery and evidence capture | Must not become ordinary PR gate | `manual-live` |

L0/L1/L4 share a broad lifecycle shape but their trigger, artifact, replay and Production-write semantics are not identical. They must not be absorbed by the existing family matrix by merely adding family names.

## 8. STM32L5 security/HIL chain

| Workflow | Trigger | Authority / validator coverage | Disposition | Lifecycle |
|---|---|---|---|---|
| `device-catalog-stm32l5-manufacturer-identity-discovery-validation.yml` | PR + `main` | Frozen manufacturer identity discovery; zero Production writes | Keep distinct authority | `security-hil` |
| `device-catalog-stm32l5-metadata-policy-validation.yml` | PR + `main` | Metadata policy; zero Production writes | Keep distinct authority | `security-hil` |
| `device-catalog-stm32l5-canonical-admission-plan-validation.yml` | PR + `main` | Canonical admission plan; zero Production writes | Keep distinct authority | `security-hil` |
| `device-catalog-stm32l5-security-scope-foundation-validation.yml` | PR + `main` | Security-scope foundation | Keep distinct authority | `security-hil` |
| `device-catalog-stm32l5-security-state-admission-gate-validation.yml` | PR + `main` | Security-state admission | Keep distinct authority | `security-hil` |
| `device-catalog-stm32l5-runtime-enforcement-admission-gate-validation.yml` | PR + `main` | Runtime-enforcement admission | Keep distinct authority | `security-hil` |
| `device-catalog-stm32l5-security-state-observer-debug-validation.yml` | PR + `main` | Observer/debug security-state gate | Keep distinct authority | `security-hil` |
| `device-catalog-stm32l5-hil-observer-debug-readiness-validation.yml` | PR + `main` | HIL observer/debug readiness; zero Production writes | Keep distinct HIL authority | `security-hil` |
| `device-catalog-stm32l5-hil-fixture-inventory-binding-validation.yml` | PR + `main` | HIL fixture inventory binding; zero Production writes | Keep distinct HIL authority | `security-hil` |
| `device-catalog-stm32l5-hil-fixture-acquisition-provenance-validation.yml` | PR + `main` | HIL fixture acquisition provenance; zero Production writes | Keep distinct HIL authority | `security-hil` |
| `device-catalog-stm32l5-production-publication-validation.yml` | PR + `main` | Deterministic publication + Production invariants + runtime catalog load | Dedicated publication boundary | `production-contract` |

Common setup and zero-Production-write mechanics can become reusable primitives, but the authority chain must not be flattened into an ordinary family matrix.

## 9. STM32U3 security/publication chain

| Workflow | Trigger | Authority / validator coverage | Disposition | Lifecycle |
|---|---|---|---|---|
| `device-catalog-stm32u3-manufacturer-identity-discovery-validation.yml` | PR + `main` | Manufacturer identity discovery; zero Production writes | Keep distinct | `security-hil` |
| `device-catalog-stm32u3-metadata-policy-validation.yml` | PR + dispatch | Frozen metadata policy; zero Production writes | Keep distinct | `security-hil` |
| `device-catalog-stm32u3-canonical-admission-plan-validation.yml` | PR + dispatch | Canonical admission plan | Keep distinct | `security-hil` |
| `device-catalog-stm32u3-security-scope-foundation-validation.yml` | PR + dispatch | Security-scope negative controls + frozen foundation + zero Production writes | Keep distinct | `security-hil` |
| `device-catalog-stm32u3-security-state-admission-gate-validation.yml` | PR + dispatch | Security-state admission gate | Keep distinct | `security-hil` |
| `device-catalog-stm32u3-runtime-enforcement-admission-gate-validation.yml` | PR + dispatch | Runtime-enforcement gate | Keep distinct | `security-hil` |
| `device-catalog-stm32u3-security-state-observer-debug-validation.yml` | PR + dispatch | Observer/debug gate | Keep distinct | `security-hil` |
| `device-catalog-stm32u3-hil-observer-debug-readiness-validation.yml` | PR + `main` | HIL readiness + zero Production writes | Keep distinct HIL authority | `security-hil` |
| `device-catalog-stm32u3-production-publication-validation.yml` | PR + `main` | Deterministic publication + Production invariants + runtime catalog load | Dedicated publication boundary | `production-contract` |

U3 intentionally has different trigger lifecycles from L5; normalization must be based on authority, not filename symmetry.

## 10. STM32U5 security/publication chain

| Workflow | Trigger | Authority / validator coverage | Disposition | Lifecycle |
|---|---|---|---|---|
| `device-catalog-stm32u5-exact-orderable-identity-probe.yml` | PR + dispatch | Retained/offline exact-orderable identity evidence | Keep offline evidence authority | `security-hil` |
| `device-catalog-stm32u5-manufacturer-identity-discovery-validation.yml` | PR | Manufacturer identity discovery + zero Production writes | Keep distinct | `security-hil` |
| `device-catalog-stm32u5-metadata-policy-validation.yml` | PR + dispatch | Frozen metadata policy + zero Production writes | Keep distinct | `security-hil` |
| `device-catalog-stm32u5-metadata-authority-delta-resolution-validation.yml` | PR + dispatch | Metadata-policy replay + authority-delta disposition + zero Production writes | Keep distinct until metadata governance is redesigned | `security-hil` |
| `device-catalog-stm32u5-canonical-admission-plan-validation.yml` | PR + dispatch | Metadata policy + metadata delta + canonical admission plan | Keep distinct | `security-hil` |
| `device-catalog-stm32u5-security-scope-foundation-validation.yml` | PR + `main` | Security-scope foundation + zero Production writes | Keep distinct | `security-hil` |
| `device-catalog-stm32u5-security-state-admission-gate-validation.yml` | PR + dispatch | Upstream admission replay + security-state gate + Production-write rejection | Keep distinct | `security-hil` |
| `device-catalog-stm32u5-runtime-enforcement-admission-gate-validation.yml` | PR + dispatch | Runtime-enforcement gate | Keep distinct | `security-hil` |
| `device-catalog-stm32u5-security-state-observer-debug-validation.yml` | PR + dispatch | Runtime-enforcement replay + observer/debug gate + catalog-write rejection | Keep distinct | `security-hil` |
| `device-catalog-stm32u5-production-publication-validation.yml` | PR + `main` | Deterministic publication + Production invariants + runtime catalog load | Dedicated publication boundary | `production-contract` |
| `device-catalog-stm32u5-catalog-runtime-governance-correction-validation.yml` | PR | Catalog/runtime governance-correction validator | Keep until correction contract lifecycle is closed; contains stale trigger reference noted below | `governance-campaign` |

Hygiene defect: the governance-correction workflow includes `.github/workflows/device-catalog-stm32u5-hil-observer-debug-readiness-validation.yml` in its path filter, but that workflow file does not exist on this baseline. The stale reference should be removed in a behavior-neutral hygiene PR.

## 11. Governance / selection / frontier campaigns

| Workflow | Trigger | Authority / validator coverage | Disposition | Lifecycle |
|---|---|---|---|---|
| `device-catalog-stm32-cross-family-prioritization-validation.yml` | PR + `main` | Prioritization policy negative controls + immutable historical replay | Candidate for consolidated governance replay | `governance-campaign` |
| `device-catalog-stm32-evidence-accessibility-validation.yml` | PR + `main` + dispatch | Retained evidence accessibility + U0/C0 ordering + U0 foundation replay | Multi-campaign historical gate; migrate only with explicit replacement | `governance-campaign` |
| `device-catalog-stm32-post-u0-selection-validation.yml` | PR + `main` | Evidence/selection tests + frozen bytes + hard-lock | Candidate for historical/governance replay | `governance-campaign` |
| `device-catalog-stm32-post-c0-selection-validation.yml` | PR + `main` | Evidence policy + selection controls + frozen bytes + hard-lock | Candidate for historical/governance replay | `governance-campaign` |
| `device-catalog-stm32-post-l0-selection-validation.yml` | PR + dispatch | Selection tests + hard-locked replay + research-only boundary | Candidate for historical/governance replay | `governance-campaign` |
| `device-catalog-post-u5-frontier-selection-validation.yml` | PR + `main` | Frozen post-U5 frontier selection | Unique validator today; migrate before retirement | `governance-campaign` |
| `device-catalog-stm32-trustzone-cohort-gate1-validation.yml` | PR + `main` | Deterministic TrustZone cohort qualification + zero Production writes | Candidate for security/governance replay, not generic family matrix | `governance-campaign` |
| `device-catalog-stm32-trustzone-cohort-succession-after-l5-blocker-validation.yml` | PR + `main` | Frozen TrustZone succession decision + zero Production writes | Unique validator today; migrate before retirement | `governance-campaign` |
| `device-catalog-stm32h7-partitioned-scope-selection-validation.yml` | PR + `main` | Frozen H7 partition selection | Frontier campaign; migration/closure decision required | `governance-campaign` |
| `device-catalog-stm32h7rs-evidence-accessibility-validation.yml` | PR + `main` | Retained H7RS official-ST accessibility evidence | Frontier evidence campaign; migration/closure decision required | `governance-campaign` |

These are the strongest workflow-count reduction candidates. Several validators are currently owned only by their dedicated workflow, so deleting the YAML today would remove unique regression coverage. Preferred migration is to an explicit historical/governance replay runner with path-based affected checks, or a documented campaign closure when the invariant no longer needs executable CI.

## 12. Manual live acquisition outside the `device-catalog-*` prefix

| Workflow | Trigger | Authority / coverage | Disposition | Lifecycle |
|---|---|---|---|---|
| `stm32f1-live-acquisition-pilot.yml` | dispatch only | Live ST transport preflight, bounded F1 acquisition, drift evaluation, retained artifact | Keep manual; not a normal PR gate | `manual-live` |

Together with the L0/L4/U0 live workflows, this confirms that external acquisition is already largely separated from deterministic PR validation.

## 13. Consolidation sequence

No workflow is retired in this inventory PR. Implementation should proceed in separate, reviewable changes:

1. **Behavior-neutral hygiene:** repair STM32U0 family-dispatch trigger parity; remove stale dispatcher path references; remove the missing U5 HIL-workflow trigger reference. Add trigger-contract tests so these defects cannot recur.
2. **C0 parity consolidation:** move all C0 stage-only deterministic replay/publication checks into the family profile or another explicit replacement gate; prove trigger and negative-control parity; then retire only the redundant C0 stage YAML files.
3. **L0/L1/L4 stage orchestration:** design reusable stage primitives only if they preserve each family’s trigger, artifact, replay and Production-boundary semantics. Do not mechanically add families to the existing dispatcher.
4. **Security/HIL mechanics:** extract common setup and fail-closed Production-write checks where useful, while keeping L5/U3/U5 security/HIL authorities separately visible.
5. **Historical/governance replay:** migrate completed selection/prioritization/frontier/requalification validators into a bounded historical/governance runner; retire campaign YAML only after each validator has a tested replacement or documented closure.
6. **Domain contract review:** decide whether `icpn-catalog-admission-separation-validation.yml` remains standalone or becomes an explicitly named check inside a core catalog/repository contract workflow. Do not lose the invariant.

## 14. Phase 2 exit criteria

The current workflow set is inventoried. Phase 2 consolidation is complete only when implementation PRs additionally prove that:

- historical, current, Production, family, security/HIL, live-source, and cross-domain boundaries remain explicit;
- STM32U0 dispatcher trigger parity is repaired;
- stale workflow trigger references are removed and regression-tested;
- every retired workflow points to a tested replacement authority or a documented closed campaign;
- C0 or later family-stage retirement includes validator-command parity and negative controls;
- non-catalog PRs gain no new Device Catalog jobs;
- live external acquisition remains non-mandatory for ordinary PRs;
- `scripts/ci/device-catalog-trigger-governance.py` remains green with zero trigger-debt violations;
- CI architecture documentation reflects the resulting authority model.
