# STM32F103 medium-density non-LQFP L1→L2 — bounded Gate 1 admission v1

Status: source-only software Provider qualification candidate; Draft PR / **not merged**.
Authority: ADR-0002 canonical ProgrammingQualificationRegistry. This is **not**
a physical device, Socket/HIL, installed OpenOCD or execution qualification.

## Fixed manufacturer/provider source

- ST **DS5319 Rev 20**, product datasheet `https://www.st.com/resource/en/datasheet/stm32f103c8.pdf`:
  Table 1 x8/xB summary, Table 2 package-by-pin-count matrix, Table 5
  package-specific signals, Section 7 exact ordering grammar and `TR` packing
  distinction. Source bytes are SHA256 pinned as `st_ds5319_rev20` in
  `data/ic-support/benchmarks/stm32f103c/source-lock.json`.
- ST **PM0075 Rev 2** manufacturer programming facts, source-byte pinned in
  the retained `stm32f103c` manufacturer-only admission contract.
- OpenOCD `v0.12.0` source commit
  `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`, target
  `tcl/target/stm32f1x.cfg` and `src/flash/nor/stm32f1x.c`,
  via the pre-existing locked source. `0x410` medium-density probe, 1-KiB
  page erase, 2-byte write alignment and software read/verify are inherited
  only from the previously reviewed medium-density Programming Group.
- Existing **65 reviewed ST L2** records remain byte-for-byte authoritative;
  new v9 admission manifest pins original v8 bytes and the new exact cohort.

## Exact 12 ICPNs (8 direct + 4 packaging-only TR)

| Package | Direct exact ICPNs | Packing-only exact ICPNs | Count |
| --- | --- | --- | ---: |
| UFQFPN48 | STM32F103CBU6 | STM32F103CBU6TR | 2 |
| TFBGA64 | STM32F103R8H6, STM32F103R8H7, STM32F103RBH6, STM32F103RBH7 | STM32F103R8H6TR, STM32F103RBH6TR | 6 |
| LFBGA100 | STM32F103V8H6, STM32F103VBH6, STM32F103VBH7 | STM32F103V8H6TR | 4 |

Independent exact-base geometry locks reuse existing ST DS5319+PM0075
documented profiles for `CB` (128 KiB / 128 × 1 KiB), `R8` and `V8`
(64 KiB / 64 × 1 KiB), and `RB` / `VB` (128 KiB / 128 × 1 KiB).
A package does not establish capacity by itself. Each direct ICPN binds
source-locked geometry, exact manufacturer Production identity and package.
Every TR variant requires the independently admitted non-TR exact identity,
matching all non-packing Catalog fields and complete operation equivalence.
TR does **not** imply silicon revision equivalence.

## The 19 reviewed: seven hard-blocked VFQFPN36 (no promotion)

- `STM32F103T8U6`, `STM32F103T8U6TR`,
  `STM32F103T8U7`, `STM32F103T8U7TR`,
  `STM32F103TBU6`, `STM32F103TBU6TR`,
  `STM32F103TBU7`.

For T-pin 36, DS5319 Rev 20 Table 2 says **VFQFPN36**, while current
Production `stm32f1-commercial-icpn.csv` uses `UFQFPN` for these exact
ICPNs. Treat this as an explicit source/normalization mismatch, not an
implicit synonym. `STM32F103T8` and `STM32F103TB` also lack independent
exact-base Flash geometry Profiles. Preserve L1 until a separately reviewed
manufacturer field reconciliation and two geometry admissions are completed.

Two additional earlier exclusions `STM32F103RBH6R` and
`STM32F103RBH6RTR` are outside the 19; `R` is customer-dedicated under
DS5319 Rev 20 Section 7 and cannot be inherited as ordinary TR packaging.

## Fail-closed test and product boundary

- New v9 manifest pins legacy v8 **65** and additive exact **12** SHA-locked
  source-only records. No changes to Production exact identity, 65 historical
  software records, OpenOCD release, PL or Socket.
- Mandatory test checks all 12, package/temperature/geometry matches, locked
  source digests and the nine explicit exclusions; invalid exact ICPN, altered
  source bytes, geometry, TR inheritance and false HIL/authority claims must
  fail closed.
- If merged in separate Gate 2, canonical read-only taxonomy would become
  ST L1=4,449 / L2=77 / L3=0; this **does not** authorize firmware execution.
  Before Gate 2, current main remains ST L1=4,461 / L2=65 / L3=0.
- No SWPC, Z2, DUT, physical flash, installed runtime, deployment or
  other PR merge is authorized by this Gate 1.

Testing: `python -m pytest -q software/python/tests/test_openocd_software_qualification_v1.py software/python/tests/test_catalog_promotion_framework.py`,
plus all required GitHub-hosted CI on the Draft PR fixed HEAD.
