# Device Catalog Phase 4.6D — STM32F7 Admission Planning

## Decision

Phase 4.6D combines the closed Phase 4.6C manufacturer-backed metadata policy with an independent OpenOCD ordering-pattern capability gate and produces a deterministic **read-only canonical admission plan**.

The frozen result is:

- 19 exact Active ICPN candidates;
- 19 `admit` decisions;
- 0 `already_present`;
- 0 manual review;
- 0 reject;
- 0 canonical STM32F7 rows before admission;
- all 19 candidates uniquely map to `tcl/target/stm32f7x.cfg`;
- 5 lifecycle exclusions remain excluded;
- 2 source-unavailable exclusions remain unresolved/excluded.

The frozen admission-plan SHA-256 is:

`1e13d87d9d4e445efb5dbb43b79bad1bf3b5b916126095fb5a55c58580691a7e`

## What the capability gate proves

For each of the 19 exact commercial identities, the current guarded OpenOCD source contains exactly one matching `ordering_pattern`, and that match routes to exactly one target configuration:

`tcl/target/stm32f7x.cfg`

The canonical proposal therefore records:

- `existing_identifier_kind=ordering_pattern`;
- `mapping_status=deterministic_ordering_pattern`;
- `openocd_target_config=tcl/target/stm32f7x.cfg`.

This is a **routing/capability evidence boundary**, not proof that every STM32F7 device has identical flash algorithms or electrical behavior.

## Negative controls

Permanent regression rejects or requires manual review for:

- unmapped exact ICPNs;
- ambiguous mapping;
- mapping to a non-STM32F7 target configuration;
- non-`ordering_pattern` identifier kinds;
- missing ordering-pattern identifiers;
- non-zero STM32F7 canonical prestate;
- changes to the frozen 19-candidate identity set;
- changes to the frozen admission plan;
- loss of the 5 lifecycle exclusions or 2 source-unavailable exclusions.

## Production boundary

Phase 4.6D planning uses the frozen Phase 4.6C Production prestate:

- 544 Production exact ICPNs;
- 188 Production Base Devices;
- STM32F7 Production exact ICPNs: 0.

The frozen plan states:

- `canonical_dataset_admission=planned`;
- `canonical_write_applied=false`;
- `production_write_applied=false`.

Therefore this phase does not itself alter the canonical CSV or Production manifest.

## Claims intentionally false

Phase 4.6D does not claim:

- programming-algorithm equivalence;
- flash-geometry equivalence across STM32F7;
- option-byte/security equivalence;
- socket/electrical qualification;
- HIL qualification;
- runtime programming support;
- complete STM32F7 commercial-family coverage.

A unique OpenOCD route proves only that the guarded programmer source has a deterministic family routing path for the exact identity. It does not prove that Plasma has exercised or qualified that path on physical hardware.

## Next transaction

After this read-only plan passes permanent CI and merges, canonical/Production publication may be performed as a separate controlled transaction. That transaction must:

1. replay this exact frozen admission plan;
2. create the STM32F7 canonical CSV deterministically;
3. verify CSV SHA-256 and Git blob identity;
4. update the Production manifest from the frozen 544/F7=0 prestate;
5. produce a publication audit that preserves all false runtime/HIL claims;
6. run current/global catalog validation after publication.

Publication changes catalog identity availability. It still does not, by itself, assert real-device programming qualification.
