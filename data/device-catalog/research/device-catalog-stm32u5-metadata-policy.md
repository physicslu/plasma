# STM32U5 Metadata Policy

## Purpose

This gate defines a fail-closed, manufacturer-authoritative metadata policy for the **266 exact STM32U5 ICPNs** already frozen by `stm32u5-exact-orderable-identity-enumeration.json`.

It does **not** discover new identities, write Production catalog data, authorize programming, define security-state behavior, or claim HIL support.

## First-principles boundary

Identity and metadata are separate authorities:

1. **Exact identity authority** — ST Quality & Reliability exact Part Number rows.
2. **Metadata decode authority** — the applicable official ST datasheet Ordering Information table.
3. **Execution authority** — explicitly out of scope for this gate.

A syntactically plausible part number is never sufficient to create a new ICPN. Metadata decoding is allowed only for one of the retained 266 exact identities.

## Ordering-information authorities

| Authority group | Retained subfamilies | Base Devices | Exact ICPNs | Datasheet |
| --- | --- | ---: | ---: | --- |
| STM32U535 | STM32U535 | 11 | 53 | DS14217 Rev 5 |
| STM32U545 | STM32U545 | 5 | 17 | DS14216 Rev 5 |
| STM32U575 | STM32U575 | 14 | 62 | DS13737 Rev 10 |
| STM32U585 | STM32U585 | 7 | 43 | DS13086 Rev 10 |
| STM32U59xxx | STM32U595, STM32U599 | 17 | 44 | DS13633 Rev 3 |
| STM32U5Axxx | STM32U5A5, STM32U5A9 | 10 | 31 | DS13543 Rev 3 |
| STM32U5Fxxx | STM32U5F7, STM32U5F9 | 5 | 8 | DS14395 Rev 4 |
| STM32U5Gxxx | STM32U5G7, STM32U5G9 | 5 | 8 | DS14102 Rev 5 |

The decoder retains only exact observed suffixes. `TR` means tape-and-reel; `Q` is retained as the SMPS dedicated-pinout code where documented. Programmed-part wildcards and inferred suffix combinations are forbidden.

## Known authority gap

`STM32U5G9ZJJ3Q` is an exact manufacturer-observed **Preview** identity and remains inside the 266-ICPN retained identity boundary.

However, DS14102 Rev 5 Ordering Information defines temperature code `6` for STM32U5Gxxx and does not define code `3`. Plasma therefore refuses to infer `temperature_grade` for this ICPN.

Result of this gate:

- retained exact identities: **266**
- metadata-ready exact identities: **265**
- manual review required: **1**
- rejected retained identities: **0**
- scope expansion: **0**
- Production exact ICPNs: **2,017** unchanged

The one manual-review result is deliberate fail-closed behavior, not a missing identity.

## Governance

This policy does not authorize:

- Production catalog admission
- Preview-to-Production promotion
- security or option-byte semantics
- OEM key semantics
- Flash geometry or programming-algorithm equivalence
- runtime programming
- debug attach
- physical validation or HIL

The next research gate is `stm32u5-metadata-authority-delta-resolution`, which must resolve the current datasheet/Preview authority mismatch before canonical admission planning proceeds.
