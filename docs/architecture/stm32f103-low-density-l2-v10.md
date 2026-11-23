# STM32F103 Low-density 12 exact ICPNs — L1→L2 documentary qualification (v10)

**Status:** 12 exact ICPNs are `SUPPORTED` in the Draft PR's versioned OpenOCD ProgrammingQualification, on top of the previously supported 77; **PR remains Draft**, unmerged and undeployed. No physical programming, hardware HIL, installation or Job execution grant is claimed.

## Qualification policy and evidence

ADR-0002 defines **L2 PROGRAMMABLE** as L1 Exact ICPN with a pinned Programming Provider recording `SUPPORTED` for that exact part. It does **not** require buying samples, real Flash/HIL PASS, or custody of original manufacturer PDF bytes. L3 remains physical compatibility verification.

- **ST manufacturer:** [DS5936 / DocID15060 Rev 7, June 2015](https://www.st.com/resource/en/datasheet/stm32f103c6.pdf), Table 1 (C4/C6/R4/R6 scope), Table 2 (packages and memory), Section 3 (pin/package), Table 58 p.95 (ordering code, grade, internal A code and TR tape-and-reel). This provides the documentary ordering and identity basis, together with locked canonical Exact ICPN research.
- **ST Flash methodology:** PM0075 Rev 2, pinned in `data/ic-support/benchmarks/stm32f103c/source-lock.json`; 0x08000000 Flash base; page erase 1 KiB; halfword (2-byte) programming. The four distinct 16/32 KiB memory geometry profiles are linked to the respective Base Device.
- **Provider:** OpenOCD 0.12.0 at commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`, `tcl/target/stm32f1x.cfg`, `src/flash/nor/stm32f1x.c`, low-density device ID `0x412` (not `0x410`). Reviewed operations: probe, erase, program, read, verify.
- **Raw PDF custody:** Original DS5936 PDF bytes were not archived by the previous process; its `sha256`/`byte_length` remain `null`, and `original_bytes_attested=false` / `NOT_ATTESTED`. This is **not** represented as a falsely verified checksum and is **not** treated as a universal L2 gate.

## Exact L2 entries on this Draft PR

| Base | Exact ICPNs | Geometry |
| --- | --- | --- |
| STM32F103C4 | `STM32F103C4T6A` | 16 KiB, 16 × 1 KiB pages |
| STM32F103C6 | `STM32F103C6T6A`, `STM32F103C6T6ATR`, `STM32F103C6T7A`, `STM32F103C6T7ATR`, `STM32F103C6U6A` | 32 KiB, 32 × 1 KiB pages |
| STM32F103R4 | `STM32F103R4H6A`, `STM32F103R4T6A` | 16 KiB, 16 × 1 KiB pages |
| STM32F103R6 | `STM32F103R6H6A`, `STM32F103R6T6A`, `STM32F103R6T6ATR`, `STM32F103R6T7A` | 32 KiB, 32 × 1 KiB pages |

The three ambiguous T-pin / VFQFPN36 vs canonical UFQFPN entries remain **L1 / UNKNOWN**: `STM32F103T4U6A`, `STM32F103T6U6A`, `STM32F103T6U7A`. No family-prefix bulk promotion is permitted.

## Implementation and safety

- The existing `OpenOCDSoftwareQualificationRegistry` composes the original 77 v9 records and exactly 12 reviewed low-density v10 records (89 unique Exact ICPNs). The shared `ProgrammingQualificationRegistry` projects 12 new L2 exact ICPNs and retains the previous 77 at L3; no duplicate manufacturer-specific Product API or separate provider was created.
- The new `plasma_web/stm32f103_low_density_candidate.py` is a **read-only evidence validator**. It checks source locks, exact package/temperature/TR mapping, flash geometry, provider Device ID, operation scopes and original v9 authority, failing closed on mismatch.
- The OpenOCD driver may fall back to a **32 KiB** maximum if the Flash size register read fails. This is **not** proof of actual 16/32 KiB capacity; any ambiguous or inconsistent size must be rejected at runtime. Manual geometry override must not bypass evidence.
- Full-bank erase can enter OpenOCD mass-erase behavior; full-bank/mass erase, option-byte mutation and protection unlock remain blocked pending distinct execution safety controls. L2 does not authorize such side effects.
- `SUPPORTED` / `job_selectable` is **not execution_authorized**. Installed Runtime, per-Site route, voltage/protection and hardware safety remain independent gates. The newly qualified 12 low-density ICPNs remain `NOT_TESTED` for HIL/L3; the original 77 F103 L3 records remain unchanged.

## Validation and Gate 2 boundary

- Source restoration performed on PR #1147 by the authorized Path 3 deterministic helper; it verified patch and module SHA256, 17 original Git blobs and `git apply --check`, then ran Python compile plus existing/low-density/negative/Catalog-Promotion Host-only test suites before deleting temporary recovery files.
- Source-pinned qualification artifacts: `release/openocd-qualification/openocd-0.12.0-stm32f103-low-density-12-v1.json`, `openocd-0.12.0-stm32f103-v10.json` and exact applicability/source-lock files.
- The draft PR must receive current-HEAD hosted CI verification and a Gate 2 review before merge. Successful software qualification **does not** imply real DUT Flash PASS, a working physical socket, or approval to program.
