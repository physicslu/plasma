# Device Catalog Phase 4.9A — STM32G4 Foundation

## Status

Foundation only. This phase freezes the bounded OpenOCD-derived STM32G4 source surface and deterministic initial research targets. It does **not** assert exact commercial ICPNs, retain manufacturer evidence, authorize canonical/Production writes, define programming policy, or claim runtime support.

## Source boundary

Source of record: `data/device-catalog/research/openocd-parts-canonical.csv`.

The guarded STM32G4 surface contains **183 rows** and maps only to `tcl/target/stm32g4x.cfg`. All rows are `upstream-openocd`, `mapping_candidate`, and `not_verified`.

Identifier surfaces are deliberately separated:

- **177 `ordering_pattern` rows** — eligible only for deterministic Base Device selection and OpenOCD routing observations.
- **6 `cmsis_device_name` rows** — routing aliases only; never manufacturer commercial identity evidence.

The six CMSIS aliases occur only in STM32G431, STM32G473, and STM32G491 (two per subfamily).

## Guarded subfamilies

| Subfamily | Total | Ordering patterns | CMSIS aliases |
|---|---:|---:|---:|
| STM32G411 | 22 | 22 | 0 |
| STM32G414 | 10 | 10 | 0 |
| STM32G431 | 27 | 25 | 2 |
| STM32G441 | 9 | 9 | 0 |
| STM32G471 | 17 | 17 | 0 |
| STM32G473 | 27 | 25 | 2 |
| STM32G474 | 25 | 25 | 0 |
| STM32G483 | 9 | 9 | 0 |
| STM32G484 | 9 | 9 | 0 |
| STM32G491 | 19 | 17 | 2 |
| STM32G4A1 | 9 | 9 | 0 |

## Deterministic initial targets

Exactly one lexicographically first concrete Base Device is selected from the ordering-pattern surface of each subfamily:

- `STM32G411C6`
- `STM32G414CB`
- `STM32G431C6`
- `STM32G441CB`
- `STM32G471CC`
- `STM32G473CB`
- `STM32G474CB`
- `STM32G483CE`
- `STM32G484CE`
- `STM32G491CC`
- `STM32G4A1CE`

These are bounded **research targets**, not supported-device claims.

## Evidence hierarchy

Phase 4.9A keeps three concepts non-equivalent:

1. OpenOCD ordering patterns establish a candidate routing surface.
2. CMSIS names are aliases and cannot establish commercial identity.
3. Exact ICPN identity/lifecycle must come from manufacturer evidence in a later discovery phase.

A unique `stm32g4x.cfg` ordering-pattern match therefore remains a routing observation only. It does not establish current commercial identity or validated programming capability.

## Fail-closed controls

The permanent regression requires an exact 183-row source surface, exact subfamily distribution, exact 177/6 identifier-kind split, one target config, and deterministic one-target-per-subfamily selection. Identifier-kind drift, target-config drift, malformed ordering patterns, and promotion of a CMSIS alias into the commercial-selection surface fail closed.

## Next phase

Phase 4.9B may acquire official ST product-page evidence for the 11 deterministic targets. Manufacturer identity/lifecycle evidence remains authoritative; OpenOCD routing stays orthogonal to commercial identity.
