# STM32F2 bounded policy and admission workflow

This document records the Phase 3 refactor that follows the bounded discovery,
evidence and planning work.  The objective is to automate deterministic batch
mechanics without collapsing the governance boundaries between Discovery,
Policy, Admission and runtime/physical programming support.

## Duplication / invariants matrix

### Policy: historical Phase 4.3C vs 4.3F

| Concern | 4.3C | 4.3F | Generic owner |
| --- | --- | --- | --- |
| retained-evidence validation | yes | yes | bounded policy engine |
| evidence/provenance binding | yes | yes | bounded policy engine |
| OpenOCD candidate normalization | yes | yes | STM32F2 policy adapter |
| deterministic candidate ordering | yes | yes | generic admission framework |
| historical canonical boundary | 0 rows | 9 rows | batch registry + bounded policy engine |
| Production snapshot reconstruction | 459 | 468 | batch registry + bounded policy engine |
| Base Device scope | batch 1 | batch 2 | batch registry |
| candidate count | 9 | 13 | batch registry |
| metadata code semantics | B/C/E | B/C/E/G | batch registry |
| source authority | ST official retained evidence | same | STM32F2 policy adapter |
| manual-review/reject classification | yes | yes | generic admission framework + adapter |
| Production write | forbidden | forbidden | governance boundary |

The repeated mechanics now live in `stm32f2_bounded_policy.py`.  Per-batch
choices live in `stm32f2-bounded-policy-batches.json`.

### Admission: historical Phase 4.3D vs 4.3G

| Concern | 4.3D | 4.3G | Generic owner |
| --- | --- | --- | --- |
| require closed policy baseline | yes | yes | bounded admission planner |
| canonical schema validation | yes | yes | bounded admission planner |
| duplicate/conflict classification | yes | yes | `device_catalog_admission_framework.py` |
| canonical input SHA binding | yes | yes | `device_catalog_admission_framework.py` |
| deterministic row ordering | yes | yes | `device_catalog_admission_framework.py` |
| idempotent sandbox write | yes | yes | `device_catalog_admission_framework.py` |
| lifecycle exclusions | none | none | batch evidence/policy |
| Production write | separate controlled publish | same | governance / publication transaction |

`stm32f2_bounded_admission.py` therefore remains a read-only planner and does
not duplicate the generic canonical writer.

## Phase 4.3I policy

Discovery input: Phase 4.3H retained official-ST evidence.

Bounded Base Devices:

- `STM32F205RE`
- `STM32F207IF`
- `STM32F215VE`
- `STM32F217VE`

Exact Active ICPN candidates: 11.

The metadata contract extends the prior cumulative STM32F2 policy with:

- `F` Flash code = `768 KiB`;
- `Y` package code = `WLCSP`;
- `V/T` = LQFP, 100 pins;
- `R/Y` = WLCSP, 66 balls/pins.

The canonical `pin_count` field means the actual physical package pin or ball
count.  It is not merely the logical ordering-code class.  ST's STM32F20x
ordering table explicitly defines `R = 64 or 66 pins` and states that 66 pins
is available on WLCSP only.  The retained ST product page identifies
`STM32F205REY6TR` as WLCSP 66.  The STM32F21x ordering table defines `V = 100
pins`, and `F = 768 Kbytes` is defined by the STM32F20x ordering table.

Policy references:

- https://www.st.com/resource/en/datasheet/stm32f205rc.pdf
- https://www.st.com/resource/en/datasheet/stm32f217ve.pdf
- https://www.st.com/en/microcontrollers-microprocessors/stm32f205re.html

The immutable policy baseline is
`stm32f2-phase4.3i-policy-baseline.json`.

## Phase 4.3J admission planning

The bounded admission planner requires the checked-in Phase 4.3I policy
baseline and the current 22-row STM32F2 canonical boundary.

The deterministic pre-publication result is:

```text
candidate_count                        11
admit                                  11
already_present                         0
manual_review_required                  0
reject                                  0
canonical_rows_before                  22
canonical_rows_after_if_published      33
Production exact ICPNs before         481
Production exact ICPNs after          492
Production write applied            false
```

A clean plan is necessary but not sufficient for publication.  Publication
must remain a separate controlled transaction that writes the canonical CSV,
updates the Production manifest content bindings, records an immutable audit,
and passes the normal Device Catalog / product runtime validation gates.

## Governance boundary

Policy/admission of these rows proves only:

- exact commercial ICPN identity has authoritative retained ST evidence;
- lifecycle is Active for the admitted exact ICPN;
- the identity maps deterministically to `tcl/target/stm32f2x.cfg`;
- canonical metadata follows the bounded STM32F2 ordering-code policy.

It does **not** prove or authorize:

- programming-algorithm equivalence;
- native PPU support;
- socket/electrical qualification;
- real-target programming success;
- runtime programming enablement merely because the catalog row exists.

Normal future STM32F2 batches should extend the JSON registry and reuse the
bounded engines.  New phase-specific large policy/admission implementations
should be treated as an exception requiring a demonstrated new semantic rule.
