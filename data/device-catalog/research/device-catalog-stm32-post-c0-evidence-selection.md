# STM32 post-C0 next-family evidence selection

Date: 2026-09-12

## Scope

This transaction selects the next STM32 family for **research only** after STM32C0 C0.5 publication. It does not admit any ICPN, modify Production, define programming behavior, or claim physical/HIL/runtime support.

Production is frozen for this transaction at:

- 912 exact ICPNs
- 293 Base Devices
- 10 STM32 families
- STM32C0 Production exact ICPNs: 209

The immutable Production prestate is `stm32-post-c0-production-manifest-prestate.json`.

## Candidate surface

The current read-only cross-family shortlist was:

1. STM32L1
2. STM32L0
3. STM32L4

One lexical-min Base Device was selected per guarded OpenOCD ordering-pattern subfamily:

| Series | Representative targets |
| --- | ---: |
| STM32L1 | 4 |
| STM32L0 | 16 |
| STM32L4 | 24 |
| **Total** | **44** |

OpenOCD only bounds the research surface. It is not commercial identity or lifecycle authority.

## Authoritative live evidence

The official-ST dual-surface acquisition transaction is retained under:

`evidence/stm32-l1-l0-l4-post-c0-live-2026-09-12/`

Authoritative workflow run: `34674798156`.

The authority model is:

- Quality & Reliability: exact commercial Part Number identity
- Sample & Buy: Marketing Status
- lifecycle status is joined only when exact Part Number sets match fail-closed

Observed result:

| Series | Targets | Active targets | Lifecycle-excluded targets | Active exact ICPNs observed | Non-Active exact variants | Manual review |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| STM32L1 | 4 | 1 | 3 | 1 | 8 | 0 |
| STM32L0 | 16 | 16 | 0 | 44 | 0 | 0 |
| STM32L4 | 24 | 24 | 0 | 60 | 3 | 0 |

STM32L1 is deprioritized for this next-family transaction because three of four representative subfamilies expose only NRND exact identities. This is not a rejection of STM32L1 for future support.

STM32L4 remains eligible. Its three observed non-Active exact variants are additional STM32L462 proposal/preview/evaluation variants while Active STM32L462 exact identities remain available; lifecycle is therefore kept at exact-variant granularity rather than incorrectly promoted to family-level exclusion.

## Ordering Information gate

After the lifecycle gate, the eligible families are STM32L0 and STM32L4.

`stm32-l0-l4-post-c0-ordering-authority-review.json` binds the official ST datasheet Ordering Information review.

- STM32L0: 16/16 representative targets covered, 16 official datasheets, zero blocking evidence issues.
- STM32L4: 24/24 representative targets covered by 20 official datasheets, zero blocking evidence issues.
- Required schema: device family, product type, device subfamily, pin count, Flash size, package, temperature range, packing/options.
- Required evidence quality is equivalent and complete for both eligible families.

The Ordering Information review is commercial metadata evidence only. It does not prove Flash algorithm/geometry equivalence, option/security semantics, socket/electrical support, HIL, or runtime programming support.

## Deterministic selection

With manufacturer lifecycle evidence complete and Ordering Information quality equivalent, the existing post-C0 shortlist order is the final tie-break.

Result:

`selected_next_research_family = STM32L0`

Frozen selection:

`stm32-post-c0-next-family-selection.json`

SHA-256:

`a46cef39516bf94901b979ccfc446b5720b2c6855b46ede1765232f6082df134`

This selection authorizes only a future STM32L0 research/discovery Gate 1 proposal. It does not authorize that future phase itself.

## Fail-closed validation

Permanent offline validation covers:

- 44-target deterministic boundary
- zero manual-review requirement
- official-ST source boundary
- exact-set join integrity
- retained summary/provenance/target digests
- all 44 per-target evidence JSONs matching the authoritative summary
- immutable 912-row Production prestate
- L1 lifecycle deprioritization semantics
- L4 exact-variant lifecycle semantics
- L0/L4 Ordering Information completeness
- deterministic selection replay
- all support/admission authority boundaries remaining false

No Production write occurs in this transaction.
