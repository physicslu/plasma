# STM32N6 Metadata Authority Replay v4.8

Research-only continuation of the locked **32 current-Active exact STM32N6 MPNs**.

## Ordering authority

Official ST **DS14791 Rev 11**, Section 7 Ordering information, directly decodes the complete locked set:

- die code: 4 = no crypto, 5 = crypto
- line code: 5 = no Neural-ART, 7 = Neural-ART
- pin/ball count: Z=142, A=169, I=178, B=198, L=223, X=264
- flash code: 0 = 0-1 Kbytes
- package code: H = VFBGA
- temperature code: 3 = industrial -40..125 C
- dedicated pinout: Q or QG
- packing exercised by the locked set: standard/unspecified or TR

Authority:
https://www.st.com/resource/en/datasheet/stm32n657a0.pdf

## Result

- current-Active exact identities: **32**
- metadata decoded: **32/32**
- blocked: **0**
- bounded metadata exceptions: **0**
- series:
  - STM32N645: 7
  - STM32N647: 7
  - STM32N655: 7
  - STM32N657: 11

## Critical capability boundary

STM32N6 is intentionally treated as a **Catalog Layer-1 identity/metadata** problem here.

This replay does **not** evaluate or claim:

- a usable internal-Flash programming path
- external-memory programming support
- OpenOCD backend applicability
- Programming Profile support
- Engineering Verified
- field evidence
- PS/HIL qualification
- Production write authorization

The known STM32N6 external-memory / special programming-profile concern remains separate and must not block identity metadata admission.

## Next gate

Prepare a reviewable **32-row STM32N6 Layer-1 admission proposal**, with every backend route left unbound and Programming Profile state unresolved.
