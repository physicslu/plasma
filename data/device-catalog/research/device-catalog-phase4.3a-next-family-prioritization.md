# Device Catalog Phase 4.3A — Next STM32 Family Prioritization

Phase 4.2AL closes the current STM32F4 research surface with zero actionable
Base Device gaps. Phase 4.3A selects the next bounded family to investigate; it
does not admit a family or any exact ICPN into Production. The guarded
Production baseline is 459 exact ICPNs and 157 Base Devices: STM32F1 is 75/18
and STM32F4 is 384/139.

## Decision

`STM32F2` is the next research family.

The deterministic inventory reads the current OpenOCD-derived catalog and the
Production manifest. Production contains 459 exact ICPNs across STM32F1 and
STM32F4. The source catalog contains 23 STM32 `plasma_series` values, leaving 21
candidate series and 2,105 source rows outside Production.

The first third-family pilot is deliberately restricted to the STM32 F-line
cohort. A candidate is eligible only when every source row is an
`ordering_pattern`, every row has complete mapping metadata, every row retains
the current upstream/candidate/not-verified source contract, and the complete
series routes through exactly one OpenOCD target configuration. This produces:

| Rank | Series | Source rows | OpenOCD target |
|---:|---|---:|---|
| 1 | STM32F2 | 47 | `tcl/target/stm32f2x.cfg` |
| 2 | STM32F3 | 90 | `tcl/target/stm32f3x.cfg` |
| 3 | STM32F0 | 111 | `tcl/target/stm32f0x.cfg` |
| 4 | STM32F7 | 123 | `tcl/target/stm32f7x.cfg` |

The smallest eligible surface wins so that third-family adapter and policy
assumptions are tested with the narrowest current blast radius. STM32F2 covers
four source subfamilies: STM32F205, STM32F207, STM32F215, and STM32F217.

## Evidence boundary

The 47 STM32F2 rows are OpenOCD routing candidates only:

- 47 `ordering_pattern` identifiers;
- 0 `manufacturer_part_number` identifiers;
- one OpenOCD target config;
- 47 `mapping_candidate` rows;
- 47 `not_verified` rows.

Consequently Phase 4.3A makes none of the following claims:

- no exact commercial ICPN is derived from an ordering pattern;
- no current ST marketing lifecycle is inferred;
- no programming-algorithm equivalence with STM32F1 or STM32F4 is inferred;
- no STM32F2 row is admission-ready;
- no Production, IC Support, runtime, or REST content changes.

## Next gate

Phase 4.3B must perform a bounded, read-only official-ST discovery for STM32F2.
It must establish current lifecycle and exact commercial part-number evidence
before proposing an adapter, policy, or Production admission. If official
evidence exposes no Active exact ICPNs, ambiguity, or a different identifier
topology, the work fails closed and returns to the ranking rather than inferring
missing data.

## Reproduction

```bash
python data/device-catalog/research/stm32_next_family_prioritization.py
python data/device-catalog/research/test_stm32_phase4_3a_next_family_prioritization.py
```

The regression binds the current source and Production hashes, the complete
eligible ranking, the selected STM32F2 contract, and negative mutations for
mixed identifier kinds, split target routing, and unexpected source-contract
status.
