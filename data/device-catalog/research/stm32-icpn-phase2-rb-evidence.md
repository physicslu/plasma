# STM32 ICPN Phase 2.3 — STM32F103RB evidence note

**Retrieval date:** 2026-08-29

## Direct ST commercial evidence

The official ST STM32F103RB product page lists these nine exact commercial order codes:

- `STM32F103RBH6`
- `STM32F103RBH6R`
- `STM32F103RBH6RTR`
- `STM32F103RBH6TR`
- `STM32F103RBH7`
- `STM32F103RBT6`
- `STM32F103RBT6TR`
- `STM32F103RBT7`
- `STM32F103RBT7TR`

Sources:

- <https://www.st.com/en/microcontrollers-microprocessors/stm32f103rb.html>
- <https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-174-cortex-174-mcus/stm32-mainstream-mcus/stm32f1-series/stm32f103/stm32f103rb.html>

The eStore identifies the admitted `H` parts as TFBGA64 and `T` parts as LQFP64. Exact strings are admitted
only because they appear verbatim in official ST commercial evidence. No missing combination is generated.

## Ordering and mapping evidence

DS5319 Rev 20 defines `R` = 64 pins, `B` = 128 KiB Flash, `H` = BGA, `T` = LQFP, temperature `6` = -40 to
85 °C, temperature `7` = -40 to 105 °C, and `TR` = tape-and-reel. The exact `H6R` and `H6RTR` strings are
retained as ST-listed options rather than inferred from the grammar.

- <https://www.st.com/resource/en/datasheet/stm32f103rb.pdf>

All nine exact ICPNs reduce deterministically to `STM32F103RB`. Plasma's canonical CSV contains exactly one
`cmsis_device_name = STM32F103RB` row mapped to `tcl/target/stm32f1x.cfg`. That CFG remains unverified
programming-capability evidence, not commercial identity.

An RB-only 19-row dataset reproduction passed the fail-closed validator before final combined validation.
