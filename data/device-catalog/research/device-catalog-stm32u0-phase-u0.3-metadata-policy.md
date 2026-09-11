# Device Catalog — STM32U0 Phase U0.3 Metadata Policy

## Status and scope

Phase U0.3 defines deterministic canonical metadata for the 68 exact STM32U0 identities retained as Active in U0.2. It does **not** admit STM32U0 to Production and does not claim programming-algorithm equivalence, Flash-controller qualification, option/security semantics, physical/HIL qualification, or runtime support.

The policy boundary is intentionally narrower than the full STM32U0 ordering grammar. Only the 68 retained U0.2 exact identities may enter metadata scope. A syntactically valid but unretained ordering code is rejected rather than inferred into the catalog.

## Authority separation

Two evidence domains remain separate:

1. **Commercial identity/lifecycle authority** — retained U0.2 official ST Quality & Reliability `Part Number` + `Marketing Status` evidence.
2. **Canonical metadata authority** — official ST datasheet Ordering Information section frozen in `stm32u0-phase-u0.3-ordering-authority.json`.

OpenOCD routing is not a metadata authority. CMSIS aliases are not a metadata authority. Neither source can create, normalize, or promote a commercial exact part number in U0.3.

## Bounded candidate set

U0.3 consumes exactly 26 retained Base Devices and 68 retained Active exact ICPNs, with zero U0.2 lifecycle exclusions, source-unavailable targets, or identity manual-review targets.

The U0.2 retained target projection SHA-256 remains `4133860a090b1c5cc01449041fb49e0b5dd60d686e1338a343f8ea18d577e2e0` and the U0.2 retained discovery baseline SHA-256 remains `3583553d75d204ccf684544ba6622c913690d2eacf059c27f9b5d88be9ddc0b1`.

## Official Ordering Information authorities

The H006/U0.1 retained authorities were checked again against the current official ST documentation surface on 2026-09-11. No revision drift was observed.

| Series | ST document | Revision | Ordering section | PDF page | Current-revision drift |
| --- | --- | ---: | ---: | ---: | --- |
| STM32U031 | DS14581 | 2 | 8 | 124 | none |
| STM32U073 | DS14548 | 2 | 8 | 135 | none |
| STM32U083 | DS14463 | 2 | 8 | 135 | none |

Structured official-PDF text is the authority surface. Screenshot retrieval cache misses remain explicit method limitations and are not silently upgraded into visual verification.

## Bounded ordering semantics

Only code combinations used by the retained 68 identities are frozen.

### STM32U031

- pin/package: `F/P=20`, `K/U=32`, `C/T=48`, `C/U=48`, `R/I=64`, `R/T=64`;
- Flash: `4=16 KiB`, `6=32 KiB`, `8=64 KiB`;
- package: `P=TSSOP`, `T=LQFP`, `U=UFQFPN`, `I=UFBGA`;
- temperature: `3=-40..125 C`, `6=-40..85 C`;
- packing: blank = standard, `TR` = tape and reel.

### STM32U073 / STM32U083

- pin/package: `K/U=32`, `C/T=48`, `C/U=48`, `R/I=64`, `R/T=64`, `M/T=80`, `M/I=81`;
- U073 Flash: `8=64 KiB`, `B=128 KiB`, `C=256 KiB`;
- U083 Flash: `C=256 KiB`;
- package: `T=LQFP`, `U=UFQFPN`, `I=UFBGA`;
- temperature: `3=-40..125 C`, `6=-40..85 C`;
- packing: blank = standard, `TR` = tape and reel.

The `M` code demonstrates why pin count cannot be normalized independently from package: `M/T` is LQFP80 while `M/I` is UFBGA81.

## Frozen metadata result

The U0.3 baseline represents 68 metadata-ready rows with no reject or manual-review decisions. Full rows are replayed deterministically; the baseline stores their canonical SHA-256 rather than duplicating them.

Canonical metadata rows SHA-256: `89e15eea9e803014cd21f2a7b60137155a8153e30963f46e07624c23c66bac3d`.

| Dimension | Distribution |
| --- | --- |
| Flash | 16 KiB: 4; 32 KiB: 7; 64 KiB: 16; 128 KiB: 13; 256 KiB: 28 |
| Package | TSSOP: 5; LQFP: 27; UFQFPN: 26; UFBGA: 10 |
| Pin count | 20: 5; 32: 14; 48: 22; 64: 15; 80: 8; 81: 4 |
| Temperature | -40 to 85 C: 55; -40 to 125 C: 13 |
| Packing suffix | standard: 52; TR: 16 |

Ordering-authority SHA-256: `4e33a1821ba3df32193a93501275f1b638636735b68c37c595c81cc04787ebfa`.

## Production prestate

U0.3 freezes the transaction prestate without changing Production: 635 exact ICPNs, 217 Base Devices, eight families (STM32F0/F1/F2/F3/F4/F7/G0/G4), and zero STM32U0 exact ICPNs.

The copied U0.3 prestate is byte-for-byte identical to Production manifest Git blob `34ad9299ff0c063a8c8b5de1c253dfee47b63428` at the transaction boundary.

## Fail-closed controls

U0.3 rejects or fails if the U0.2 replay fails, identity scope changes, an unretained/CMSIS-shaped identifier enters metadata scope, Ordering Information bindings or revision checks drift, a retained code becomes unbound, `M/T` and `M/I` are collapsed, OpenOCD/CMSIS becomes metadata authority, or any Production/admission/programming/Flash-security/HIL/runtime authority flag becomes true.

## Phase boundary

U0.3 establishes `metadata_ready` only. It does not establish programmability or product support.

The next transaction, U0.4, may construct a **read-only admission plan** using these frozen 68 metadata rows plus separately governed routing/capability evidence. Only a later controlled publication transaction may modify Production.
