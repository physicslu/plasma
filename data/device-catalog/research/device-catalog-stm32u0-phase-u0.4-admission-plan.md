# Device Catalog — STM32U0 Phase U0.4 Read-only Admission Plan

## Status and scope

Phase U0.4 is a deterministic **read-only admission-planning transaction** for the 68 exact STM32U0 commercial identities closed by U0.2 and metadata-qualified by U0.3.

It does not write the STM32U0 canonical dataset and does not modify Production. It does not claim programming-algorithm equivalence, Flash-controller/geometry equivalence, option/security semantics, physical target qualification, HIL qualification, or runtime programming support.

## Input closure

U0.4 consumes only the closed U0.3 metadata set:

- 26 retained Base Devices;
- 68 manufacturer-verified Active exact ICPNs;
- 68 metadata-ready rows;
- U0.3 canonical metadata rows SHA-256 `89e15eea9e803014cd21f2a7b60137155a8153e30963f46e07624c23c66bac3d`;
- U0.3 policy baseline Git blob `8f766def80027050e09ee5fe594ef1f379b7c2b3`.

U0.4 cannot discover a 69th identity, reinterpret commercial lifecycle state, expand the bounded Ordering Information grammar, or mutate U0.3 metadata semantics.

## Independent routing capability gate

Commercial identity and metadata are necessary but not sufficient for Device Catalog admission planning.

For every one of the 68 exact ICPNs, U0.4 replays the current guarded OpenOCD ordering-pattern catalog through the existing STM32U0 `resolve_mapping()` path. A candidate is capability-admittable only when the mapping is exactly:

- `status = unique`;
- `match_count = 1`;
- `identifier_kind = ordering_pattern`;
- `target_configs = ["tcl/target/stm32u0x.cfg"]`;
- non-empty `existing_identifier`.

The current mapping catalog Git blob is `0ef056e3363e20bb527590c4a4cc1cc0d7afb810`. This equals the historical catalog blob bound by retained U0.2 evidence. U0.4 still performs a fresh deterministic replay rather than trusting the historical `unique` observation.

A catalog-byte change after this planning boundary fails closed and requires the admission plan to be recomputed in a new reviewed transaction.

## Deterministic result

The frozen compact U0.4 plan records:

| Dimension | Result |
| --- | ---: |
| Manufacturer-verified exact identities | 68 |
| Metadata-ready exact identities | 68 |
| Current unique OpenOCD routes | 68 |
| Ambiguous routes | 0 |
| Unmapped routes | 0 |
| Capability-admittable | 68 |
| Manual review | 0 |
| Reject | 0 |

The full 68 proposed canonical rows are rebuilt deterministically by `stm32u0_phase_u0_4_admission.py`; the retained JSON stores the compact admission summary and exact identity set instead of duplicating every proposed row.

## Canonical row projection

The U0.4 family adapter extends U0.3 manufacturer-backed metadata with routing fields:

- `cmsis_device_name` — always blank for these commercial exact identities;
- `existing_identifier` — the unique OpenOCD ordering pattern;
- `existing_identifier_kind = ordering_pattern`;
- `mapping_status = deterministic_ordering_pattern`;
- `openocd_target_config = tcl/target/stm32u0x.cfg`.

CMSIS aliases remain observational name surfaces only. They cannot satisfy the routing gate and cannot become exact commercial identities.

The package-dependent `M` code remains explicit:

- `STM32U073M8I6` → UFBGA81, mapped through `STM32U073M8Ix`;
- `STM32U073M8T6` → LQFP80, mapped through `STM32U073M8Tx`.

Packing suffixes also remain commercial identity semantics. For example `STM32U083CCT6TR` routes on commercial core `STM32U083CCT6` while retaining the exact `TR` identity in the proposed canonical row.

## Production boundary

Production remains unchanged at the U0.4 planning boundary:

- 635 exact ICPNs;
- 217 Base Devices;
- eight STM32 Production families;
- zero STM32U0 Production rows;
- Production manifest Git blob `34ad9299ff0c063a8c8b5de1c253dfee47b63428`.

No file under `data/device-catalog/production/` is modified by U0.4.

## What a clean U0.4 plan means

A clean U0.4 result means only:

> each of the 68 closed commercial identities has manufacturer-backed metadata and one deterministic route in the current Plasma OpenOCD mapping model, so it is eligible for a later controlled catalog-publication transaction.

It does **not** mean:

- OpenOCD can physically program every device;
- Flash algorithm/controller behavior has been qualified;
- erase/program/verify semantics are proven;
- option bytes or security transitions are understood;
- PPU runtime support exists;
- Z2/FPGA/SWD electrical behavior is qualified;
- real-IC HIL has passed.

Those claims belong to separate IC Support/runtime/HIL evidence chains.

## Fail-closed controls

U0.4 fails if:

- U0.2 retained commercial evidence no longer replays cleanly;
- U0.3 metadata policy or compact baseline drifts;
- the 68 exact identity set changes;
- the OpenOCD catalog bytes change from the frozen planning boundary;
- any exact identity loses its single `stm32u0x.cfg` ordering-pattern route;
- a CMSIS alias is used as a route identity;
- canonical prestate already contains STM32U0 rows;
- Production prestate drifts from the bound transaction snapshot;
- any programming/HIL/runtime authority flag becomes true.

## Next phase

U0.5 may perform **controlled publication** of the clean U0.4 admission set. That must be a separate transaction with its own Gate 1 approval and deterministic prestate/write/idempotency checks.
