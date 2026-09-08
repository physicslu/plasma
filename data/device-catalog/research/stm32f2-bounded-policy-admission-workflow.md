# STM32F2 bounded policy and admission workflow

This document records the Phase 3 refactor that follows the bounded discovery,
evidence and planning work. The objective is to automate deterministic batch
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

The repeated mechanics live in `stm32f2_bounded_policy.py`. Per-batch choices
live in `stm32f2-bounded-policy-batches.json`.

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

`stm32f2_bounded_admission.py` remains a read-only planner and does not
duplicate the generic canonical writer.

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
count. It is not merely the logical ordering-code class. ST's STM32F20x
ordering table explicitly defines `R = 64 or 66 pins` and states that 66 pins
is available on WLCSP only. The retained ST product page identifies
`STM32F205REY6TR` as WLCSP 66. The STM32F21x ordering table defines `V = 100
pins`, and `F = 768 Kbytes` is defined by the STM32F20x ordering table.

Policy references:

- https://www.st.com/resource/en/datasheet/stm32f205rc.pdf
- https://www.st.com/resource/en/datasheet/stm32f217ve.pdf
- https://www.st.com/en/microcontrollers-microprocessors/stm32f205re.html

The immutable policy baseline is
`stm32f2-phase4.3i-policy-baseline.json`.

## Phase 4.3J admission and publication

The bounded admission planner replays from the guarded 22-row historical
STM32F2 canonical boundary and the closed Phase 4.3I policy baseline.

The deterministic admission result is:

```text
candidate_count                   11
admit                             11
already_present                    0
manual_review_required             0
reject                             0
STM32F2 canonical rows        22 -> 33
Production exact ICPNs       481 -> 492
STM32F2 Base Devices           8 -> 12
Production Base Devices      165 -> 169
```

The publication transaction is bound by:

```text
admission plan SHA-256
1b8649c284210076d74fa4b418c5f40554f5d74e1b03062054685d70f34faba8

published STM32F2 canonical SHA-256
69a9e02be14237bd2c683bc63eed4bd132ba62c5e8c334ef0e85671f868003d0

published STM32F2 canonical Git blob
1bec0770179f3849c6cfbb66aea9ad9d63610f55
```

`stm32f2-phase4.3j-admission-audit.json` records the immutable publication
accounting and proposal artifact identity. The Production manifest binds the
33-row STM32F2 source by both Git blob and SHA-256 content digest.

Post-admission regression reconstructs the historical 22-row canonical input,
replays the 4.3J plan, verifies the exact plan digest, writes 22 -> 33 in a
sandbox, requires the second write to be a no-op, and rejects unbound canonical
drift. This preserves the historical fail-closed boundary after publication.

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
- physical programming support merely because the catalog row is selectable.

Normal future STM32F2 batches should extend the JSON registry and reuse the
bounded engines. New phase-specific large policy/admission implementations
should be treated as an exception requiring a demonstrated new semantic rule.
