# STM32F3 Phase 4.4C Metadata Policy

Status: bounded policy complete; canonical/Production admission deferred.

## Scope

Phase 4.4C consumes the retained Phase 4.4B official-ST discovery transaction
and derives canonical metadata for exactly 10 Active commercial ICPNs across six
bounded Base Devices:

- STM32F301C6
- STM32F302C6
- STM32F303C6
- STM32F318C8
- STM32F334C4
- STM32F373C8

The policy does not claim full STM32F3 commercial coverage.

## Authority boundaries

Three independent evidence domains are kept separate:

1. **Commercial identity and lifecycle** — retained Phase 4.4B official ST browser
   evidence. STM32F3 uses the `stm32f3_dual_surface_v1` profile: Quality &
   Reliability owns exact Part Number identity; Sample & Buy owns Marketing
   Status; both exact-identity sets must match before evidence is accepted.
2. **Canonical package/pin/flash/temperature semantics** — official ST datasheet
   Ordering Information tables. Product marketing descriptions are not used as
   flash-size authority.
3. **Programming transport routing** — guarded OpenOCD ordering-pattern catalog.
   Every candidate must resolve uniquely to `tcl/target/stm32f3x.cfg`.

Unique OpenOCD routing does not prove programming-algorithm equivalence,
hardware/socket qualification, or runtime programming support.

## Metadata contract

For this bounded batch:

| Ordering code | Canonical meaning |
| --- | --- |
| Flash `4` | 16 KiB |
| Flash `6` | 32 KiB |
| Flash `8` | 64 KiB |
| Package `T` | LQFP |
| Package `Y` | WLCSP |
| Pin/package `C/T` | 48 physical pins |
| Pin/package `C/Y` | 49 physical balls |
| Temperature `6` | -40 to 85 C |
| Temperature `7` | -40 to 105 C |
| Option suffix empty | standard packing |
| Option suffix `TR` | tape and reel |

`pin_count` means the actual physical package pin/ball count. This matters because
STM32F3 ordering code `C` represents a 48-or-49-pin class in the small-device
ordering schemes; the package code resolves the physical count.

Official ordering-information references retained by the policy baseline:

- `https://www.st.com/resource/en/datasheet/stm32f301c6.pdf`
- `https://www.st.com/resource/en/datasheet/stm32f302c6.pdf`
- `https://www.st.com/resource/en/datasheet/stm32f303r8.pdf`
- `https://www.st.com/resource/en/datasheet/stm32f318c8.pdf`
- `https://www.st.com/resource/en/datasheet/stm32f334c4.pdf`
- `https://www.st.com/resource/en/datasheet/stm32f373c8.pdf`

## Deterministic result

The offline policy planner replays the retained evidence and current mapping
catalog against a zero-row STM32F3 canonical prestate. Expected result:

- candidate count: 10
- admit decisions: 10
- already present: 0
- manual review: 0
- reject: 0
- conflicts: 0
- canonical rows before: 0
- Production snapshot: 492 exact ICPNs / 169 Base Devices
- STM32F3 Production rows before admission: 0

The immutable policy summary is
`stm32f3-phase4.4c-policy-baseline.json`.

## Governance

Phase 4.4C explicitly leaves the following false/deferred:

- Production write applied: false
- exact ICPN admission: deferred
- programming algorithm equivalence: not claimed
- runtime support: not claimed
- full STM32F3 surface coverage: false

A later Phase 4.4D may consume the clean policy result through the generic
admission mechanics, but Phase 4.4C itself performs no canonical or Production
write.
