# STM32L1 L1.4 Read-only Capability / Admission Plan

## Scope

L1.4 consumes the merged L1.2 manufacturer-authoritative exact identity set and the merged L1.3 manufacturer-authoritative metadata policy, then applies one independent OpenOCD ordering-pattern routing gate. It is planning only: no canonical dataset or Production write is performed.

## Frozen inputs

- 59 Base Devices
- 144 manufacturer-verified Active exact ICPNs
- 144 / 144 metadata-ready
- L1.3 metadata-ready exact set SHA-256: `0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12`
- L1.3 metadata rows SHA-256: `c794a21a63e72d805170034defe4af4e749ce456966f9083efe2f4abfa4fe247`
- OpenOCD catalog Git blob: `0ef056e3363e20bb527590c4a4cc1cc0d7afb810`
- OpenOCD catalog SHA-256: `43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`
- required target config: `tcl/target/stm32l1.cfg`

## Capability replay

Calibration run `34806076943`, head `b7e1cef2caf4812a18a3d9d008b5125e998a1a08`, completed successfully.

Result:
- capability-admittable: **144**
- capability-unresolved: **0**
- OpenOCD route replay: **144 unique / 0 ambiguous / 0 unmapped**
- admission decisions: **144 admit / 0 already present / 0 manual review / 0 reject**
- canonical rows before: **0**
- canonical dataset admission: **planned**

An OpenOCD route is a capability-routing prerequisite only. It does not establish programming-algorithm equivalence, Flash geometry, option/security semantics, electrical/socket qualification, HIL, PPU deployment, or runtime support.

## Frozen plan

- `stm32l1-phase-l1.4-admission-plan.json`
- Git blob: `6b75db8c09809534eba530e07ff11cf91085677f`
- SHA-256: `ea413a7c1761eded8875737c9e8fde3ff359a4bf52dfde1f52a795179d2457e4`

Permanent validation deterministically rebuilds the plan, verifies all 144 exact routes remain unique, requires the admitted exact set to equal the L1.3 metadata-ready set, and fails closed on any mapping or Production drift.

## Production boundary

Production remains unchanged:
- exact ICPNs: **1,718**
- Base Devices: **530**
- families: **12**
- STM32L1 exact ICPNs: **0**

## Next phase

L1.5 may perform bounded canonical/Production publication only under a separate Gate 1 after L1.4 merges. L1.4 itself authorizes no write.
