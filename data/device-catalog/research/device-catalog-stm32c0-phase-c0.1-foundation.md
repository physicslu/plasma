# Device Catalog — STM32C0 Phase C0.1 Foundation

## Status

Research foundation only. C0.0 deterministically selected `STM32C0` as the next research family after post-U0 manufacturer-evidence and Ordering Information review. C0.1 freezes the bounded OpenOCD-derived STM32C0 research surface and binds six deterministic representatives to the retained official-ST C0.0 evidence.

C0.1 does **not** authorize canonical admission, Production publication, programming-algorithm equivalence, Flash geometry, option/security semantics, physical/HIL qualification, or runtime programming support.

The 21 exact Active ICPNs referenced by C0.1 are the exact ICPNs observed for the six deterministic representatives. They are **not** a complete STM32C0 family inventory. Complete commercial discovery is intentionally deferred to C0.2.

## Frozen selection input

C0.1 is bound to the C0.0 frozen selection:

- selection: `stm32-post-u0-next-family-selection.json`
- selected family: `STM32C0`
- selection scope: `next_family_research_only`
- selection SHA-256: `f2bc4d955952cc8c25362ca5568e944470f7a1b43bf41dee2fcca9516e9c8773`

The selection remains research-only and all authority-boundary claims remain false.

## Bounded OpenOCD research surface

C0.1 freezes the current upstream-OpenOCD-derived STM32C0 surface at:

- target config: `tcl/target/stm32c0x.cfg`
- source rows: **95**
- `ordering_pattern` rows: **73**
- `cmsis_device_name` rows: **22**
- subfamilies: `STM32C011`, `STM32C031`, `STM32C051`, `STM32C071`, `STM32C091`, `STM32C092`

OpenOCD/CMSIS data bounds research only. It is not commercial identity authority and is not programming-support evidence.

## Deterministic representatives

One lexical-min Base Device is selected from the guarded ordering-pattern surface for each subfamily:

| Subfamily | Representative Base Device |
|---|---|
| STM32C011 | STM32C011F4 |
| STM32C031 | STM32C031C4 |
| STM32C051 | STM32C051C6 |
| STM32C071 | STM32C071C8 |
| STM32C091 | STM32C091CB |
| STM32C092 | STM32C092CB |

CMSIS aliases cannot enter commercial representative selection.

## Manufacturer evidence binding

C0.1 is bound to the retained C0.0 official-ST evidence summary:

- path: `evidence/stm32-c0-l1-l0-post-u0-live-2026-09-11/probe-summary.json`
- SHA-256: `1bfa9da6e6b3d020c3f643eb5d6c72ee7ee5c8aa995c66de21fa7576b79a9228`
- C0 representatives attempted: **6**
- verified identity targets: **6**
- Active representative targets: **6**
- manual review: **0**
- source unavailable: **0**
- lifecycle exclusions: **0**
- exact Active ICPNs observed for these representatives: **21**

The evidence authority is the C0.0 retained exact-set join of official ST Q&R identity and Sample & Buy Marketing Status. The Q&R-only C0 layout diagnostic is not used as family-quality evidence.

## Ordering Information binding

C0.1 is bound to:

- review: `stm32-c0-l0-post-u0-ordering-authority-review.json`
- SHA-256: `9f4bde47508100025d3d6e92813f244431a18d95cf3fc73a45de93849dddd38d`

Official ST Ordering Information authorities for the six representatives are:

| Representative | Datasheet | Revision | Ordering page |
|---|---:|---:|---:|
| STM32C011F4 | DS13866 | 5 | 93 |
| STM32C031C4 | DS13867 | 4 | 100 |
| STM32C051C6 | DS14721 | 2 | 107 |
| STM32C071C8 | DS14693 | 2 | 128 |
| STM32C091CB | DS14720 | 3 | 121 |
| STM32C092CB | DS14720 | 3 | 121 |

The review reports complete required Ordering Information coverage, zero blocking evidence issues, and no revision drift at the C0.0 review boundary.

## Frozen foundation baseline

Canonical C0.1 baseline:

- `stm32c0-phase-c0.1-foundation-baseline.json`
- SHA-256: `c89e8c528f80f9b199a2b153d3d40aa4af090e50c492a7c88bfa7876ce406515`

The baseline records the bounded surface, deterministic representatives, representative exact ICPNs, official Ordering Information authorities, input evidence hashes, and fail-closed authority claims.

## Validation

Permanent deterministic validation consists of:

- `stm32c0_phase_c0_1_foundation.py`
- `test_stm32c0_phase_c0_1_foundation.py`
- `validate_stm32c0_phase_c0_1_foundation.py`
- `.github/workflows/device-catalog-stm32c0-c01-foundation-validation.yml`

Controls include:

- exact source-row and identifier-kind counts;
- exact six-subfamily surface;
- exact target config;
- deterministic representative selection;
- CMSIS exclusion from commercial representative selection;
- malformed ordering-pattern rejection;
- target-config and identifier-kind drift rejection;
- frozen C0.0 selection/evidence/Ordering hashes;
- representative-only inventory semantics;
- byte-level C0.1 baseline SHA-256 hard lock;
- all admission/capability/Production claims remain false.

## Production boundary

C0.1 performs **zero Production writes**. Production remains the state established before this transaction:

- exact ICPNs: **703**
- Base Devices: **243**
- STM32 Production families: **9**
- STM32C0 Production exact ICPNs: **0**

C0.1 must not be interpreted as a 21-device Production addition.

## Next transaction

The next Device Catalog transaction is **STM32C0 C0.2 — Manufacturer-Authoritative Commercial Discovery**. C0.2 should expand the frozen 73 ordering-pattern research surface into the deterministic Base Device set and obtain the complete bounded exact commercial ICPN/lifecycle inventory from official ST evidence. It requires a new Gate 1 approval.
