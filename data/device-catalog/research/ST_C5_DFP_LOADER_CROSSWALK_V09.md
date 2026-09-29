# STM32C5 DFP / Loader Source Crosswalk v0.9

**Reference date:** 2026-09-29 · Research-only · No Production Catalog modification.

## Material finding

The pinned official [STM32C5xx DFP](https://github.com/STMicroelectronics/stm32c5xx-dfp/tree/a5f65bc64535cfa723e9d25f58d7ce23d0937aed) (pack v2.1.0, dated 2026-05-04) contains **three actual** `.xldr` on-chip flash algorithm files. Its `STMicroelectronics.stm32c5xx_dfp.pdsc` (blob `859649be212ea43bc524eb977e1279e45da644c8`) declares **80 Base Devices and 157 exact Dvariant records**, with an explicit loader algorithm for each parent.

### Official pinned loader source mapping

| STM32C5 series | DFP family DEV_ID reference | PDSC algorithm | Git blob SHA |
| --- | --- | --- | --- |
| C53, C54 | `0x44F` | `Flash/STM32C5[34]x.xldr` | `ef1d74c6c9cbc7cfe992be476897f621512154a0` |
| C55, C56 | `0x44E` | `Flash/STM32C5[56]x.xldr` | `c8f1dfbd183477f79db8fc8174d5d08d3b2fbdb7` |
| C59, C5A | `0x45A` | `Flash/STM32C5[9A]x.xldr` | `9b5326edebbed8f7ade21029d6d014aa56d66bba` |

## Verified source-byte SHA256 (research-only)

The PR's first pinned upstream source replay (GitHub Actions run [36540249563](https://github.com/physicslu/plasma/actions/runs/36540249563)) independently fetched all three official fixed-commit `.xldr` files and verified their original Git blob identity plus ELF32 little-endian signatures. Their SHA256 are now frozen in the v0.9 JSON report and checked on every source replay:

| Official file | SHA256 |
| --- | --- |
| `STM32C5[34]x.xldr` | `4645574f274f5274de869dbd2a6b35fd79d134f7ec07224c3f17ed2d40c7b8b6` |
| `STM32C5[56]x.xldr` | `131784c2e4eb4589200b614e56b83abd21a34906c1fd485ca3d806378d28732d` |
| `STM32C5[9A]x.xldr` | `b9aacec837613f273b0d88fb3ca41c5c52712752fd26271959dd03a41dab8e53` |

The upstream binaries are **not copied into Plasma** and have **not** been run against a physical chip. Successful ELF/source integrity replay proves neither legal production redistribution nor a compatible compiled runtime programming backend.

The DFP declares `<license>LICENSE.md</license>`; the pinned license file Git blob `f404bd9d1021334ecfbbb82da1ee4bbe68a82173` carries a BSD-3-Clause license. Packaging/redistribution and any third-party component obligations **still require independent review** before shipping binaries with Plasma. No `.xldr` binary is copied into the Production repository in this PR.

### Exact commercial to DFP variant reconciliation

Compare the **172 distinct C5 public eStore same-card Active exact MPNs** from v0.7 to the separately dated DFP 2.1.0. The source-derived CSV `st-c5-dfp-commercial-loader-crosswalk-v0.9.csv` records all 172 MPNs, without changing the exact set.

| Group | eStore observed | Exact DFP Dvariant match | Base-device-only; exact variant absent |
| --- | ---: | ---: | ---: |
| C53 | 51 | 39 | 12 |
| C54 | 12 | 9 | 3 |
| C55 | 48 | 36 | 12 |
| C56 | 12 | 10 | 2 |
| C59 | 39 | 35 | 4 |
| C5A | 10 | 10 | 0 |
| **Total** | **172** | **139** | **33** |

For the 33 unmatched exact retail codes, the official DFP matches **one unique Base Device** but not an exact `Dvariant`. Parent flash/loader information is retained solely as a structural research lead. The exact-variant flash value stays blank and Plasma route readiness stays false. **Do not invent** matching temperature, packing/TR, flash, security, or silicon-specific facts by expanding a DFP pattern.

The eStore research acquisition is dated 2026-09-29 and the pinned DFP release is 2026-05-04. Absence from the earlier DFP must never turn an officially observed retail part into NRND or Obsolete.

### Important fork vs patch distinction

The previously pinned [ST OpenOCD fork](https://github.com/STMicroelectronics/OpenOCD/blob/c8d973bdad9a6fddb51459eda109b3b95d23b57a/tcl/target/stm32c5x.cfg) holds `set dev_id_loader { }` and `set die_max_flash_size { ... }` as **Tcl scalar lists**, yet later tests both with `info exists var($dev_id)`, the syntax for a Tcl array. A host-only `tclsh` test demonstrates that the original scalar definition cannot satisfy the indexed lookup. This is a distinct blocker in addition to the empty loader mapping. Its fallback flash-size path is affected when the flash-size register yields an invalid value.

The publicly posted [upstream OpenOCD C5 patch #9699](https://review.openocd.org/c/openocd/+/9699) proposes an `array set dev_id_loader` with three URLs pointing to the pinned official DFP loader sources. **Do not infer the upstream patch is merged, the full fallback is fixed, or the Plasma backend has been built/qualified.** The posted patch's loader downloading path must not be adopted as an implicit runtime network dependency: Plasma factory operation needs independently approved, locally staged, hash-pinned loaders.

### Reproduction

The offline validator crosschecks v0.7's frozen exact C5 set and original 23 ST Production sources; every candidate is explicitly `plasma_route_ready=false`.

```bash
python data/device-catalog/research/validate_st_c5_dfp_loader_crosswalk_v09.py
python -m unittest discover -s data/device-catalog/research -p test_validate_st_c5_dfp_loader_crosswalk_v09.py -v
tclsh data/device-catalog/research/test_c5_scalar_array_v09.tcl
```

For full independent source replay, supply original files from the **exact pinned manufacturer commit**, never a moving branch:

```bash
python data/device-catalog/research/validate_st_c5_dfp_loader_crosswalk_v09.py \
  --pdsc /path/to/STMicroelectronics.stm32c5xx_dfp.pdsc \
  --loader-dir /path/to/pinned/Flash/ \
  --license /path/to/pinned/LICENSE.md \
  --fork-cfg /path/to/pinned/stm32c5x.cfg
```

The PR's separate official-source replay job fetches these read-only fixed-commit bytes and verifies Git blob IDs and expected ELF32 signatures. No physical Flash erase/write, target debug attachment, loader execution, runtime dependency promotion, production publication or license signoff is claimed.

**Next gate:** independently review licence/distribution, reconcile the 33 exact DFP-absent variants, then qualify a corrected local-only OpenOCD loader route on Plasma PS and later HIL. ST Production stays **2,683 exact ICPNs / 23 families** pending a separately approved ICPN publication PR.
