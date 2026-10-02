# STM32H5 Metadata Authority Replay v2.7

Research-only continuation after merged layered-gap PR #702.

## Purpose

Replay all **190 locked Active STM32H5 exact MPNs** against their own official ST Ordering Information authority. This gate validates Layer-1 metadata only. It does not invent a backend route and does not write Production.

## Official ST authority set

| Cohort | Authority |
| --- | --- |
| STM32H503 | DS14053 Rev 4 |
| STM32H523 | DS14540 Rev 3 |
| STM32H533 | DS14539 Rev 3 |
| STM32H543 | DS15168 Rev 1 |
| STM32H553 | DS15167 Rev 1 |
| STM32H562 / H563 | DS14258 Rev 6 |
| STM32H573 | DS14121 Rev 5 |
| STM32H5E4 / H5E5 | DS14971 Rev 1 |
| STM32H5F4 / H5F5 | DS14972 Rev 1 |

Each exact MPN is decoded using only the code vocabulary belonging to its own authority: pin count, Flash size, package, temperature, optional dedicated SMPS pinout, and packing.

Cross-subfamily inference is forbidden.

## Replay result

- locked Active exact MPNs: **190**
- metadata decoded: **190/190**
- blocked: **0**
- direct Ordering Information decode: **187**
- bounded exact ST Quality & Reliability exceptions: **3**

The three exceptions are:

- `STM32H5E4ZJJ6`
- `STM32H5E4ZJJ7Q`
- `STM32H5E4ZKJ6`

DS14971 Rev 1 lists STM32H5E4ZJ/ZK device references but its Ordering Information package-code table omits package code `J`. The official ST Quality & Reliability rows for these exact MPNs identify the package as **UFBGA 144 10x10x0.6 P 0.8 mm**.

The exception is therefore exact-identity bounded. It does **not** globally add `J` to the H5E package code map.

## Fail-closed semantic checks

The validator also enforces authority-specific combinations:

- H562/H563/H573:
  - temperature `3` requires `Q` / SMPS;
  - temperature `6` or `7` forbids `Q` because those Ordering Information entries are LDO-only.
- H5E/H5F:
  - temperature `7` requires `Q` / SMPS;
  - temperature `6` forbids `Q` because it is LDO-only.
- H543/H553:
  - temperature `3` is accepted only with package code `Z` (LQFP-EP).

Unknown code letters, missing exact exceptions, or invalid combinations fail closed.

## Layer separation

This gate establishes:

- Layer-1 identity: locked
- current manufacturer lifecycle: Active, locked by prior evidence
- metadata authority replay: **complete**
- Layer-1 admission proposal readiness: **true**

It deliberately does **not** establish:

- a Plasma STM32H5 OpenOCD route
- Programming Profile applicability
- Engineering Verified status
- operational/field evidence
- HIL success
- Production write authorization

All 190 remain Layer-2 `no_mapping` under the current Plasma backend inventory.

## Next gate

Prepare a reviewable **190-row STM32H5 Layer-1 Catalog admission proposal**, retaining `no_mapping` for all rows. Production publication remains a separate explicit owner-approval transaction.
