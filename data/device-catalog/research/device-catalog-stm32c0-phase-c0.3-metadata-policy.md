# Device Catalog — STM32C0 Phase C0.3 Metadata Policy

## Status and scope

STM32C0 Phase C0.3 defines deterministic manufacturer-authoritative commercial metadata for exactly the 220 Active exact ICPNs / 50 Base Devices retained by C0.2.

C0.3 does **not** expand commercial identity scope and does not publish STM32C0 to Production. It does not claim programming-policy or algorithm equivalence, Flash-controller qualification, option/security qualification, physical/HIL qualification, or PPU/runtime programming support.

The policy is intentionally bounded. A syntactically valid STM32C0 ordering code that is not present in the frozen C0.2 Active exact-ICPN set is rejected rather than inferred into C0.3.

## Authority separation

C0.3 keeps two evidence domains separate:

1. **Commercial identity/lifecycle authority** — retained C0.2 official ST Quality & Reliability exact identity plus Sample & Buy Marketing Status exact-set join.
2. **Canonical commercial metadata authority** — official ST datasheet Ordering Information, frozen in `stm32c0-phase-c0.3-ordering-authority.json`.

OpenOCD routing is neither identity nor metadata authority. CMSIS aliases are neither commercial identity nor metadata authority. The six C0.2 Base Devices without an OpenOCD ordering-pattern route therefore remain valid metadata candidates when manufacturer identity and Ordering Information semantics are complete.

## Frozen input boundary

C0.3 consumes the immutable C0.2 retained transaction:

- Base Devices: **50**;
- unique Active exact ICPNs: **220**;
- source-unavailable targets: **0**;
- identity manual-review targets: **0**;
- lifecycle-only Base Devices: **0**;
- excluded non-Active exact part: **1** — `STM32C091KBT3` (`Preview`);
- OpenOCD routing: **44 unique / 6 unmapped**, non-gating.

C0.3 explicitly rejects the Preview part and any other exact identity outside the retained Active set.

## Official Ordering Information authorities

The official ST document surface was revalidated on 2026-09-12. No revision drift was observed.

| Series | ST document | Revision | Ordering section | PDF page |
| --- | --- | ---: | ---: | ---: |
| STM32C011 | DS13866 | 5 | 7 | 93 |
| STM32C031 | DS13867 | 4 | 7 | 100 |
| STM32C051 | DS14721 | 2 | 7 | 107 |
| STM32C071 | DS14693 | 2 | 7 | 128 |
| STM32C091 | DS14720 | 3 | 7 | 121 |
| STM32C092 | DS14720 | 3 | 7 | 121 |

STM32C091 and STM32C092 legitimately share DS14720, but their manufacturer series identity remains distinct.

The frozen authority artifact SHA-256 is:

`691733479e7f89ac9f9fe1dbd7cd95a7db6be8b27e7d75a77ae38b853d3899b0`

## Critical STM32C0 ordering semantics

### C071 product version versus packing

C071 uses manufacturer-defined suffix semantics that must not be collapsed:

- blank: standard product version, tray packing;
- `TR`: standard product version, tape-and-reel packing;
- `N`: N product version, tray packing;
- `NTR`: N product version, tape-and-reel packing.

`N` is not packing and `TR` is not product-version identity. The C0.3 canonical `option_suffix` preserves the exact suffix rather than pretending these meanings are equivalent.

### C071 package-dependent pin count

The pin designator cannot always be interpreted independently from package:

- `F/P` → TSSOP20;
- `F/Y` → WLCSP19.

The C0.3 parser therefore resolves pin count from the bounded `pin/package` pair.

### C091 / C092 shared document authority

DS14720 covers both C091 and C092. Shared document authority does not authorize normalization of one series into the other. Series and Base Device remain exact manufacturer-defined identities.

## Deterministic metadata result

GitHub Actions replayed the retained C0.2 evidence and C0.3 policy and observed:

```text
candidate_count:        220
base_device_count:      50
metadata_ready:         220
manual_review_required: 0
reject:                 0
```

This is an observed result, not a target forced by the policy. Any unknown retained code would have produced a manual-review or reject decision instead of being guessed into the 220/220 result.

Frozen exact-ICPN-set SHA-256:

`b116f624e971a3be5c947e107589bdb4d1bf5f5b0585ecae71e743cfb7a2649a`

Frozen metadata-row SHA-256:

`94ebe11fda28cb6d7b68c13c7edb4bf8341887f6146d52f72461bc6ef35bee19`

### Metadata distributions

| Dimension | Distribution |
| --- | --- |
| Flash | 16 KiB: 20; 32 KiB: 51; 64 KiB: 49; 128 KiB: 55; 256 KiB: 45 |
| Package | LQFP: 77; SO8N: 7; TSSOP: 31; UFBGA: 7; UFQFPN: 97; WLCSP: 1 |
| Pin count | 8: 7; 19: 1; 20: 36; 28: 31; 32: 63; 48: 57; 64: 25 |
| Temperature | -40..85 C: 127; -40..105 C: 54; -40..125 C: 39 |
| Option suffix | blank: 121; `TR`: 80; `N`: 16; `NTR`: 3 |

## Production prestate

C0.3 freezes, but does not modify, the current Production prestate:

```text
exact ICPNs:       703
Base Devices:      243
STM32 families:    9
STM32C0 exact IDs: 0
```

The C0.3 copied Production manifest is byte-identical to Git blob:

`89cbaa8807daf8f9c55bc8c1ca0bc1c05eaec1fc`

C0.3 creates no Production catalog row and does not reinterpret metadata readiness as admission.

## Fail-closed controls

C0.3 validation fails or rejects when:

- a candidate is outside the retained C0.2 Active exact set;
- the excluded Preview part is presented as metadata-ready;
- a CMSIS-shaped identifier is presented as a commercial identity;
- official Ordering Information document/revision bindings drift;
- a required package, pin/package, Flash, temperature, product-version, or packing code is not in the bounded authority;
- C071 `N` semantics are removed or collapsed with `TR`;
- C091/C092 manufacturer series are collapsed;
- OpenOCD or CMSIS is promoted to metadata authority;
- Production, admission, programming, Flash/security, HIL, or runtime authority becomes true.

The permanent C0.3 validator also replays the frozen metadata rows and exact-identity set by digest.

## Phase boundary

C0.3 establishes **metadata readiness only**.

The next transaction, **C0.4**, may build a separate read-only admission plan using the frozen C0.3 metadata rows plus independently governed routing/capability evidence. C0.4 must not be inferred from C0.3 success and requires its own Gate 1 approval.

Only a later controlled publication transaction may modify Production.
