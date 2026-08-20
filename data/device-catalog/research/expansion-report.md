# OpenOCD MCU Part-Number Expansion Report

OpenOCD source commit: `56b8d93fbe61a78dc903d770820d6d896b6d8134`

## Current execution result

- MCU/Wireless MCU CFG candidates evaluated: **114**
- CFG files with deterministic PDSC mappings: **36**
- Unique device identifiers mapped: **1023**
- CMSIS device names: **893**
- Ordering patterns: **130**
- Pinned PDSC sources parsed: **27**
- Helper/external-memory targets deferred: **9**
- Flash-capable targets awaiting a source adapter/rule: **69**

Every mapped row remains `not_verified`. This report proves only a deterministic software mapping and a declared OpenOCD Flash driver, not engineering, Socket, or production validation.

## Mapped identifiers by vendor

| Vendor | Identifiers |
|---|---:|
| Microchip | 89 |
| NXP | 247 |
| Nuvoton | 207 |
| STMicroelectronics | 140 |
| Texas Instruments | 340 |

## Outcome interpretation

- `mapped`: a pinned source plus one deterministic rule selected the Target CFG.
- `source_adapter_pending`: Flash is declared, but the current automated sources/rules are insufficient.
- `deferred`: the CFG is a helper/alias or resolves only an external/general-purpose Flash bank.
