# Phase 4.3D STM32F2 exact-ICPN admission closure

Phase 4.3D admits nine exact STMicroelectronics ordering codes for four bounded
STM32F2 base devices. The admission is based on retained official ST product-page
evidence, explicit lifecycle validation, and one deterministic OpenOCD ordering-pattern
mapping per base device.

## Admitted exact ICPNs

- `STM32F205RBT6`
- `STM32F205RBT6TR`
- `STM32F205RBT7`
- `STM32F207ICH6`
- `STM32F207ICT6`
- `STM32F215RET6`
- `STM32F215RET6TR`
- `STM32F217IEH6`
- `STM32F217IET6`

All nine decisions are `admit`; conflicts, manual reviews, rejects, and lifecycle
exclusions are zero. The retained evidence is
`stm32f2-phase4.3b-official-st-discovery-live-2026-09-06`.

## Controlled publish binding

- Proposal run: `34070625312`
- Proposal artifact: `10000326131`
- Proposal artifact ZIP SHA-256: `871ca9719279278d3cad7563164324626951288605e165f664e7f63adc028a12`
- Admission plan SHA-256: `b657e31ea214348e3153acc7a2514b11b48b88de4ca84f31237cf0574a36a8e8`
- Canonical STM32F2 CSV SHA-256: `935477152326adfa531b21cd1b87374e10b78c6deed19f11353a56f92f11ec26`

The branch-level Production manifest changes from 459 to 468 exact ICPNs and
from two to three Families. STM32F2 contributes nine exact ICPNs across four base
devices.

## Explicit limits

This transaction proves exact catalog identity and deterministic OpenOCD target
configuration selection only. It does not claim programming-algorithm equivalence,
native PPU runtime support, socket or hardware validation, or complete STM32F2
commercial-surface coverage. Those states remain fail-closed and `no_evidence`.
