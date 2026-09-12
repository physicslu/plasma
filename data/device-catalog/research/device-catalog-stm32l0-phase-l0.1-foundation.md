# Device Catalog — STM32L0 Phase L0.1 Foundation

## Status and scope

STM32L0 L0.1 is a bounded **research foundation** transaction. It consumes the post-C0 selection that chose `STM32L0`, freezes the current OpenOCD-derived L0 research surface, and binds one deterministic representative Base Device per ordering-pattern subfamily to already-retained official-ST commercial identity/lifecycle and Ordering Information evidence.

L0.1 does **not** perform complete STM32L0 commercial discovery. It does not authorize canonical admission, Production publication, programming policy, Flash-controller or geometry equivalence, option/security behavior, socket/electrical or HIL qualification, or PPU/runtime programming support.

## Frozen selection input

The transaction is bound to:

- selection: `stm32-post-c0-next-family-selection.json`
- selected family: `STM32L0`
- scope: `next_family_research_only`
- selection SHA-256: `a46cef39516bf94901b979ccfc446b5720b2c6855b46ede1765232f6082df134`

## Bounded OpenOCD research surface

L0.1 freezes STM32L0 at:

- target config: `tcl/target/stm32l0.cfg`
- source rows: **166**
- ordering-pattern rows: **164**
- CMSIS alias rows: **2**
- ordering-pattern subfamilies: **16**

Subfamilies:

`STM32L010`, `STM32L011`, `STM32L021`, `STM32L031`, `STM32L041`, `STM32L051`, `STM32L052`, `STM32L053`, `STM32L062`, `STM32L063`, `STM32L071`, `STM32L072`, `STM32L073`, `STM32L081`, `STM32L082`, `STM32L083`.

OpenOCD/CMSIS data bounds research only. It is not commercial identity authority and is not programming-support evidence.

OpenOCD catalog SHA-256:

`43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`

## Deterministic representatives

One lexical-min Base Device is selected per guarded ordering-pattern subfamily:

| Subfamily | Representative |
|---|---|
| STM32L010 | STM32L010C6 |
| STM32L011 | STM32L011D3 |
| STM32L021 | STM32L021D4 |
| STM32L031 | STM32L031C4 |
| STM32L041 | STM32L041C6 |
| STM32L051 | STM32L051C6 |
| STM32L052 | STM32L052C6 |
| STM32L053 | STM32L053C6 |
| STM32L062 | STM32L062C8 |
| STM32L063 | STM32L063C8 |
| STM32L071 | STM32L071C8 |
| STM32L072 | STM32L072CB |
| STM32L073 | STM32L073CB |
| STM32L081 | STM32L081CB |
| STM32L082 | STM32L082CZ |
| STM32L083 | STM32L083CB |

CMSIS aliases cannot enter commercial representative selection.

## Manufacturer evidence binding

L0.1 reuses the retained post-C0 official-ST dual-surface evidence. No new live acquisition is required.

The commercial authority remains:

- Quality & Reliability for exact Part Number identity;
- Sample & Buy for Marketing Status;
- exact identity/lifecycle sets joined fail-closed.

For STM32L0 the retained evidence records:

- 16/16 representative targets verified Active;
- 0 lifecycle-excluded representative targets;
- 0 manual-review targets;
- 44 Active exact ICPNs observed across the 16 representatives.

The **44 exact ICPNs are representative evidence only**, not a complete STM32L0 family inventory.

Retained evidence SHA-256:

`45c3020462601e6cb36e726cc1acc4203abc36a96063a5223ab5c7511bcff02c`

Target-manifest SHA-256:

`767ad681a7d8e839cbf68b507babb2c417905a2f40a380566e773fa987ab9434`

## Ordering Information binding

Official ST Ordering Information is complete for all 16 representatives using 16 official datasheets, with zero blocking issues and no revision drift at the retained review boundary.

Two semantics are explicitly preserved:

- `STM32L010` uses a narrower ordering grammar and does not expose the general L0 D/BOR option.
- `STM32L031` `S` is an official UFQFPN28 one-power-pair option and must not be normalized away.

Post-C0 comparison review SHA-256:

`d16e71cb322c7da754ed12cc1bd0e984015888cbf8bdb07685e1d87966ad8612`

Detailed L0 Ordering review SHA-256:

`9f4bde47508100025d3d6e92813f244431a18d95cf3fc73a45de93849dddd38d`

## Immutable Production boundary

Historical replay is bound to the immutable post-C0 Production prestate rather than the mutable live manifest.

- prestate SHA-256: `15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420`
- exact ICPNs: **912**
- Base Devices: **293**
- STM32 Production families: **10**
- STM32L0 Production exact ICPNs: **0**

L0.1 performs **zero Production writes**.

## Frozen foundation baseline

- baseline: `stm32l0-phase-l0.1-foundation-baseline.json`
- SHA-256: `958572fa69a4457966256851a39badfdc38490e0c3ce155978155baf3ca9e488`

The baseline stores the bounded surface, deterministic representatives, evidence digests and fail-closed authority claims. Exact representative ICPNs remain in the retained evidence rather than being duplicated as a second identity source of truth.

## Validation

Permanent deterministic validation consists of:

- `stm32l0_phase_l0_1_foundation.py`
- `test_stm32l0_phase_l0_1_foundation.py`
- `validate_stm32l0_phase_l0_1_foundation.py`
- `.github/workflows/device-catalog-stm32l0-l01-foundation-validation.yml`

Controls cover surface counts, target config, ordering-pattern parsing, CMSIS exclusion, deterministic representatives, immutable evidence digests, exact-set lifecycle integrity, official-ST Ordering authority, L010/L031 special semantics, immutable 912-row Production prestate, byte-level baseline lock, and all admission/programming/HIL/runtime authority boundaries remaining false.

## Next transaction

After L0.1 is merged, the next Device Catalog transaction may be **STM32L0 L0.2 — Manufacturer-Authoritative Commercial Discovery**. It must obtain the complete bounded commercial identity/lifecycle inventory and requires a **new Gate 1**.
