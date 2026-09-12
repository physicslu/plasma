# Device Catalog — STM32C0 Phase C0.4 Read-only Admission Plan

## Status and scope

Phase C0.4 is a deterministic **read-only capability/admission-planning transaction** for the 220 exact STM32C0 commercial identities closed by C0.2 and metadata-qualified by C0.3.

It does not write the STM32C0 canonical dataset and does not modify Production. It does not claim programming-algorithm equivalence, Flash-controller/geometry equivalence, option/security semantics, physical target qualification, HIL qualification, or runtime programming support.

## Input closure

C0.4 consumes only the closed C0.3 metadata set:

- 50 retained Base Devices;
- 220 manufacturer-verified Active exact ICPNs;
- 220 metadata-ready rows;
- C0.3 metadata rows SHA-256 `94ebe11fda28cb6d7b68c13c7edb4bf8341887f6146d52f72461bc6ef35bee19`;
- C0.3 policy-ready exact-set SHA-256 `b116f624e971a3be5c947e107589bdb4d1bf5f5b0585ecae71e743cfb7a2649a`;
- C0.3 policy baseline Git blob `4272a441f072433b0dfe726f1d97459bbad957f3`.

C0.4 cannot discover a 221st identity, reinterpret commercial lifecycle state, expand Ordering Information semantics, or mutate C0.3 metadata.

## Independent routing capability gate

Commercial identity and metadata are necessary but not sufficient for Device Catalog admission planning.

For every one of the 220 exact ICPNs, C0.4 replays the current guarded OpenOCD ordering-pattern catalog through the existing STM32C0 `resolve_mapping()` path. A candidate is capability-admittable only when the mapping is exactly:

- `status = unique`;
- one non-empty ordering pattern ending in `x`;
- `target_config = tcl/target/stm32c0x.cfg`;
- the commercial core is covered by that ordering pattern.

The current mapping catalog Git blob is `0ef056e3363e20bb527590c4a4cc1cc0d7afb810`. It is byte-identical to the historical catalog bound by retained C0.2 evidence. C0.4 still performs a fresh deterministic replay rather than trusting the historical routing summary.

A catalog-byte change after this planning boundary fails closed and requires recomputation in a new reviewed transaction.

## Deterministic result

| Dimension | Result |
| --- | ---: |
| Manufacturer-verified exact identities | 220 |
| Metadata-ready exact identities | 220 |
| Current unique OpenOCD routes | 209 |
| Ambiguous routes | 0 |
| Unmapped routes | 11 |
| Capability-admittable | 209 |
| Capability-unresolved | 11 |
| Canonical identity rejects | 0 |

The capability-unresolved exact set is frozen as:

- `STM32C051K8U3`
- `STM32C051K8U3TR`
- `STM32C051K8U6`
- `STM32C051K8U6TR`
- `STM32C051K8U7`
- `STM32C051K8U7TR`
- `STM32C071FBY6TR`
- `STM32C071R8I6N`
- `STM32C071RBI6N`
- `STM32C091RBI6`
- `STM32C092RBI6`

Exact unresolved-set SHA-256: `32698be0aee4f95360a1b27ddfecd1034d7627e0b223dd8873153b5d96ec5601`.

These 11 identities remain **manufacturer-verified Active and metadata-ready**. Their exclusion is a capability-routing decision, not a commercial identity rejection.

## Why Base Device routing counts are not the admission count

C0.2 reported 44 unique and 6 unmapped **Base Devices**. Some of those six Base Devices contain a mixture of uniquely routed and unmapped exact ICPNs. C0.4 therefore applies the gate at exact-ICPN level, not Base Device level.

The six mixed Base Devices are:

- `STM32C051K8`
- `STM32C071FB`
- `STM32C071R8`
- `STM32C071RB`
- `STM32C091RB`
- `STM32C092RB`

Their uniquely routed exact identities remain eligible for the read-only admission plan; only the 11 exact unresolved identities are excluded.

## Metadata semantics remain independent

Routing does not rewrite C0.3 manufacturer semantics. In particular:

- `STM32C071FBY6TR` remains WLCSP19 + `TR`, even though it is currently unmapped;
- `STM32C071R8I6N` and `STM32C071RBI6N` retain official C071 `N` product-version semantics;
- C091 and C092 remain distinct manufacturer series despite shared DS14720 authority;
- CMSIS names remain observational alias surfaces and cannot satisfy the route gate.

## Production boundary

Production remains unchanged at the C0.4 planning boundary:

- **703 exact ICPNs**;
- 243 Base Devices;
- nine STM32 Production families;
- zero STM32C0 Production rows;
- Production manifest Git blob `89cbaa8807daf8f9c55bc8c1ca0bc1c05eaec1fc`;
- Production manifest SHA-256 `903476d41997f9d20c237bccea0ee1e085fc343730e0d3740b2b82b0de0462b0`.

No file under `data/device-catalog/production/` is modified by C0.4.

## What a clean C0.4 plan means

A clean C0.4 result means only:

> 209 of the 220 closed commercial identities have manufacturer-backed metadata plus one deterministic route in the current Plasma OpenOCD mapping model and are eligible for a later controlled catalog-publication transaction; 11 remain capability-unresolved without losing their commercial identity or metadata qualification.

It does **not** mean:

- OpenOCD can physically program every admitted device;
- Flash algorithm/controller behavior has been qualified;
- erase/program/verify semantics are proven;
- option bytes or security transitions are understood;
- PPU runtime support exists;
- Z2/FPGA/SWD electrical behavior is qualified;
- real-IC HIL has passed.

Those claims belong to separate IC Support/runtime/HIL evidence chains.

## Fail-closed controls

C0.4 fails if:

- C0.2 retained commercial evidence no longer replays cleanly;
- C0.3 metadata policy or frozen baseline drifts;
- the 220 exact identity set changes;
- the OpenOCD catalog bytes change from the frozen planning boundary;
- the exact unresolved set changes from the reviewed 11 identities;
- an admitted identity loses its unique `stm32c0x.cfg` ordering-pattern route;
- a CMSIS-shaped identifier is used as a route identity;
- canonical prestate already contains STM32C0 rows;
- Production prestate drifts from 703 exact ICPNs / 243 Base Devices;
- any programming/HIL/runtime authority flag becomes true.

## Next phase

C0.5 may perform **controlled publication of the 209 capability-admittable identities**. The 11 capability-unresolved identities must remain excluded unless a later reviewed routing-evidence transaction positively resolves them.

C0.5 is a separate transaction and requires its own Gate 1 approval with deterministic prestate/write/idempotency controls.
