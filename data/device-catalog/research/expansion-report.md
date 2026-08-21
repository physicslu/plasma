# OpenOCD MCU Part-Number Expansion Report

OpenOCD source commit: `56b8d93fbe61a78dc903d770820d6d896b6d8134`

## Current execution result

- MCU/Wireless MCU CFG candidates evaluated: **114**
- CFG files with deterministic authoritative-source mappings: **78**
- Unique device identifiers mapped: **1804**
- CMSIS/vendor device names: **1557**
- Manufacturer ordering part numbers: **117**
- Ordering patterns: **130**
- Pinned PDSC sources parsed: **58**
- Pinned vendor SDK/board/product sources parsed: **8**
- Canonical unique identifiers across baseline and expansion: **7530**
- Canonical unique target CFG files: **131**
- Baseline/expansion target conflicts resolved: **34**
- Helper/external-memory targets deferred: **12**
- Flash-capable targets awaiting a source adapter/rule: **24**

Every mapped row remains `not_verified`. This report proves only a deterministic software mapping and a declared OpenOCD Flash driver, not engineering, Socket, or production validation.

## Mapped identifiers by vendor

| Vendor | Identifiers |
|---|---:|
| Analog Devices | 17 |
| Artery | 103 |
| Bouffalo Lab | 4 |
| Cypress/Fujitsu | 312 |
| Geehy | 124 |
| GigaDevice | 29 |
| Holtek | 30 |
| Microchip | 234 |
| NXP | 247 |
| Nuvoton | 207 |
| Raspberry Pi | 3 |
| STMicroelectronics | 140 |
| Texas Instruments | 354 |

## Canonical identifiers by CPU architecture

| CPU architecture | Identifiers |
|---|---:|
| ARM Cortex-M | 7369 |
| ARM7TDMI | 5 |
| AVR | 3 |
| MIPS32 | 128 |
| RISC-V | 24 |
| Xtensa | 3 |

## Outcome interpretation

- `mapped`: a pinned authoritative source plus one deterministic rule selected the Target CFG.
- `source_adapter_pending`: Flash is declared, but the current automated sources/rules are insufficient.
- `deferred`: the CFG is a helper/alias or resolves only an external/general-purpose Flash bank.
- Canonical deduplication prefers the narrower expansion rule when a baseline family CFG overlaps.
- A dual-architecture device appears once in the canonical CSV and once under each supported architecture.
