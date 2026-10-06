# STM32WL3 Metadata Authority Replay v4.5

Research-only continuation of the locked **47 current-Active exact STM32WL3 MPNs**.

## Ordering authority

Official ST datasheet ordering tables are bound as follows:

- STM32WL30 — DS14855 Rev 1
- STM32WL31 — DS14836 Rev 1
- STM32WL33 — DS14221 Rev 6
- STM32WL3R — DS15018 Rev 2

The current exact set exercises:

- packages: VFQFPN only
- pins: 32 and 48
- flash: 64, 128 and 256 KiB
- temperature codes: 6 (-40..85 C) and 7 (-40..105 C)
- frequency options: none, A and X
- packing: standard/tray or TR

## Result

- current-Active exact identities: **47**
- metadata decoded: **47/47**
- blocked: **0**
- direct Ordering Information decode: **45**
- exact-MPN bounded exceptions: **2**
  - `STM32WL31C8V6`
  - `STM32WL31CBV6`

DS14836 Rev 1's ordering table lists `K=32` but omits the `C=48` pin-code row even though the same datasheet contains VFQFPN48 package information and ST's exact product/Q&R pages list the two locked `C` products as Active VFQFPN48. The exception is therefore exact-MPN bounded; no generalized WL31 `C` rule is introduced.

## Boundary

This establishes Device Catalog Layer-1 metadata readiness only.

It does **not** evaluate or claim:

- backend/OpenOCD route applicability
- Programming Profile support
- Engineering Verified
- field evidence
- PS/HIL qualification
- Production write authorization

## Next gate

Prepare a reviewable **47-row STM32WL3 Layer-1 admission proposal**, with every backend route left unbound.
