# STM32F2 Metadata Authority Replay v3.9

Research-only continuation after merged v3.8 exact-gap lock.

## Scope

Replay all **72 missing current-Active STM32F2 exact MPNs** against official ST Ordering Information authority.

This is Device Catalog **Layer-1 metadata only**. Backend/OpenOCD applicability is deliberately not evaluated.

## Authority

Official ST ordering tables currently define:

- STM32F205 / STM32F207: DS6329 Rev 18
- STM32F215 / STM32F217: DS6697 Rev 13

The locked gap exercises only explicitly bound package/pin combinations:

- LQFP64, LQFP100, LQFP144, LQFP176
- UFBGA176
- WLCSP66

Flash codes cover 128, 256, 512, 768 and 1024 KiB. Temperature codes `6` and `7` map to -40..85 C and -40..105 C. Packing suffix is empty or `TR`.

## Replay result

- input gap: **72**
- metadata decoded: **72/72**
- blocked: **0**
- metadata exceptions: **0**
- direct Ordering Information decode: **72/72**

No cross-series or unsupported package inference is needed.

## Boundary

This establishes Layer-1 metadata readiness only. It does not claim backend mapping, Programming Profile support, Engineering Verified status, field evidence, PS/HIL qualification, or Production authorization.

## Next gate

Prepare a reviewable **72-row STM32F2 Layer-1 admission proposal**. Production publication remains a separate explicit owner-approval transaction.
