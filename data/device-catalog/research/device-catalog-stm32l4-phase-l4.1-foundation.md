# STM32L4 Phase L4.1 — Foundation

## Status and scope

STM32L4 L4.1 is a bounded **research foundation** transaction. It consumes the post-L0 selection that chose `STM32L4`, freezes the current OpenOCD-derived L4 research surface, and binds one deterministic representative Base Device per ordering-pattern subfamily to already-retained official-ST evidence.

L4.1 does **not** perform complete commercial discovery, canonical admission, Production publication, programming-policy definition, Flash-algorithm/geometry equivalence, option/security qualification, PPU/Socket electrical qualification, HIL, or runtime-support qualification.

## Frozen starting state

Post-L0 Production prestate:

```text
Production exact ICPNs: 1272
Production Base Devices: 392
STM32 families: 11
STM32L0 Production: 360
STM32L4 Production: 0
```

The immutable prestate SHA-256 is:

`c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`

The frozen post-L0 selection SHA-256 is:

`70dd86816606e94380fe6a0b0474a88771542607fc7db2aaa3a8be65e1e2e7b8`

## OpenOCD research surface

OpenOCD is used only to bound the research surface and route family/subfamily structure. It is not commercial identity or programming authority.

```text
source rows:        255
ordering patterns:  207
CMSIS aliases:       48
subfamilies:          24
target config: tcl/target/stm32l4x.cfg
```

The 24 deterministic representatives are:

`STM32L412C8`, `STM32L422CB`, `STM32L431CB`, `STM32L432KB`, `STM32L433CB`, `STM32L442KC`, `STM32L443CC`, `STM32L451CC`, `STM32L452CC`, `STM32L462CE`, `STM32L471QE`, `STM32L475RC`, `STM32L476JE`, `STM32L486JG`, `STM32L496AE`, `STM32L4A6AG`, `STM32L4P5AE`, `STM32L4Q5AG`, `STM32L4R5AG`, `STM32L4R7AI`, `STM32L4R9AG`, `STM32L4S5AI`, `STM32L4S7AI`, `STM32L4S9AI`.

Selection rule: lexical-min concrete Base Device from each guarded OpenOCD ordering-pattern subfamily.

## Retained manufacturer-authoritative evidence

No new ST acquisition is required for L4.1. The retained official-ST commercial identity/lifecycle probe already covers all 24 representatives:

```text
representative targets:              24
verified identity targets:           24
Active candidate targets:            24
Active exact ICPNs observed:          60
lifecycle-excluded targets:            0
excluded non-Active exact variants:    3
manual review:                         0
source unavailable:                    0
```

The three non-Active variants are all under representative `STM32L462CE` and remain exact-variant lifecycle dispositions. They are not Active candidates and must not be promoted by the foundation transaction.

Retained probe summary SHA-256:

`45c3020462601e6cb36e726cc1acc4203abc36a96063a5223ab5c7511bcff02c`

Target manifest SHA-256:

`767ad681a7d8e839cbf68b507babb2c417905a2f40a380566e773fa987ab9434`

## Ordering Information authority

The retained official-ST Ordering Information review covers 24/24 representatives using 20 official datasheets:

```text
ordering authority covered targets: 24
required schema complete targets:   24
blocking evidence issues:            0
revision drift:                  false
ordering evidence quality:    complete
```

Review SHA-256:

`d16e71cb322c7da754ed12cc1bd0e984015888cbf8bdb07685e1d87966ad8612`

Important retained semantics include exact-variant lifecycle handling for `STM32L462CE` and package/options distinctions for higher-density L4 devices. Ordering Information is metadata evidence only; it does not establish physical programming support.

## Frozen baseline

Permanent baseline:

`stm32l4-phase-l4.1-foundation-baseline.json`

Expected SHA-256:

`3f85587e74f9af1ee93f59d53a05ea1d47201e6b8564b8e8a91cb91f378bd40f`

The baseline stores aggregate evidence counts and authority digests rather than duplicating the 60 Active exact ICPNs into a second commercial-identity source of truth.

## Validation model

The L4.1 validator fails closed on:

- OpenOCD catalog byte drift;
- row-count, identifier-kind, target-config or subfamily drift;
- deterministic representative drift;
- post-L0 selection drift;
- target-manifest drift;
- retained official-ST identity/lifecycle drift;
- STM32L462 non-Active lifecycle disposition drift;
- Ordering Information authority or coverage drift;
- frozen Production prestate drift;
- any authority-boundary flag escaping `false`.

## Production boundary

L4.1 performs **zero Production writes**.

```text
Production exact ICPNs: 1272 (delta 0)
Production Base Devices: 392 (delta 0)
Production families: 11 (delta 0)
STM32L4 Production: 0
```

The next transaction, if separately authorized, is **STM32L4 Phase L4.2 — Manufacturer-Authoritative Commercial Discovery**. L4.2 must determine the complete current commercial exact-ICPN surface; the 60 representative Active exact ICPNs in L4.1 are not a complete-family inventory.
