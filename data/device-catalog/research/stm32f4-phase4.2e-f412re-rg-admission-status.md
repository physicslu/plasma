# STM32F4 Phase 4.2E — F412RE/RG admission

Locked base: `main@58dc5201595dd8703a69d635453cae608d2a7d30`

Pre-state:
- STM32F1 exact ICPNs: 75
- STM32F4 exact ICPNs: 199
- ST total exact ICPNs: 274
- STM32F4 Base Devices: 68
- OpenOCD ordering-pattern Base Devices: 149
- gap Base Devices: 81
- policy-ready: 2 (`STM32F412RE`, `STM32F412RG`)
- policy-blocked: 79

Bounded scope:
- lifecycle control: `STM32F479ZG`
- admission targets: `STM32F412RE`, `STM32F412RG`

Safety boundary:
- discovery is read-only
- no Production write before retained evidence and immutable admission proposal
- ordering-pattern routing is not programming-algorithm equivalence
- no PPU/socket validation claim
