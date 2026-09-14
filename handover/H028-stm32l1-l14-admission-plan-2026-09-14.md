# H028 — STM32L1 L1.4 Read-only Capability / Admission Plan

Date: 2026-09-14
Status: **Gate 1 implementation complete; Gate 2 merge approval required**
PR: #552 — `Device catalog: plan STM32L1 L1.4 read-only admission`
Branch: `agent/device-catalog-stm32l1-l14-admission-plan`

## 1. Approved Gate 1 scope

L1.4 consumes merged L1.2 identity and merged L1.3 metadata, then applies an independent OpenOCD ordering-pattern capability-routing gate.

Approved work:
- replay all 144 manufacturer-verified / metadata-ready exact ICPNs;
- require exactly one OpenOCD ordering-pattern route to `tcl/target/stm32l1.cfg` for capability admission;
- keep ambiguous/unmapped exact identities out of admission without rejecting their commercial identity;
- freeze a deterministic read-only admission plan;
- add negative controls, permanent offline validation, and a zero-Production-diff guard.

Explicitly outside scope: canonical publication, Production writes, Flash geometry, erase/program algorithm equivalence, option/security programming qualification, electrical/socket qualification, HIL, PPU deployment, and runtime programming support.

## 2. Frozen inputs

L1.3:
- Base Devices: **59**
- manufacturer-verified Active exact ICPNs: **144**
- metadata-ready: **144**
- manual review / reject / exception: **0 / 0 / 0**
- metadata-ready exact-set SHA-256: `0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12`
- metadata rows SHA-256: `c794a21a63e72d805170034defe4af4e749ce456966f9083efe2f4abfa4fe247`
- L1.3 baseline Git blob: `55a0c05d9fdbc527b7e2bfb2fb4ac5d99b000c58`
- L1.3 baseline SHA-256: `6da49ceda71a3611244e1961e6aca3809d5809f8f7106834123c6ae48e726e62`

OpenOCD research surface:
- catalog Git blob: `0ef056e3363e20bb527590c4a4cc1cc0d7afb810`
- catalog SHA-256: `43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`
- required target config: `tcl/target/stm32l1.cfg`

Production prestate/poststate:
- exact ICPNs: **1,718**
- Base Devices: **530**
- families: **12**
- STM32L1 Production exact ICPNs: **0**
- manifest Git blob: `1aa2311a25a69742c428147a402816ed5071e04e`

## 3. Capability replay

Calibration workflow:
- `STM32L1 L1.4 admission-plan calibration`
- run: **34806076943**
- executed head: `b7e1cef2caf4812a18a3d9d008b5125e998a1a08`
- result: **SUCCESS**

Replay result:
- capability-admittable: **144**
- capability-unresolved: **0**
- unique routes: **144**
- ambiguous routes: **0**
- unmapped routes: **0**
- admit: **144**
- already present: **0**
- manual review: **0**
- reject: **0**

All admitted exact ICPNs route through one deterministic ordering pattern to `tcl/target/stm32l1.cfg`.

## 4. Frozen plan and permanent validation

Frozen plan:
`data/device-catalog/research/stm32l1-phase-l1.4-admission-plan.json`

Plan Git blob:
`6b75db8c09809534eba530e07ff11cf91085677f`

Plan SHA-256:
`ea413a7c1761eded8875737c9e8fde3ff359a4bf52dfde1f52a795179d2457e4`

Permanent validator:
`data/device-catalog/research/validate_stm32l1_phase_l1_4_admission_plan.py`

Permanent CI:
`.github/workflows/device-catalog-stm32l1-l14-admission-plan-validation.yml`

Permanent validation requires:
- L1.3 hard-lock validation remains clean;
- frozen plan bytes/digest remain fixed;
- deterministic replay equals the frozen plan;
- 144 / 144 exact ICPNs remain capability-admittable;
- ambiguous/unmapped remain zero;
- admitted exact set equals the L1.3 metadata-ready exact set;
- canonical prestate remains absent/zero-row;
- Production remains 1,718 / 530 / 12 / STM32L1=0;
- all programming/runtime/HIL claims remain false.

## 5. Interpretation

OpenOCD is used only as a capability-routing prerequisite. It is not manufacturer commercial identity authority and does not prove physical programming support.

L1.4 establishes a clean read-only admission plan. It does **not** publish STM32L1 to Production.

## 6. Next governance step

After synchronized final CI passes, PR #552 requires explicit **Gate 2 Merge approval**.

A future L1.5 publication transaction requires a separate Gate 1.
