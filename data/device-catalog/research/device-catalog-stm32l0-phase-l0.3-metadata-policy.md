# STM32L0 Phase L0.3 — Manufacturer-Authoritative Metadata Policy

## Purpose

L0.3 converts the retained L0.2 commercial identity boundary into deterministic commercial metadata using official ST datasheet Ordering Information only.

L0.3 is read-only policy qualification. It does **not** publish STM32L0 to Production and does not qualify programming algorithms, Flash/security behavior, PPU/Socket/HIL, or runtime support.

## Frozen input

L0.2 retained boundary:

```text
Base Devices:                 99
Active exact ICPNs:          360
excluded non-Active PNs:      10
manual identity review:        0
```

Active exact ICPN set SHA-256:

`8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b`

Retained L0.2 live-summary SHA-256:

`c664e6458d00f169b2653021284acb56664b607c245e97f51bf13f4a232d51de`

## Metadata authority

Metadata authority is official ST **Ordering Information**. OpenOCD routing and CMSIS aliases are explicitly non-authoritative for package, pin count, Flash size, temperature grade, or ordering suffix semantics.

The frozen authority contains:

- 16 STM32L0 subfamily/series records;
- 19 official ST datasheet bindings;
- explicit package, pin, Flash, temperature and suffix grammar;
- exact Base Device partitioning where a series requires multiple datasheets.

### STM32L010

STM32L010 cannot safely inherit the more general L0 D/BOR ordering grammar. Four official Ordering Information documents partition the six retained Base Devices:

| Official document | Retained Base Devices |
|---|---|
| DS12324 Rev 3 (`stm32l010c6.pdf`) | STM32L010C6 |
| DS12323 Rev 3 (`stm32l010f4.pdf`) | STM32L010F4, STM32L010K4 |
| DS12325 Rev 3 (`stm32l010k8.pdf`) | STM32L010K8, STM32L010R8 |
| DS12319 Rev 3 (`stm32l010rb.pdf`) | STM32L010RB |

For these L010 authorities, the retained suffix grammar is blank / `TR` only. A general D/BOR option is not inferred.

### STM32L031 / STM32L041

The official `S` one-power-pair option is preserved instead of normalized away. `S` and `STR` remain distinct commercial ordering semantics where observed in the retained exact Part Number set.

## Deterministic result

Final L0.3 planner result:

```text
Base Devices:                 99
candidate exact ICPNs:       360
metadata-ready:              360
manual review:                 0
reject:                        0
```

Metadata-ready exact-set SHA-256:

`8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b`

Metadata rows SHA-256:

`6aefd256256febb6d5f48ec58e44b5fec64489593df333c68723581eb7786a95`

The metadata-ready exact set equals the retained L0.2 Active exact set; L0.3 adds metadata qualification but does not expand commercial identity scope.

## Metadata distribution

```text
Flash:       8K 11, 16K 44, 32K 75, 64K 86, 128K 64, 192K 80
Package:     LQFP 155, TFBGA 25, TSSOP 24, UFBGA 14, UFQFPN 117, WLCSP 25
Temperature: -40..85 C 264, -40..105 C 56, -40..125 C 40
Options:     blank 199, TR 132, D 14, DTR 10, S 2, STR 3
```

## Frozen baseline and validation

Baseline:

`data/device-catalog/research/stm32l0-phase-l0.3-policy-baseline.json`

Permanent replay validator:

`data/device-catalog/research/validate_stm32l0_phase_l0_3_policy.py`

The validator hard-locks:

- retained L0.2 evidence identity and summary digest;
- the 360 exact ICPN set;
- 16 series / 19 official datasheet authority bindings;
- Ordering Information authority byte identity;
- 360 deterministic metadata rows and metadata distribution;
- zero manual-review / zero reject state;
- immutable Production prestate;
- all fail-closed authority boundaries.

Dedicated validation run `34693595288` passed after the frozen baseline replay was added.

## Production boundary

L0.3 performs zero Production writes.

```text
Production exact ICPNs: 912 (delta 0)
Production Base Devices: 293 (delta 0)
Production STM32 families: 10 (delta 0)
STM32L0 Production: 0
```

Canonical admission is explicitly deferred to **L0.4**. Metadata readiness is not a claim of physical programming support.
