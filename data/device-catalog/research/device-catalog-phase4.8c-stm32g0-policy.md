# STM32G0 Device Catalog Phase 4.8C — Metadata Policy

Status: **metadata-policy closure candidate**

Phase 4.8C consumes only the 49 Active exact ICPNs retained by Phase 4.8B. It does not acquire new manufacturer identity evidence, does not admit rows into the canonical Production dataset, and does not claim programming/runtime support.

## Authority boundary

Commercial identity and lifecycle remain owned by the immutable Phase 4.8B official-ST dual-surface evidence. Metadata semantics are decoded only from explicit ST ordering-information contracts.

OpenOCD is not a metadata authority. CMSIS aliases are not commercial identities and are not metadata authorities. Their routing/capability role is deferred to Phase 4.8D.

Official ordering-information authorities bound by this phase:

- STM32G030: `https://www.st.com/resource/en/datasheet/stm32g030c6.pdf`
- STM32G031: `https://www.st.com/resource/en/datasheet/stm32g031c4.pdf`
- STM32G041: `https://www.st.com/resource/en/datasheet/stm32g041c6.pdf`
- STM32G050: `https://www.st.com/resource/en/datasheet/stm32g050c6.pdf`
- STM32G051: `https://www.st.com/resource/en/datasheet/stm32g051c6.pdf`
- STM32G061: `https://www.st.com/resource/en/datasheet/stm32g061c6.pdf`
- STM32G070: `https://www.st.com/resource/en/datasheet/stm32g070cb.pdf`
- STM32G071: `https://www.st.com/resource/en/datasheet/stm32g071c8.pdf`
- STM32G081: `https://www.st.com/resource/en/datasheet/stm32g081cb.pdf`
- STM32G0B0: `https://www.st.com/resource/en/datasheet/stm32g0b0ce.pdf`
- STM32G0B1: `https://www.st.com/resource/en/datasheet/stm32g0b1kb.pdf`
- STM32G0C1: `https://www.st.com/resource/en/datasheet/stm32g0c1cc.pdf`

## Bounded decode contract

The retained 49 Active exact ICPNs require only the following ordering-code semantics:

| Field | Code | Meaning |
|---|---|---|
| Pin count | C | 48 pins |
| Flash | 4 | 16 KiB |
| Flash | 6 | 32 KiB |
| Flash | 8 | 64 KiB |
| Flash | B | 128 KiB |
| Flash | C | 256 KiB |
| Flash | E | 512 KiB |
| Package | T | LQFP |
| Package | U | UFQFPN |
| Temperature | 6 | -40 to 85 C |
| Temperature | 7 | -40 to 105 C |
| Temperature | 3 | -40 to 125 C |
| Option | blank | standard product version / non-TR exact identity |
| Option | TR | tape-and-reel packing |
| Option | N | ST N product version; preserve exact identity |
| Option | NTR | N product version plus tape-and-reel; grammar-supported but absent from retained 49 |

The policy intentionally does not generalize beyond this bounded ordering surface.

## N-product-version decision

This is the critical STM32G0-specific policy difference.

ST ordering information for STM32G0B1/STM32G0C1 explicitly defines an `N` product version in the option field. Therefore `N` is not disposable packaging noise and must not be normalized away.

Phase 4.8B retained these Active identities:

- `STM32G0B1CBT6N`
- `STM32G0B1CBU6N`

They remain distinct exact ICPNs in Phase 4.8C. Their metadata rows retain `option_suffix = N` and a verification status that explicitly records preservation of the N product version.

This also explains the Phase 4.8B OpenOCD gap: those two manufacturer-valid N identities are not matched by the current ordering-pattern surface. The correct response is to preserve identity and defer capability routing, not delete the identities.

## Policy result

Deterministic replay result:

- candidate count: **49**
- metadata ready: **49**
- manual review: **0**
- rejected: **0**
- Production write: **false**
- OpenOCD metadata gate: **false**
- CMSIS metadata gate: **false**
- capability mapping: deferred to **Phase 4.8D**

Frozen metadata distribution:

- package: LQFP 26, UFQFPN 23
- pin count: 48 pins 49
- temperature: -40..85 C 29, -40..105 C 8, -40..125 C 12
- options: blank 27, TR 20, N 2
- Flash: 16 KiB 2, 32 KiB 11, 64 KiB 11, 128 KiB 21, 256 KiB 2, 512 KiB 2

## Frozen inputs

Historical Production prestate remains:

- exact ICPNs: **563**
- Base Devices: **197**
- STM32G0 Production rows: **0**
- family counts: F0 42, F1 75, F2 33, F3 10, F4 384, F7 19

Byte anchors:

- Phase 4.8C policy baseline SHA-256: `953df55b097ad58c93738e2aeecc7c762cb464f882493bf622fefbb61fc3a787`
- Phase 4.8C Production prestate SHA-256: `4b05b3e3e7cb8e9b8cc426f9358d758f04d5bc4944b23e44ee0cad1d3bea1cd3`
- retained Phase 4.8B discovery baseline SHA-256: `ef059c3226b506aa0ff739abf8c6bf3e0f525ceaefb571693458dad6b706f10a`
- retained Phase 4.8B evidence manifest SHA-256: `ff90c6ab4b3adb8bf9c87d5b0321ec3b29eab32f9854b38e566c09d7ffb39469`

One-off generation run `34373699868` and replay run `34373846737` both completed successfully.

## Explicit non-claims

Phase 4.8C does **not** authorize canonical admission, Production publication, programming-algorithm equivalence, HIL qualification, or runtime support. Phase 4.8D must independently decide capability/routing admission, including how to treat manufacturer-valid N-product-version identities that are currently absent from the OpenOCD ordering-pattern surface.
