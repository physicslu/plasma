# NXP ADR-0002 Phase 2 — KL25 FCF Sector Fail-Closed Correction

**Disposition:** Software Executor safety defect fix for exact `MKL25Z128VLK4`; the 12 KL25 parts remain **Phase 2 `CANDIDATE`**, with **0 new `SUPPORTED`**. This PR is not an operation admission, deployed OpenOCD attestation, physical HIL approval or a change to Production Catalog.

## Finding: old 16-byte guard is insufficient

The existing KL25 compiler invoked `_reject_fcf_intersection` on `PROGRAM`, but blocked payload overlap with the **16-byte** FCF address span `0x00000400–0x0000040F` only. That was not the correct safety boundary for **OpenOCD's `kinetis_write()`**.

The approved OpenOCD 0.12.0 commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c` contains a driver path which, when `allow_fcf_writes` is false, checks **intersection with the entire Flash sector containing FCF**. A write touching that sector can invoke `kinetis_fill_fcf`, compare/synthesize the FCF, and potentially invoke `kinetis_write_inner` on FCF, **even when the requested image itself excludes the 16 FCF bytes**. This behavior was also observed in the historical KL25 Software Executor commit `56b8d93fbe61a78dc903d770820d6d896b6d8134` because the `kinetis_write()` function text is unchanged between the two source versions.

For the frozen exact KL25 geometry, the FCF-containing sector is **`[0x400, 0x800)`**, i.e., 1024 bytes. A payload at `0x410` or `0x7FC` was permitted by the previous PLASMA compiler despite this OpenOCD FCF entry path. That is unacceptable under ADR-0002's security, protected flash and operation-scoped fail-closed requirements.

## Correction to software-only compiler

- Preserve the immutable historic backend lock and Programming Profile ID. **Do not broaden admission.**
- Inside `software/python/plasma_interfaces/kl25_openocd_plan.py`, `_reject_fcf_intersection()` reads the already approved `flash_configuration_field_sector_start` and `flash_configuration_field_sector_size_bytes` directly from the pinned backend lock.
- Validate that this sector has positive size and fully contains the 16-byte FCF; fail closed if inconsistent.
- Reject **any** `PROGRAM` whose half-open payload interval overlaps the entire FCF sector; retain existing alignment, Flash bounds, no-implicit-erase, other safety and fixed-target checks.
- Keep explicit exact-sector `ERASE` at `0x400` rejected as before. Ordinary READ/VERIFY and PROGRAM below `0x400` or from `0x800` onward retain their existing code path, *subject to existing gates*.
- Do not enable FCF source `write`, mass erase, security unprotect, vendor fallback or any bypass.

## Pinned source observations

See `nxp-kl25-fcf-sector-safety-v1.json` for source commit names and Git blobs. Function-level comparison across the two immutable upstream commits found `kinetis_write`, `kinetis_write_inner`, `kinetis_write_sections`, `kinetis_erase` and `kinetis_ftfx_command` byte-for-byte unchanged as extracted function text. `kinetis_probe_chip` differed by local `unsigned int` vs `unsigned` declarations in the inspected function. `kinetis_fill_fcf` **did change**: the approved older release contains `assert(bank_iter->prot_blocks)`, where the prototype revision had explicit diagnostics and early continuation for absent protection blocks. `klx.cfg` also differs in SWD/SWJ transport selection, as documented in merged PR #935.

**Scope boundary:** These are source-level observations of specific functions, not complete version semantic-equivalence certification. The approved OpenOCD source files are identified by immutable Git blob IDs but **not copied into this repository**; a matching function body does not prove installed binary SHA, target silicon ID/revision, flash geometry, electrical compatibility, or successful operations.

## Regression gates

| Test case | Expected behavior |
| --- | --- |
| PROGRAM `[0x400,0x404)` | Denied — direct FCF |
| PROGRAM `[0x410,0x414)` | **Denied — indirect FCF-sector risk** |
| PROGRAM `[0x7FC,0x800)` | **Denied — final sector longword** |
| PROGRAM `[0x3FC,0x404)` | Denied — boundary crossing |
| PROGRAM `[0,0x401)` | Denied — overlap from address zero |
| PROGRAM `[0,0x400)` | Allowed by this specific FCF rule; other gates apply |
| PROGRAM `[0x800,0x804)` | Allowed by this specific FCF rule; other gates apply |
| Corrupt FCF sector geometry | Fail closed |
| Exact `ERASE` 1024 bytes at `0x400` | Remains denied |

Existing installed-wheel KL25 compiler/executor/lock CI is reused and expanded to execute these tests on the actual imported installed Python module, not only repository text.

## Remaining ADR-0002 Phase 2 blockers

Even after this software safety correction, the KL25 exact profile **does not** become `SUPPORTED`. Still pending: approved OpenOCD 0.12.0/commit-specific provider semantic review, SWD/SWJ interface binding, silicon ID and revision, protected-area/flash geometry and FCF/security proof, Erase/Program/Read/Verify operation-specific qualification and reviewed current-version Programming Profile. Phase 3 PPU/Site/Socket HIL is independently `NOT_AUDITED`.

No Production Manifest, IC Selector, Job authorization, OpenOCD release pin, FPGA or PPU changes. Draft PR; owner approval required for merge.
