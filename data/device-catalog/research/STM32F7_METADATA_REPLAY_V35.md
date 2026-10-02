# STM32F7 Metadata Authority Replay v3.5

Research-only continuation after the merged v3.4 exact-gap lock.

## Scope

Replay all **154 missing current-Active STM32F7 exact MPNs** against official ST Ordering Information authority.

This is Device Catalog **Layer-1 metadata only**. Backend/OpenOCD applicability is deliberately not evaluated and is not an admission gate.

## Authority surface

The replay binds the current gap to official ST Ordering Information by series:

- STM32F722 / STM32F723: DS11853 Rev 9
- STM32F730: DS12536 Rev 2
- STM32F732 / STM32F733: DS11854 Rev 7
- STM32F745 / STM32F746: DS10916 Rev 5
- STM32F756: DS10915 Rev 5
- STM32F765 / STM32F767 / STM32F769: DS11532 Rev 9
- STM32F777 / STM32F779: DS11243 Rev 8

Package/pin semantics are explicit and fail closed, including UFBGA144, WLCSP143, UFBGA176, TFBGA216 and WLCSP180 combinations.

## STM32F750 boundary

Three current-Active x8 identities require exact-product-bounded metadata overrides:

- `STM32F750V8T6`
- `STM32F750V8T7`
- `STM32F750Z8T6`

The generic DS12535 Rev 2 Ordering Information table does not encode the commercial `8` Flash code used by these exact products. The overrides therefore consume the official ST exact-product surfaces only for these exact identities. No generalized STM32F750 x8 interpretation is created.

## Replay result

- locked gap exact MPNs: **154**
- metadata decoded: **154/154**
- blocked: **0**
- direct Ordering Information decode: **151**
- exact-product bounded overrides: **3**

Metadata distribution:

| Dimension | Distribution |
| --- | --- |
| package | LQFP 93; TFBGA 34; UFBGA 20; WLCSP 7 |
| Flash | 64 KiB 8; 256 KiB 8; 512 KiB 44; 1024 KiB 54; 2048 KiB 40 |
| temperature | -40..85 C 118; -40..105 C 36 |
| packing | standard/tray 120; TR 34 |

## Boundaries

This gate establishes:

- exact Layer-1 candidate set locked: true
- metadata authority replay complete: true
- Layer-1 admission proposal ready: true

It does **not** establish:

- backend/OpenOCD applicability for the 154 additions
- Programming Profile support
- Engineering Verified status
- operational/field evidence
- PS/HIL qualification
- Production write authorization

## Next gate

Prepare a reviewable **154-row STM32F7 Layer-1 admission proposal**. Production publication remains a separate explicit owner-approval transaction.
