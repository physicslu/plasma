# ST STM32F103 Low-density 12 exact ICPNs — Gate 1 Path 1

**State: source-review candidate only; NOT Level 2; Draft PR; no merge/deployment/hardware.**

## Authority / provenance

- ADR-0002 remains the only Catalog Level and ProgrammingQualification authority.
- Fixed PLASMA OpenOCD: v0.12.0, commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`, `stm32f1x.cfg` and `stm32f1x.c`. The `stm32f1x` driver has an explicit Low-density `0x412` probe branch, 1024-byte pages, 32-KiB maximum *fallback*, and halfword writes.
- ST official: **DS5936, DocID15060 Rev 7**, June 2015, [STM32F103x4/x6 datasheet](https://www.st.com/resource/en/datasheet/stm32f103c6.pdf), Table 1 (x4/x6), Table 2 (pin/package), Table 58 (ordering and TR).
- ST PM0075 Rev 2 is already original-byte SHA-256 pinned at `data/ic-support/benchmarks/stm32f103c/source-lock.json`.
- **Blocking source custody:** DS5936 official PDF was visually reviewed online, but the original PDF bytes could not be acquired in the approved repository execution environment. Its original PDF SHA-256 and byte length are therefore `null`, not invented. `stm32f103-low-density-ds5936-source-lock-v1.json` explicitly records `INCOMPLETE_FAIL_CLOSED`. The requested genuine SHA-256 lock is **NOT DONE**, and no part is `SUPPORTED`.

## Exact candidate cohort — 12

| Base device | Exact ICPNs | Flash / pages |
| --- | --- | --- |
| STM32F103C4 | STM32F103C4T6A | 16 KiB / 16 × 1 KiB |
| STM32F103C6 | STM32F103C6T6A, STM32F103C6T6ATR, STM32F103C6T7A, STM32F103C6T7ATR, STM32F103C6U6A | 32 KiB / 32 × 1 KiB |
| STM32F103R4 | STM32F103R4H6A, STM32F103R4T6A | 16 KiB / 16 × 1 KiB |
| STM32F103R6 | STM32F103R6H6A, STM32F103R6T6A, STM32F103R6T6ATR, STM32F103R6T7A | 32 KiB / 32 × 1 KiB |

Three explicit exclusions: `STM32F103T4U6A`, `STM32F103T6U6A`, `STM32F103T6U7A`. ST DS5936 Table 2 gives T-pin36 **VFQFPN36**, while the current Canonical CSV says **UFQFPN**; keep these at L1 until independent source-backed Catalog reconciliation.

## Files and authority boundary

- Four isolated low-density Memory Geometry profiles: C4/C6/R4/R6; not substitutes for existing C8/R8 medium-density geometry.
- `stm32f1-low-density-flash-v0.json`: low-density `0x412`, 16/32 KiB, 1-KiB page, halfword writes, fail-closed programming safety constraints. All operations remain unqualified.
- `stm32f103-low-density-exact-12-applicability-v1.json`: 12 exact Catalog-locked candidate identities, package/geometry and safe TR source identity.
- `openocd-0.12.0-stm32f103-low-density-12-v1.json`: 12 CANDIDATE records, **0 SUPPORTED**, 0 operations qualified.
- `openocd-0.12.0-stm32f103-v10.json`: proposed additive envelope, byte-lock of v9; retains authoritative 77 L2, does **not** become active provider registry.
- `plasma_web/stm32f103_low_density_candidate.py`: read-only fail-closed integrity auditor. It is **not** a provider and has no execution/mutation path.

The existing provider registry stays on v9 and the existing 77 exact ICPNs. Canonical Product Catalog and NXP/Microchip statuses are unchanged.

## Safety requirements for a future reviewed admission

1. Acquire **original official DS5936 PDF bytes** and pin verified SHA-256 / size; verify authoritative package, A internal-code, and TR compatibility per exact row.
2. Review the four exact Geometry Profiles, low-density `0x412` operation contract, and program/erase/read/verify source for the *same* OpenOCD commit; retain source-blob evidence.
3. Flash size register `0x1FFFF7E0` may fail or read `0`/`0xFFFF`. The driver falls back to maximum **32 KiB**, including for 16-KiB parts. Treat fallback, manual `FLASH_SIZE` override, invalid Device ID/revision, out-of-range address, protection ambiguity and read/verify mismatch as unsafe, **never** positive geometry evidence.
4. OpenOCD `stm32x_erase()` redirects a full-bank range into `stm32x_mass_erase()`; disallow full-bank erase until a separate execution safety review, even if explicit `mass_erase` command is denied. Option-byte write, RDP unlock, security mutation are excluded.
5. Extend the existing `OpenOCDSoftwareQualificationRegistry` **only after** all required evidence is pinned, with separate positive/negative qualification tests. Any missing evidence leaves exact ICPN at L1 and software state UNKNOWN in the current registry. No runtime or physical claims flow from source-only qualification.
6. If independently qualified in a future approved commit, baseline would become ST L1=4437 / L2=89 / L3=0, but this branch **does not** enact that projected state.

## Acceptance

Existing `.github/workflows/openocd-software-qualification.yml` runs the new regression alongside v9 and Programming Qualification tests. New tests verify exact 12, the three exclusions, legacy 77, link/blob integrity, 16/32-KiB geometry, TR inheritance, fail-closed source custody, wrong device ID, unsafe full-bank erase and no premature support claim.

**Note:** tests that correctly reject unsafe states do not substitute for positive DS5936 original-source attestation. Gate 2 readiness remains **BLOCKED** for 12-item L2 promotion until genuine source/qualification evidence is available.

Prior overlapping ST normalization PRs [#932](https://github.com/physicslu/plasma/pull/932) and [#934](https://github.com/physicslu/plasma/pull/934) were reviewed for overlapping provider/tests; neither branch was merged or inherited. Current `main` was used as the implementation baseline.
