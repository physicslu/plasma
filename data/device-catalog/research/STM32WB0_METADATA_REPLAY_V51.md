# STM32WB0 Metadata Authority Replay v5.1

Research-only continuation of the locked **24 current-Active exact STM32WB0 MPNs**.

## Official metadata authority

The locked set is covered by official ST Ordering Information:

- STM32WB05xN — DS14620 — network coprocessor; `N` is a role code, **not Flash density**
- STM32WB05xZ — DS14591 — `Z = 192 Kbytes`
- STM32WB06xC / STM32WB07xC — DS14676 — `C = 256 Kbytes`
- STM32WB09xE — DS14210 — `E = 512 Kbytes`

All retained exact identities use official pin/package, temperature and tape-and-reel ordering codes.

## Package-dependent physical count

For STM32WB06/07 `CCF`, the Ordering Information pin-count code is `C = 48`, while the actual WLCSP package is **WLCSP49**. Layer-1 records the physical package count as 49. The VFQFPN alternative remains 48.

## Replay result

- current-Active exact identities: **24**
- metadata decoded: **24/24**
- blocked: **0**
- bounded metadata exceptions: **0**
- network-coprocessor identities: **4**
- ordinary Flash MCU identities: **20**

## Capability boundary

This replay establishes identity and metadata only. It does not bind:

- OpenOCD or any other programming backend
- Programming Profile
- Engineering Verified
- field evidence
- PS/HIL qualification
- Production publication

## Next gate

Prepare a reviewable **24-row STM32WB0 Layer-1 admission proposal** with all backend routes unbound and preserve the WB05xN network-coprocessor semantic boundary.
