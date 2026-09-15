# STM32U5 manufacturer identity discovery

Status: **research-only; manufacturer base-device identity snapshot frozen**

This transaction freezes the STM32U5 commercial **Base Device** identities currently exposed by STMicroelectronics' STM32U5 Product Selector. It intentionally does not equate Base Device names with exact orderable ICPNs.

## Bounded result

- 74 manufacturer-observed Base Devices
- 12/12 upstream STM32U5 subfamilies represented
- Base-device set SHA-256: `ab83ea88d30d173e3809b3c1245691a0fb6be4a78f6fa35bd47f6caa8533bcdf`
- Source: `https://www.st.com/en/microcontrollers-microprocessors/stm32u5-series/products.html`

Subfamily counts:

- STM32U535: 11
- STM32U545: 5
- STM32U575: 14
- STM32U585: 7
- STM32U595: 10
- STM32U599: 7
- STM32U5A5: 6
- STM32U5A9: 4
- STM32U5F7: 1
- STM32U5F9: 4
- STM32U5G7: 1
- STM32U5G9: 4

## Exact-ICPN boundary

Exact orderable part numbers are **not** inferred from the Base Device names. The next transaction must enumerate ST `Quality & Reliability` exact `Part Number` rows for every retained Base Device and must reject synthesized order codes.

This split is deliberate: it prevents a Base Device such as `STM32U535CE` from being falsely counted as an exact ICPN such as `STM32U535CET6`.

## Governance boundary

Catalog admission remains independent from PPU/Socket HIL and physical programming success. This transaction does not authorize runtime programming, security-state mutation, debug attach, or physical-validation claims.

Zero Production writes. **Exact Production ICPN count remains 2,017.**

Next gate: `stm32u5-exact-orderable-identity-enumeration`.
