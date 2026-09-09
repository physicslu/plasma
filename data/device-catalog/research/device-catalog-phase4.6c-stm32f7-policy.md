# Device Catalog Phase 4.6C — STM32F7 Metadata Policy

## Decision

Phase 4.6C converts only the retained **Active** Phase 4.6B commercial identities into deterministic canonical metadata candidates.

This phase is a metadata-policy gate. It is **not** a Production admission gate and does not claim runtime programming support.

The bounded input is intentionally smaller than the 16-target Phase 4.6B discovery set:

- 9 Active Base Devices;
- 19 Active exact ICPNs;
- 5 lifecycle-only Base Devices remain excluded;
- 2 source-unavailable Base Devices remain unresolved and excluded.

All 19 Active candidates are `metadata_ready`; manual review and rejection counts are both zero.

## Authority separation

Phase 4.6B and Phase 4.6C answer different questions.

Phase 4.6B establishes commercial identity and lifecycle from retained official ST product-page evidence.

Phase 4.6C establishes package, pin count, flash size, temperature grade and packing suffix from official ST ordering-information authority. OpenOCD is not used as metadata authority.

The normal authority groups are:

- STM32F722 / STM32F723 -> `stm32f722ic.pdf`;
- STM32F730 -> `stm32f730i8.pdf`;
- STM32F732 / STM32F733 -> `stm32f732ie.pdf`;
- STM32F745 -> `stm32f745ie.pdf`;
- STM32F778 / STM32F779 -> `stm32f777bi.pdf`.

## STM32F750 exception

`STM32F750N8H6` is handled by a narrow exact-product metadata override.

The retained exact identity is Active, and the official ST exact-product surface supports:

- 64 KiB flash;
- TFBGA216;
- -40 to 85 C;
- exact identity `STM32F750N8H6`.

The generic STM32F750 ordering-table extraction is not treated as sufficient authority for generalized decoding because the observed machine-extracted ordering content is inconsistent with the retained exact x8 product identity.

Therefore:

- `STM32F750N8H6` is accepted;
- a forged `STM32F750N8H7` is rejected;
- no generalized STM32F750 decode is authorized.

This is an explicit evidence conflict boundary, not an implicit exception.

## Frozen Phase 4.6C result

The immutable policy baseline contains:

| Measure | Result |
|---|---:|
| metadata candidates | 19 |
| metadata ready | 19 |
| manual review | 0 |
| reject | 0 |
| Active Base Devices | 9 |
| Production exact ICPNs in frozen prestate | 544 |
| Production Base Devices in frozen prestate | 188 |
| STM32F7 Production exact ICPNs | 0 |

Metadata distribution:

| Dimension | Distribution |
|---|---|
| flash | 64 KiB: 3; 256 KiB: 4; 512 KiB: 10; 2048 KiB: 2 |
| package | UFBGA: 10; LQFP: 6; WLCSP: 2; TFBGA: 1 |
| pin count | 176: 16; 180: 2; 216: 1 |
| temperature | -40 to 85 C: 16; -40 to 105 C: 3 |
| packing suffix | standard: 14; TR: 5 |

The Phase 4.6C Production prestate is frozen separately from the mutable current Production manifest. This prevents later legitimate Production growth from invalidating historical Phase 4.6C replay.

## Fail-closed boundaries

Permanent regression must reject:

- promotion of lifecycle-only identities into the Active candidate set;
- fabricated exact ICPNs for source-unavailable targets;
- unknown package, flash, temperature or option codes;
- generalized STM32F750 decoding beyond the exact retained identity;
- any change to the frozen 544-exact / 188-Base-Device Production prestate;
- metadata baseline drift;
- use of OpenOCD as metadata authority.

## Claims intentionally false or deferred

Phase 4.6C does not claim:

- canonical dataset admission;
- Production write authorization;
- programming-algorithm equivalence;
- physical/electrical target qualification;
- flash programming-policy equivalence;
- runtime support;
- complete STM32F7 commercial-family coverage.

Exact ICPN admission and capability mapping are deferred to **Phase 4.6D**.

## Next gate

Phase 4.6D may consume only the 19 `metadata_ready` exact ICPNs from this frozen policy baseline. It must separately evaluate admission/capability constraints and must preserve the five lifecycle exclusions and two unresolved source-unavailable targets as non-admitted historical evidence.
