# Device Catalog Phase 4.6A — STM32F7 Bounded Discovery Foundation

## Decision

STM32F7 is the next STM32 ICPN expansion family after STM32F2, STM32F3, and STM32F0.

The retained Phase 4.3A prioritization ranked the eligible families as:

```text
STM32F2 -> STM32F3 -> STM32F0 -> STM32F7
```

STM32F2, STM32F3, and STM32F0 are now in Production. Phase 4.6A therefore continues the retained deterministic sequence with STM32F7 rather than re-ranking families ad hoc.

Phase 4.6A establishes only the deterministic OpenOCD source surface and initial Base Device set required before official ST acquisition. It does not perform live manufacturer acquisition, define metadata/admission policy, or modify Production.

## Guarded source surface

A one-off read-only GitHub Actions inspection was executed before the permanent contract was written:

- run: `34323571759`;
- source: `openocd-parts-canonical.csv`;
- STM32F7 rows: 123;
- source subfamilies: 16;
- identifier kind: `ordering_pattern` for 123/123;
- target config: `tcl/target/stm32f7x.cfg` for 123/123;
- OpenOCD distribution: `upstream-openocd` for 123/123;
- mapping status: `mapping_candidate` for 123/123;
- validation status: `not_verified` for 123/123.

The temporary inspection workflow is not part of the permanent Phase 4.6A architecture and is removed before merge.

## Sixteen source subfamilies

| Source subfamily | Rows | Deterministic first concrete Base Device |
|---|---:|---|
| STM32F722 | 10 | `STM32F722IC` |
| STM32F723 | 12 | `STM32F723IC` |
| STM32F730 | 4 | `STM32F730I8` |
| STM32F732 | 5 | `STM32F732IE` |
| STM32F733 | 6 | `STM32F733IE` |
| STM32F745 | 10 | `STM32F745IE` |
| STM32F746 | 16 | `STM32F746BE` |
| STM32F750 | 3 | `STM32F750N8` |
| STM32F756 | 8 | `STM32F756BG` |
| STM32F765 | 14 | `STM32F765BG` |
| STM32F767 | 14 | `STM32F767BG` |
| STM32F768 | 1 | `STM32F768AI` |
| STM32F769 | 8 | `STM32F769AG` |
| STM32F777 | 7 | `STM32F777BI` |
| STM32F778 | 1 | `STM32F778AI` |
| STM32F779 | 4 | `STM32F779AI` |

The source rows are ordering patterns such as `STM32F722ICKx`. The final package code plus wildcard are routing syntax, not part of the Base Device identity. Phase 4.6A therefore extracts `STM32F722IC`, not `STM32F722ICK`.

## Deterministic selection

Phase 4.6A delegates ordering to the existing generic `deterministic_first_unadmitted_targets()` core with an empty STM32F7 Production boundary. The initial bounded discovery set is the lexicographically first concrete Base Device in each guarded source subfamily.

This is a 16-Base-Device discovery batch. It is not a 123-ICPN admission batch and it is not a runtime-support batch.

## Mapping boundary

The foundation verifies ordering-pattern routing using synthetic routing values only. These probes demonstrate that the current OpenOCD source can route each selected Base Device through exactly one ordering pattern and the single `tcl/target/stm32f7x.cfg` target config.

OpenOCD routing is not an authority for commercial ICPN existence. Synthetic routing values are not manufacturer evidence and must not be persisted as exact ICPNs.

## Fail-closed conditions

Offline regression rejects:

- STM32F7 source-row count drift;
- subfamily count/set drift;
- non-ordering-pattern identifiers;
- target-config drift;
- OpenOCD distribution drift;
- mapping-status drift;
- validation-status drift;
- malformed or non-concrete ordering patterns.

## Claims intentionally false

Phase 4.6A keeps all of the following false:

- manufacturer evidence retained;
- exact commercial ICPN asserted;
- canonical dataset admission;
- Production write authorization;
- programming policy defined;
- runtime support claimed.

## Next gate

The next ICPN engineering step is Phase 4.6B: bounded official-ST discovery for the 16 deterministic Base Devices.

That discovery must establish manufacturer-backed exact commercial identities and lifecycle evidence. OpenOCD mapping may be retained as an orthogonal capability/routing fact, but it must not be promoted into commercial identity evidence.

Only after retained manufacturer evidence exists should STM32F7 metadata and admission policy be designed.
