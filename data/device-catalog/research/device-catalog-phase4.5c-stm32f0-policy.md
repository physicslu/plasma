# STM32F0 Phase 4.5C Metadata Policy

Status: bounded metadata policy implemented; exact ICPN admission and Production publication deferred.

## Scope

Phase 4.5C consumes the retained Phase 4.5B official-ST commercial identity transaction and derives deterministic metadata for exactly 42 Active exact ICPNs across 13 bounded STM32F0 Base Devices:

- STM32F030C6
- STM32F031C4
- STM32F038C6
- STM32F042C4
- STM32F048C6
- STM32F051C4
- STM32F058C8
- STM32F070C6
- STM32F071C8
- STM32F072C8
- STM32F078CB
- STM32F091CB
- STM32F098CC

This is not a claim of full STM32F0 commercial coverage.

## Authority boundaries

Phase 4.5C keeps three evidence domains independent:

1. **Commercial identity and lifecycle** — retained Phase 4.5B official ST browser evidence under `stm32f0_dual_surface_v1`. Quality & Reliability supplies exact Part Number identity; Sample & Buy supplies Marketing Status. The retained batch contains 42 Active exact ICPNs and zero lifecycle exclusions.
2. **Package, physical pin/ball count, flash size, temperature and packing semantics** — official ST datasheet Ordering Information tables.
3. **Programming/capability routing** — OpenOCD and later programmer capability policy. This is explicitly **not** a metadata authority and is deferred to Phase 4.5D.

Therefore an OpenOCD mapping that is absent, ambiguous or later changes cannot alter an already manufacturer-backed package, flash, temperature or packing meaning. Conversely, valid metadata does not prove that Plasma can program the device.

## Metadata contract

For this bounded 42-ICPN batch:

| Ordering code | Canonical meaning |
| --- | --- |
| Flash `4` | 16 KiB |
| Flash `6` | 32 KiB |
| Flash `8` | 64 KiB |
| Flash `B` | 128 KiB |
| Flash `C` | 256 KiB |
| Package `T` | LQFP |
| Package `U` | UFQFPN |
| Package `Y` | WLCSP |
| Pin/package `C/T` | 48 physical pins |
| Pin/package `C/U` | 48 physical pins |
| Pin/package `C/Y` | 49 physical balls |
| Temperature `6` | -40 to 85 C |
| Temperature `7` | -40 to 105 C |
| Option suffix empty | tray / standard packing |
| Option suffix `TR` | tape and reel |

`pin_count` means the actual physical package pin/ball count, not merely the ordering-code class. The important bounded exception is `STM32F078CBY6TR`: its `C/Y` combination is a 49-ball WLCSP, while `C/T` and `C/U` are 48-pin packages. A flat rule `C = 48` is therefore invalid.

Official ordering-information references bound by the policy baseline:

- `https://www.st.com/resource/en/datasheet/stm32f030c6.pdf`
- `https://www.st.com/resource/en/datasheet/stm32f051c4.pdf`
- `https://www.st.com/resource/en/datasheet/stm32f072c8.pdf`
- `https://www.st.com/resource/en/datasheet/stm32f078cb.pdf`
- `https://www.st.com/resource/en/datasheet/stm32f091cb.pdf`
- `https://www.st.com/resource/en/datasheet/stm32f098cc.pdf`

## Deterministic result

The checked-in baseline `stm32f0-phase4.5c-policy-baseline.json` freezes all 42 metadata rows and the following distribution:

| Dimension | Result |
| --- | --- |
| Flash | 16 KiB ×7; 32 KiB ×9; 64 KiB ×12; 128 KiB ×10; 256 KiB ×4 |
| Package | LQFP ×24; UFQFPN ×17; WLCSP ×1 |
| Temperature | -40..85 C ×34; -40..105 C ×8 |
| Packing | standard/tray ×26; tape-and-reel ×16 |

Expected policy accounting:

- candidates: 42
- metadata ready: 42
- manual review: 0
- reject: 0
- Production snapshot: 502 exact ICPNs / 175 Base Devices
- STM32F0 Production rows: 0
- OpenOCD metadata gate: false
- capability mapping: deferred to Phase 4.5D

## Governance

Phase 4.5C explicitly leaves the following false/deferred:

- canonical/Production write applied: false
- exact ICPN admission: deferred
- OpenOCD routing gate: not applied in metadata policy
- programming algorithm equivalence: not claimed
- physical target/socket/electrical qualification: not claimed
- runtime programming support: not claimed
- full STM32F0 surface coverage: false

Phase 4.5D may consume the clean identity + metadata result and separately evaluate capability/OpenOCD admission requirements. Phase 4.5C itself performs no `data/device-catalog/production/**` write.
