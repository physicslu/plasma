# Device Catalog Phase 4.4A — STM32F3 Bounded Discovery Foundation

## Decision

STM32F3 is the fourth STM32 family expansion target.

This is not a discretionary choice. The retained Phase 4.3A prioritization
contract ranks STM32F3 immediately after STM32F2; its regression explicitly
requires STM32F3 to become the next selected family when STM32F2 is removed
from the eligible set.

Phase 4.4A establishes only the deterministic source-surface and routing
foundation required before official ST acquisition. It does not perform live
manufacturer acquisition, define an admission policy, or modify Production.

## Guarded source surface

A one-off read-only GitHub Actions probe was executed against the repository
catalog itself before this contract was written:

- run: `34199585215`;
- source: `openocd-parts-canonical.csv`;
- STM32F3 rows: 90;
- identifier kind: `ordering_pattern` for 90/90;
- target config: `tcl/target/stm32f3x.cfg` for 90/90;
- OpenOCD distribution: `upstream-openocd` for 90/90;
- mapping status: `mapping_candidate` for 90/90;
- validation status: `not_verified` for 90/90.

The temporary probe workflow was removed after the source shape was captured;
normal validation is offline and deterministic.

## Six source subfamilies

| Source subfamily | Rows | Deterministic first concrete Base Device |
|---|---:|---|
| STM32F301 | 8 | `STM32F301C6` |
| STM32F302 | 22 | `STM32F302C6` |
| STM32F303 | 24 | `STM32F303C6` |
| STM32F373 | 12 | `STM32F373C8` |
| STM32F3x4 | 12 | `STM32F334C4` |
| STM32F3x8 | 12 | `STM32F318C8` |

The `STM32F3x4` and `STM32F3x8` values are source classification labels, not
ST product-page identities. Their ordering-pattern rows contain concrete
families such as STM32F334 and STM32F318/328/358/378/398. Target selection
therefore operates on the concrete Base Device extracted from each ordering
pattern, never on the wildcard-bearing subfamily label.

## Deterministic selection

Phase 4.4A delegates target ordering to the existing generic
`deterministic_first_unadmitted_targets()` core with an empty STM32F3
Production boundary. The first bounded discovery set is therefore the
lexicographically first concrete Base Device in each of the six guarded source
subfamilies.

This is a six-Base-Device batch. It is not an ICPN-count batch.

## Mapping boundary

The foundation verifies ordering-pattern routing using synthetic routing values
only. These probes demonstrate that the current OpenOCD catalog resolves each
selected Base Device through exactly one ordering pattern and exactly one
`tcl/target/stm32f3x.cfg` target.

Synthetic routing values are not commercial manufacturer evidence and must not
be persisted as exact ICPNs.

## Fail-closed conditions

Offline regression rejects:

- STM32F3 source-row count drift;
- subfamily count/set drift;
- non-ordering-pattern identifiers;
- target-config drift;
- OpenOCD distribution drift;
- mapping/validation-status drift;
- malformed or non-concrete ordering patterns.

## Claims intentionally false

Phase 4.4A keeps all of the following false:

- manufacturer evidence retained;
- exact commercial ICPN asserted;
- canonical dataset admission;
- Production write authorization;
- programming policy defined;
- runtime support claimed.

## Next gate

The next engineering step is a bounded official-ST discovery transaction for
the six deterministic Base Devices. Before retention, the acquisition must
prove that each ST product page is authoritative, exposes Active exact
commercial ICPNs, and that every candidate maps uniquely back to the guarded
STM32F3 ordering-pattern surface.

Only after retained manufacturer evidence exists should STM32F3 metadata and
admission policy be designed.
