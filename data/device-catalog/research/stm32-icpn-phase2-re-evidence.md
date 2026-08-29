# STM32 ICPN Phase 2.3 — STM32F103RE evidence note

**Retrieval date:** 2026-08-29

## Direct ST commercial evidence

The official ST STM32F103RE product page was used to admit exactly these four commercial order codes after
the RB evidence and deterministic mapping had been established:

- `STM32F103RET6`
- `STM32F103RET6TR`
- `STM32F103RET7`
- `STM32F103REY6TR`

Source:

- <https://www.st.com/en/microcontrollers-microprocessors/stm32f103re.html>

No `RET7TR`, `REY6`, or other syntactically plausible code is created because the retrieved official product
page does not list it.

## Ordering and mapping evidence

DS5792 Rev 13 defines `R` = 64 pins, `E` = 512 KiB Flash, `T` = LQFP, `Y` = WLCSP64, temperature `6` =
-40 to 85 °C, temperature `7` = -40 to 105 °C, and `TR` = tape-and-reel.

- <https://www.st.com/resource/en/datasheet/stm32f103re.pdf>

All four exact ICPNs reduce deterministically to `STM32F103RE`. Plasma's canonical CSV contains exactly one
`cmsis_device_name = STM32F103RE` row mapped to `tcl/target/stm32f1x.cfg`. OpenOCD remains unverified
capability evidence only; no runtime or hardware validation is claimed.
