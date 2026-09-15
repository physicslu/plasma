# STM32U5 security-scope foundation

Status: **research-only; identity discovery allowed; target execution remains blocked**

This transaction advances the remaining ranked STM32 TrustZone cohort candidate, STM32U5. The frozen Gate 1 inventory contains 12 STM32U5 subfamilies, 162 upstream mapping rows, 63 ordering-pattern rows, 99 CMSIS-device-name rows, and one OpenOCD target config: `tcl/target/stm32u5x.cfg`.

## Catalog-admission boundary

The merged ICPN governance invariant is authoritative: catalog admission is independent from PPU/Socket HIL and from physical programming success. This security foundation therefore **does not** contain a `production_admission_allowed=false` security gate. Manufacturer identity and metadata may later be admitted to the Production catalog when catalog-level requirements are satisfied, while physical validation and execution eligibility remain separate states.

## Manufacturer security evidence

Official ST evidence is bounded to the STM32U5 product/documentation pages, RM0456, and ST's RDP security guidance. The family uses Arm Cortex-M33 with TrustZone and lifecycle RDP levels 0, 0.5, 1, and 2. RDP 0.5 applies only with TrustZone enabled. RDP2 closes normal debug access but is not modeled as unconditionally terminal because an OEM2 unlocking mechanism can condition RDP2-to-RDP1 regression. OEM lock/key state therefore must never be inferred.

Security-state mutation, option-byte writes, OEM-key provisioning/unlock, RDP regression, mass erase, runtime programming, debug attach, and HIL claims all remain fail-closed.

## Bounded candidate scope

`STM32U535`, `STM32U545`, `STM32U575`, `STM32U585`, `STM32U595`, `STM32U599`, `STM32U5A5`, `STM32U5A9`, `STM32U5F7`, `STM32U5F9`, `STM32U5G7`, and `STM32U5G9` are upstream research candidates only. Their presence in upstream OpenOCD/CMSIS evidence is not manufacturer commercial-identity evidence.

The next bounded transaction is **STM32U5 manufacturer identity discovery**.

Production Exact ICPN count at this gate: **2,017**.
