# Retained STM32F4 Phase 4.1 R/T policy evidence

Evidence ID: `stm32f4-phase4.1-rt-policy-2026-09-01-e125390`

This policy-only package binds seven official STMicroelectronics STM32F4
datasheet ordering schemes to one catalog semantic mapping:

```text
pin-count code R = 64 pins
package code T = LQFP
R/T = LQFP64
```

The mapping covers 11 currently unadmitted OpenOCD ordering-pattern Base
Devices. It changes policy readiness only. It does not admit an exact ICPN,
does not establish current lifecycle or commercial availability, and does not
claim programming-algorithm equivalence from an OpenOCD routing pattern.

The official PDF bytes are not checked into the repository and no PDF-byte
hash is claimed. `sources.json` retains the source URLs, document revisions,
page locators, affected Base Devices, and normalized observations. The package
manifest provides deterministic SHA-256 integrity for every retained local
file and is validated offline.
