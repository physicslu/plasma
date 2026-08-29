# STM32 ICPN Phase 2.2 — STM32F103CB evidence note

**Retrieval date:** 2026-08-29

This note records the authoritative evidence used to extend the Phase 2 STM32F1 commercial ICPN dataset from `STM32F103C8` to `STM32F103CB`.

## Direct ST commercial evidence

The official ST eStore page for STM32F103CB lists exactly these six active order codes in the retrieved page:

- `STM32F103CBT6`
- `STM32F103CBT6TR`
- `STM32F103CBT7`
- `STM32F103CBT7TR`
- `STM32F103CBU6`
- `STM32F103CBU6TR`

Source:

- <https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-174-cortex-174-mcus/stm32-mainstream-mcus/stm32f1-series/stm32f103/stm32f103cb.html>

These exact strings are admitted as commercial ICPNs because they occur verbatim in an official ST commercial source. No other `STM32F103CB*` codes are generated from the ordering grammar.

## Ordering-field evidence

ST datasheet DS5319 Rev 20 covers STM32F103x8 / STM32F103xB and defines the fields used here:

- `C` = 48 pins
- `B` = 128 KiB Flash
- `T` = LQFP
- `U` = VFQFPN or UFQFPN; the eStore identifies the two admitted `U6` parts specifically as UFQFPN 48
- `6` = -40 to 85 °C
- `7` = -40 to 105 °C
- `TR` = tape and reel

Source:

- <https://www.st.com/resource/en/datasheet/stm32f103cb.pdf>

The datasheet explicitly says to contact ST for available options. Therefore its ordering scheme is used only to decode exact order codes already proven by ST commercial evidence; it is not used to synthesize additional ICPNs.

## Mapping boundary

All six order codes reduce to base identity `STM32F103CB`. The Plasma dataset records that base identity separately from the exact commercial ICPN and links it to the existing `cmsis_device_name` / OpenOCD capability row only when the validator can find the asserted canonical mapping.

OpenOCD target configuration remains capability evidence, not commercial identity.

## Validation

The repository's fail-closed validator and GitHub Actions device-catalog validation workflow are authoritative for deterministic mapping acceptance:

```bash
python data/device-catalog/research/validate_stm32f1_commercial_icpn.py
```

The PR must not be merge-ready unless that CI check passes.
