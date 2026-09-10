# Device Catalog — STM32U0 Phase U0.1 Foundation

## Status

Research foundation only. H006 deterministically selected `STM32U0` as the next research family. Phase U0.1 freezes the bounded OpenOCD-derived STM32U0 research surface and binds its deterministic representatives to the retained official-ST identity/lifecycle and Ordering Information evidence already acquired during H006.

This phase does **not** authorize canonical admission, Production publication, programming-algorithm equivalence, Flash geometry, option/security semantics, physical/HIL qualification, or runtime programming support.

## Primary workstream

`ICPN`

This transaction answers only:

> What is the deterministic, replayable STM32U0 commercial research surface that later admission work may investigate?

It does not answer whether Plasma can program STM32U0.

## Bounded source surface

Source of record: `data/device-catalog/research/openocd-parts-canonical.csv`.

The guarded STM32U0 source surface is:

| Property | Frozen value |
| --- | ---: |
| Total source rows | 48 |
| `ordering_pattern` rows | 42 |
| `cmsis_device_name` rows | 6 |
| Subfamilies | 3 |
| OpenOCD target config | `tcl/target/stm32u0x.cfg` |

Subfamily totals are:

| Subfamily | Source rows |
| --- | ---: |
| STM32U031 | 16 |
| STM32U073 | 24 |
| STM32U083 | 8 |

`ordering_pattern` and `cmsis_device_name` are deliberately non-equivalent. OpenOCD/CMSIS data bounds and routes research. It is not manufacturer commercial identity authority.

## Deterministic representatives

Exactly one lexicographically first concrete Base Device is selected from the `ordering_pattern` surface of each guarded subfamily:

| Subfamily | Research representative |
| --- | --- |
| STM32U031 | `STM32U031C6` |
| STM32U073 | `STM32U073C8` |
| STM32U083 | `STM32U083CC` |

CMSIS-only aliases cannot participate in this representative selection.

## Retained official-ST identity/lifecycle evidence

Phase U0.1 replays the H006 retained evidence; it does not reacquire historical live evidence.

Retained probe-summary SHA-256:

`d4339d85a7565f4be731de863ee7db0c1301a335bb5b2777e84a1089aae2769d`

The three deterministic representatives are all retained as `verified_active`. Eight active exact commercial ICPNs were observed in that representative evidence:

- `STM32U031C6T6`
- `STM32U031C6U6`
- `STM32U073C8T6`
- `STM32U073C8U6`
- `STM32U083CCT6`
- `STM32U083CCT6TR`
- `STM32U083CCU6`
- `STM32U083CCU6TR`

These eight ICPNs are retained evidence attached to the three representatives. They are **not** a Phase U0.1 Production admission set and are not evidence that the full 48-row research surface resolves to eight exact ICPNs.

## Official Ordering Information authority

Ordering Information review SHA-256:

`3fe019d420cbe43c732b9d403acaa2f1b0bf0dc583b38073eb25528217f5efe9`

| Representative | Official ST datasheet | Revision | Ordering page |
| --- | --- | ---: | ---: |
| `STM32U031C6` | DS14581 | 2 | 124 |
| `STM32U073C8` | DS14548 | 2 | 135 |
| `STM32U083CC` | DS14463 | 2 | 135 |

All three retained Ordering Information reviews have complete required schema coverage. Raw PDF transport diagnostics and screenshot-cache availability are not authority or selection gates.

## Selection binding

H006 selection artifact SHA-256:

`2c81a6c3495a75a6f4115252293af6e99b727f3d12d67f31853922279a96d017`

Phase U0.1 requires that artifact to continue to state:

`selected_next_research_family = STM32U0`

with scope `next_family_research_only`, and with all canonical-admission, programming, Flash/security, HIL, runtime, and Production-write authority boundaries false.

## Fail-closed controls

The permanent replay rejects:

- source-row count or subfamily-surface drift;
- the 42/6 identifier-kind split changing;
- target-config, OpenOCD distribution, mapping-status, or validation-status drift;
- malformed ordering patterns;
- CMSIS aliases promoted into the commercial-representative surface;
- deterministic representative drift;
- H006 selection artifact or retained evidence digest drift;
- retained representative identity/lifecycle or exact-ICPN drift;
- official Ordering Information authority drift;
- any admission/programming/Flash/security/HIL/runtime authority flag becoming true.

Frozen Phase U0.1 baseline SHA-256:

`55fd41eaa32c50571d4081321ce293ff87294c98db230386ddff418ee0579a20`

## Production boundary

Phase U0.1 does not modify `data/device-catalog/production/`.

At transaction start the Production Device Catalog remains the H006 boundary of 635 exact ICPNs / 217 Base Devices / 8 STM32 families, with STM32U0 absent. Current/global Device Catalog CI remains responsible for validating the actual Production payload; this historical research foundation intentionally does not permanently freeze the global Production count, because future separately approved family admissions must remain possible.

## Next transaction

A later STM32U0 commercial discovery/admission phase may expand from these three representatives using manufacturer-authoritative identity and Ordering Information evidence. Such work must be a separate transaction and must not infer programming policy, Flash controller equivalence, option/security semantics, HIL, or runtime support from this foundation.
