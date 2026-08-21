# OpenOCD MCU Part-Number Expansion Report

OpenOCD source commit: `56b8d93fbe61a78dc903d770820d6d896b6d8134`

## Current execution result

- MCU/Wireless MCU CFG candidates evaluated: **114**
- CFG files with deterministic authoritative-source mappings: **99**
- Unique device identifiers mapped: **1931**
- CMSIS/vendor device names: **1616**
- Manufacturer ordering part numbers: **167**
- Ordering patterns: **148**
- Pinned PDSC sources parsed: **58**
- Pinned vendor MCU SDK/product sources parsed: **16**
- Pinned OpenOCD MCU Flash-driver part tables parsed: **5**
- Pinned OpenOCD exact-MCU target definitions parsed: **7**
- Canonical unique identifiers across baseline and expansion: **7657**
- Canonical MCU vendors: **19**
- Manufacturer MCU families preserved: **310**
- Simplified Plasma series preserved: **141**
- Manufacturer MCU subfamilies when available: **862**
- Selectable identifiers without an optional subfamily: **908**
- Canonical unique target CFG files: **152**
- Baseline/expansion target conflicts resolved: **34**
- Helper, external-memory, Flashless, or invalid-TAP targets deferred: **15**
- Flash-capable targets awaiting a source adapter/rule: **0**

Every mapped row remains `not_verified`. This report proves only a deterministic software mapping and a declared OpenOCD Flash driver, not engineering, Socket, or production validation.

## Mapped identifiers by vendor

| Vendor | Identifiers |
|---|---:|
| Analog Devices | 50 |
| Artery | 107 |
| Bouffalo Lab | 4 |
| Cypress/Fujitsu | 312 |
| Geehy | 124 |
| GigaDevice | 29 |
| Holtek | 30 |
| Infineon | 18 |
| Microchip | 234 |
| NIIET | 1 |
| NXP | 267 |
| Nuvoton | 210 |
| Raspberry Pi | 3 |
| STMicroelectronics | 145 |
| Silicon Labs | 42 |
| Texas Instruments | 354 |
| XMOS | 1 |

## Canonical identifiers by CPU architecture

| CPU architecture | Target CFG files | Identifiers |
|---|---:|---:|
| ARM Cortex-M | 122 | 7442 |
| ARM7TDMI | 13 | 47 |
| ARM966E-S | 2 | 12 |
| AVR | 3 | 3 |
| MIPS32 | 1 | 128 |
| RISC-V | 9 | 24 |
| Xtensa | 3 | 3 |

## Outcome interpretation

- `mapped`: a pinned authoritative source plus one deterministic rule selected the Target CFG.
- `source_adapter_pending`: Flash is declared, but the current automated sources/rules are insufficient.
- `deferred`: the CFG is a helper/alias, is Flashless, has an unresolved TAP ID, or resolves only an external/general-purpose Flash bank.
- Canonical deduplication prefers the narrower expansion rule when a baseline family CFG overlaps.
- Part-number-first live search uses manufacturer family, optional subfamily, and Plasma series only as secondary context.
- A dual-architecture device appears once in the canonical CSV and once under each supported architecture.
