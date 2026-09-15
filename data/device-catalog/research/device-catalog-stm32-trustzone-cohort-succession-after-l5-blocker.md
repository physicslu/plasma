# STM32 TrustZone cohort succession after STM32L5 external blocker

## Purpose

This research-only gate records a deterministic succession decision after the rank-1 TrustZone candidate, STM32L5, reached an external physical-hardware dependency. It does not modify the original Gate1 ranking and does not reinterpret the STM32L5 result as a family failure.

## Upstream evidence

- `stm32-trustzone-cohort-gate1-qualification.json` retains the original ranking: STM32L5 rank 1, STM32U3 rank 2, STM32U5 rank 3.
- `stm32l5-hil-fixture-acquisition-provenance.json` records zero verified physical acquisition, `hil_execution_ready=false`, blocker type `external_hardware_acquisition_required`, and no next software-only STM32L5 research gate.

## Succession rule

Preserve the original ranking. A candidate may be skipped only while an explicit merged external blocker prevents further software-only progress. The blocked candidate remains paused and may resume when its external dependency is satisfied.

Under that rule, STM32U3 is the first unblocked candidate and becomes the next software-only TrustZone research target.

## STM32U3 bounded scope

- rank: 2
- subfamilies: 8
- catalog evidence rows: 171
- ordering-pattern rows: 75
- CMSIS-device-name rows: 96
- target config: `tcl/target/stm32u3x.cfg`
- structural gate: pass
- mapping metadata: complete

Selection remains catalog/research evidence only. It does not establish Flash geometry, programming-algorithm equivalence, TrustZone semantics, option-byte semantics, HIL validation, runtime programming, or Production admission.

## Production boundary

No Production catalog write is authorized by this transaction.

**Exact ICPN count: 1,862**.

## Next research gate

`stm32u3-security-scope-foundation`
