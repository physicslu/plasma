# Device Catalog Phase 4.5A — STM32F0 Bounded Discovery Foundation

## Decision

STM32F0 is the next STM32 ICPN expansion target after STM32F2 and STM32F3.

The retained Phase 4.3A prioritization ranked the eligible families as:

```text
STM32F2 -> STM32F3 -> STM32F0 -> STM32F7
```

STM32F2 and STM32F3 are now in Production. Phase 4.5A therefore continues the retained deterministic sequence with STM32F0 rather than re-ranking families ad hoc.

Phase 4.5A establishes only the deterministic OpenOCD source surface and initial Base Device set required before official ST acquisition. It does not perform live manufacturer acquisition, define metadata/admission policy, or modify Production.

## Guarded source surface

A one-off read-only GitHub Actions probe was executed against the repository catalog before the permanent contract was written:

- run: `34314647551`;
- artifact: `10089609203`;
- source: `openocd-parts-canonical.csv`;
- STM32F0 rows: 111;
- unique ordering patterns: 111;
- identifier kind: `ordering_pattern` for 111/111;
- target config: `tcl/target/stm32f0x.cfg` for 111/111;
- OpenOCD distribution: `upstream-openocd` for 111/111;
- mapping status: `mapping_candidate` for 111/111;
- validation status: `not_verified` for 111/111.

The temporary probe workflow is not part of the permanent Phase 4.5A architecture and is removed before this PR is ready for merge.

## Thirteen source subfamilies

| Source subfamily | Rows | Deterministic first concrete Base Device |
|---|---:|---|
| STM32F030 | 7 | `STM32F030C6` |
| STM32F031 | 10 | `STM32F031C4` |
| STM32F038 | 5 | `STM32F038C6` |
| STM32F042 | 13 | `STM32F042C4` |
| STM32F048 | 3 | `STM32F048C6` |
| STM32F051 | 17 | `STM32F051C4` |
| STM32F058 | 4 | `STM32F058C8` |
| STM32F070 | 4 | `STM32F070C6` |
| STM32F071 | 10 | `STM32F071C8` |
| STM32F072 | 13 | `STM32F072C8` |
| STM32F078 | 7 | `STM32F078CB` |
| STM32F091 | 11 | `STM32F091CB` |
| STM32F098 | 7 | `STM32F098CC` |

The OpenOCD source rows are ordering patterns such as `STM32F030C6Tx`. The final package code plus wildcard are routing syntax, not part of the Base Device identity. Phase 4.5A therefore extracts `STM32F030C6`, not the probe-only intermediate string `STM32F030C6T`.

## Deterministic selection

Phase 4.5A delegates ordering to the existing generic `deterministic_first_unadmitted_targets()` core with an empty STM32F0 Production boundary. The initial bounded discovery set is the lexicographically first concrete Base Device in each guarded source subfamily.

This is a 13-Base-Device discovery batch. It is not an ICPN-count batch and it is not a runtime-support batch.

## Mapping boundary

The foundation verifies ordering-pattern routing using synthetic routing values only. These probes show that the current OpenOCD catalog can route each selected Base Device through exactly one ordering pattern and the single `tcl/target/stm32f0x.cfg` target config.

OpenOCD routing is not an authority for commercial ICPN existence. Synthetic routing values are not manufacturer evidence and must not be persisted as exact ICPNs.

## Fail-closed conditions

Offline regression rejects:

- STM32F0 source-row count drift;
- subfamily count/set drift;
- non-ordering-pattern identifiers;
- target-config drift;
- OpenOCD distribution drift;
- mapping/validation-status drift;
- malformed or non-concrete ordering patterns.

## Claims intentionally false

Phase 4.5A keeps all of the following false:

- manufacturer evidence retained;
- exact commercial ICPN asserted;
- canonical dataset admission;
- Production write authorization;
- programming policy defined;
- runtime support claimed.

## Next gate

The next ICPN engineering step is Phase 4.5B: bounded official-ST discovery for the 13 deterministic Base Devices.

That discovery must establish manufacturer-backed exact commercial identities and lifecycle evidence. OpenOCD mapping may be recorded as an orthogonal capability/routing fact, but lack of runtime/PPU/Socket support must not be confused with commercial ICPN identity.

Only after retained manufacturer evidence exists should STM32F0 metadata and admission policy be designed.
