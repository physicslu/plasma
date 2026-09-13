# STM32L1 Phase L1.1 — Foundation

## Status and scope

STM32L1 L1.1 is a bounded **research foundation** transaction. It consumes the completed H024 lifecycle requalification, freezes the current OpenOCD-derived L1 research surface, and binds one deterministic representative Base Device per guarded subfamily to already-retained official-ST lifecycle and Ordering Information evidence.

L1.1 does **not** perform complete commercial discovery, canonical admission, Production publication, programming-policy definition, Flash-algorithm/geometry equivalence, option/security qualification, PPU/Socket electrical qualification, HIL, or runtime-support qualification.

## Frozen starting state

Post-L4 Production prestate:

```text
Production exact ICPNs: 1718
Production Base Devices: 530
STM32 families: 12
STM32L4 Production: 446
STM32L1 Production: 0
```

## OpenOCD research surface

OpenOCD is used only to bound the research surface and route family/subfamily structure. It is not commercial identity or programming authority.

```text
source rows:        132
ordering patterns:   87
CMSIS aliases:       45
subfamilies:           4
target config: tcl/target/stm32l1.cfg
```

The four deterministic representatives are:

`STM32L100C6`, `STM32L151C6`, `STM32L152C6`, `STM32L162QC`.

Selection rule: lexical-min concrete Base Device from each guarded OpenOCD ordering-pattern subfamily.

## Retained manufacturer-authoritative evidence

No new ST acquisition is required for L1.1. H024 already retained generation-aware official-ST commercial identity/lifecycle evidence for all four representatives:

```text
representative Base Devices:          4
Active exact ICPNs observed:          9
non-Active exact variants retained:   8
active subfamilies:                  4/4
manual review:                        0
source unavailable:                   0
```

The non-Active variants remain exact-variant lifecycle dispositions. They must not be promoted by the foundation transaction. The generation-A companion pages for STM32L100/L151/L152 are essential evidence; the previous single-page family-level lifecycle extrapolation was invalidated by H024.

## Ordering Information authority

Official ST Ordering Information coverage is complete across all four subfamilies:

- STM32L100 generation A: `DocID025966 Rev 6`
- STM32L151 / STM32L152 generation A: `DocID024330 Rev 5`
- STM32L162: `DS10287 Rev 6`
- generation migration authority: `TN1176`

Ordering Information is metadata evidence only; it does not establish physical programming support.

## Validation model

The L1.1 validator fails closed on:

- OpenOCD catalog byte drift;
- row-count, identifier-kind, target-config or subfamily drift;
- deterministic representative drift;
- H024 requalification-result drift;
- generation-aware target-manifest drift;
- retained exact lifecycle evidence drift;
- Ordering Information or TN1176 authority drift;
- frozen Production prestate drift;
- any authority-boundary claim escaping `false`.

## Production boundary

L1.1 performs **zero Production writes**.

```text
Production exact ICPNs: 1718 (delta 0)
Production Base Devices: 530 (delta 0)
Production families: 12 (delta 0)
STM32L1 Production: 0
```

The next transaction, if separately authorized, is **STM32L1 Phase L1.2 — Manufacturer-Authoritative Commercial Discovery**. L1.2 must determine the complete current commercial exact-ICPN surface; the 9 Active exact ICPNs retained for L1.1 representatives are not a complete-family inventory.
