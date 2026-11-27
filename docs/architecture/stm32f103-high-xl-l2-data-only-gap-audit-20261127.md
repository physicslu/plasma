# STM32F103 High/XL-density L1→L2 data-only gap audit (2026-11-27)

**Baseline:** `46697ed33c86799fee4a424422474cd67abab3e3` (`origin/main`, merged #1542). **Outcome:** 0 new L2; 20 XL-density exact ICPNs BLOCKED at L1; 43 High-density exact ICPNs already L3. This is documentary/software evidence, not HIL, Runtime authority, or a live Catalog publication. ADR-0002 and the existing #1542 Publisher remain the authority.

## Canonical inventory and disposition

The source is `data/device-catalog/production/icpn-v1-manifest.json` → source-locked `data/device-catalog/research/stm32f1-commercial-icpn.csv`, loaded through `get_default_programming_qualification_registry()` at the baseline. Counts use actual canonical rows and their current qualification, not generated ordering permutations. Every listed record has STMicroelectronics identity and `tcl/target/stm32f1x.cfg` route. High-density's reviewed source-locked qualification is `release/openocd-qualification/openocd-0.12.0-stm32f103-high-rvz-package-v4.json`; exact package scope is bounded to the existing R/V/Z LQFP applicability. No High record is eligible for L1→L2, and its L3 provenance must remain unchanged.

| Cohort | Canonical exact ICPNs | Current → result |
| --- | --- | --- |
| C, 256 KiB | STM32F103RCT6, RCT6TR, RCT7, RCT7TR, RCY6TR, VCH6, VCT6, VCT6TR, ZCH6, ZCT6, ZCT6TR, ZCT7, ZCT7TR (all prefixed STM32F103) | 13 L3 → 13 L3 |
| D, 384 KiB | STM32F103RDT6, RDT6TR, RDY6TR, VDH6, VDH6TR, VDT6, VDT6TR, VDT7, VDT7TR, ZDH6, ZDH6TR, ZDT6 (all prefixed STM32F103) | 12 L3 → 12 L3 |
| E, 512 KiB | STM32F103RET6, RET6TR, RET7, REY6TR, VEH6, VEH6TR, VEH7, VET6, VET6TR, VET7, VET7TR, ZEH6, ZEH6TR, ZEH7, ZEH7TR, ZET6, ZET6TR, ZET7 (all prefixed STM32F103) | 18 L3 → 18 L3 |
| F, 768 KiB | STM32F103RFT6, RFT6TR, VFT6, VFT6TR, VFT7, ZFH6, ZFH6TR, ZFT6 (all prefixed STM32F103) | 8 L1 → 8 L1 BLOCKED |
| G, 1024 KiB | STM32F103RGT6, RGT6TR, RGT7, VGT6, VGT6TR, VGT7, VGT7TR, ZGH6, ZGH6TR, ZGH7, ZGT6, ZGT6TR (all prefixed STM32F103) | 12 L1 → 12 L1 BLOCKED |

The three unresolved Low-density `STM32F103T4U6A`, `STM32F103T6U6A`, `STM32F103T6U7A` remain unchanged. No L0, L2, or L3 row was promoted or duplicated.

## Source custody and applicability

Official source URLs were read on 2026-11-27 (Asia/Taipei). Browser retrieval provided document text, not original PDF bytes; **original-byte SHA-256 and byte length are NOT_ATTESTED** for this audit. Existing repository source locks are separate, pre-existing evidence; do not interpret a JSON digest as a newly acquired PDF digest.

| Source | Revision / applicability and references | Custody |
| --- | --- | --- |
| [DS5792](https://www.st.com/resource/en/datasheet/stm32f103rc.pdf) | Rev 13; C/D/E High-density, ordering information, device summary, electrical range. Existing ordering and Profile evidence covers the 43 listed LQFP parts. | Prior source-locked review; PDF bytes NOT_ATTESTED here. |
| [PM0075](https://www.st.com/resource/en/programming_manual/pm0075-stm32f10xxx-flash-memory-microcontrollers-stmicroelectronics.pdf) | Rev 2; High-density Flash organization and programming. Existing `stm32f103-high-density/programming-review-v3.json` locks its source digest. Does not establish XL Bank 2. | Reused prior lock; no new PDF acquisition. |
| [STM32F103xF/G datasheet](https://www.st.com/resource/en/datasheet/stm32f103zg.pdf) | DocID16554 Rev 4; F/G 768 KiB/1 MiB, SWD, 2.0–3.6 V, LQFP64/100/144 and LFBGA144 package definitions, ordering table. Canonical rows here are R/V/Z LQFP. | PDF bytes NOT_ATTESTED. |
| [PM0068](https://www.st.com/resource/en/programming_manual/pm0068-stm32f10xxx-xldensity-flash-programming-stmicroelectronics.pdf) | Doc ID 17100 Rev 2; XL only. §§1.1–1.3 and Table 1: Bank 1 fixed 512 KiB `0x08000000–0x0807ffff`, Bank 2 up to 512 KiB beginning `0x08080000`, 2 KiB pages; separate control registers. | PDF bytes NOT_ATTESTED. |
| [RM0008](https://www.st.com/resource/en/reference_manual/cd00171190-stm32f101xx-stm32f102xx-and-stm32f103xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf) | Common F103 register/debug reference; XL Flash details defer to PM0068. Revision and original bytes NOT_ATTESTED here. | Reference only. |
| [ES0340](https://www.st.com/resource/en/errata_sheet/es0340-stm32f101xcde-and-stm32f103xcde-device-errata-stmicroelectronics.pdf) / [ES0346](https://www.st.com/resource/en/errata_sheet/es0346-stm32f101xfg-and-stm32f103xfg-xldensity-device-errata-stmicroelectronics.pdf) | High Rev 17 / XL Rev 7. ES0346 identifies Rev 1/A limitations including Flash BSY/STRT and RDP; exact silicon revision is not encoded by commercial ICPN. | Reference only; bytes NOT_ATTESTED. |

## Pinned Provider and representation gap

[OpenOCD `stm32f1x.cfg`](https://github.com/openocd-org/openocd/blob/9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c/tcl/target/stm32f1x.cfg) and [`stm32f1x.c`](https://github.com/openocd-org/openocd/blob/9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c/src/flash/nor/stm32f1x.c) were read at the locked 0.12.0 commit. Their Git blob IDs match `openocd-0.12.0-stm32f1-source-lock-v1.json`. The driver maps `0x414` to 2 KiB High pages and max 512 KiB, and `0x430` to 2 KiB XL pages and max 1024 KiB. It reads flash size at `0x1ffff7e0`; invalid/unreadable size falls back to family maximum, which cannot by itself attest an exact F/G capacity. `0x430` sets dual-bank mode: Bank 1 512 KiB, Bank 2 reported total minus 512 KiB at `0x08080000`, with the second controller register base `0x40022040`. Erase and write select the bank's register base and require a halted target; write is halfword aligned with an asynchronous loader or slow halfword fallback. Read/verify use the OpenOCD flash framework. Protection/option-byte commands operate through Bank 1 and are outside the proposed qualified operation set. A bank-local full-range erase can invoke mass erase, so cross-bank erase semantics need explicit range validation. Rev 1/A errata, invalid-size fallback, protection state, boot option effects, out-of-range and cross-bank transitions need a bounded XL contract.

The exact CFG creates **one** `stm32f1x` bank at `0x08000000`; it does not register Bank 2. The #1542 Publisher's `_validate_data_only_l2` constructs one `flash_geometry` from `main_flash_start`, total size, and page count; its current source-driven group lookup has no qualified XL group, second-bank controller/range representation, or reviewed XL package-route authority. A hypothetical 768/1024 KiB single-bank Profile would conceal the controller boundary and fail this Gate 1's dual-bank requirement. No new XL Profile, Geometry Profile or `SUPPORTED` record is emitted. A separate, minimal Gate 1 follow-up should add explicit two-bank geometry and qualified two-bank Provider/CFG operations with exact source locks and boundary negatives, then use the same Publisher to publish the 20 eligible L1 records.

## Isolated Publisher observation

On a temporary SQLite DB imported from the exact baseline manifest and registry: baseline and result were **5,885 total; L0 204, L1 5,592, L2 12, L3 77**. `validate_changes` → `stage_revision` → `publish_staged` → repeat publish (idempotent) → `rollback` passed with an unchanged L1 XL row; active digest returned to `4db4ff4c62aaa8c6214d4db27c28660ce8ec96227e0ff321652b5650ef8207a7`. An attempted forged XL L2 `SUPPORTED` row failed `validate_changes` with `L2 lacks exact pinned Provider/Profile evidence`; the active digest remained intact. The 20 XL rows remain `job_selectable=false`. This exercise did not publish a live revision or claim XL L2 support. New qualified ICPNs: High 0, XL 0; blocked 20; reused Programming Profiles 0; new Geometry Profiles 0.

## Verification limits

The baseline import, exact-cohort inventory, unchanged L1 Stage/Validate/Publish/repeat/Rollback, rejected forged XL L2, unchanged total/level counts, and unchanged active digest after rejection were observed with the merged Publisher. Existing Python regression suite was **NOT_RUN** in this checkout because `python3 -m pytest` fails with `No module named pytest`; no package installation or live service was used. The other requested L2 negative variants are **NOT_RUN** for XL because no truthful XL `SUPPORTED` qualification exists to mutate; #1542's existing publisher regression tests cover its admitted medium-density fixture and remain the appropriate code regression. No hardware or physical OpenOCD programming was run.
