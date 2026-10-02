# STM32F3 Metadata Authority Replay v3.1

Research-only continuation after the merged v3.0 exact-gap lock.

## Scope

Replay all **182 missing current-Active STM32F3 exact MPNs** against official ST Ordering Information authority.

This is Device Catalog **Layer-1 metadata only**. Backend/OpenOCD applicability is deliberately not evaluated and is not an admission gate for this task.

## Authority partition

| Series / density band | Official authority |
| --- | --- |
| STM32F301 x6/x8 | DS9895 Rev 8 |
| STM32F302 x6/x8 | DS9896 Rev 8 |
| STM32F302 xB/xC | DS9911 Rev 9 |
| STM32F302 xD/xE | DS10592 / DocID026900 Rev 4 |
| STM32F303 x6/x8 | DS9866 Rev 8 |
| STM32F303 xB/xC | DS9118 Rev 14 |
| STM32F303 xD/xE | DS10362 / DocID026415 Rev 5 |
| STM32F318 x8 | DS10315 Rev 7 |
| STM32F328 x8 | DS10336 / DocID026351 Rev 3 |
| STM32F334 x4/x6/x8 | DS9994 Rev 9 |
| STM32F358 xC | DocID025540 Rev 4 |
| STM32F373 x8/xB/xC | DS8845 / DocID022691 Rev 7 |
| STM32F378 xC | DS10062 / DocID025608 Rev 4 |
| STM32F398 xE | DocID027227 Rev 2 |

F302 and F303 must be density-band resolved before metadata decoding. Cross-band or cross-series inference is forbidden.

## Ordering-code semantics

The replay resolves only explicitly authorized combinations.

Important package-specific physical pin counts include:

- `C/T` → LQFP48
- `C/Y` → WLCSP49
- `K/T` or `K/U` → 32 pins
- `R/T` → LQFP64
- `R/Y` → WLCSP66, only on the admitted F378 authority surface
- `V/T`, `V/H`, `V/Y` → 100 pins/balls
- `Z/T` → LQFP144

Flash codes:

- `4` → 16 KiB
- `6` → 32 KiB
- `8` → 64 KiB
- `B` → 128 KiB
- `C` → 256 KiB
- `D` → 384 KiB
- `E` → 512 KiB

Temperature codes `6` and `7` mean -40..85 C and -40..105 C respectively. The only current packing suffix is `TR`.

## Replay result

- locked gap exact MPNs: **182**
- metadata decoded: **182/182**
- blocked: **0**
- metadata exceptions: **0**
- direct official Ordering Information decode: **182/182**

The 182 rows split across 14 authority bands. Unknown density codes, cross-band pin/package combinations, unsupported suffixes, or unbound metadata fail closed.

## Boundaries

This gate establishes:

- exact Layer-1 candidate set locked: true
- metadata authority replay complete: true
- Layer-1 admission proposal ready: true

It does **not** establish:

- backend/OpenOCD applicability
- Programming Profile support
- Engineering Verified status
- operational/field evidence
- PS/HIL qualification
- Production write authorization

## Next gate

Prepare a reviewable **182-row STM32F3 Layer-1 admission proposal**. Production publication remains a separate explicit owner-approval transaction.
