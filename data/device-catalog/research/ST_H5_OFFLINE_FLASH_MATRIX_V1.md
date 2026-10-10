# STM32H5 — 190 Exact ICPN Device-ID / Flash Geometry Offline Matrix v1

**2026-10-10. State: research-only; no Production backend mapping, no target I/O, no Z2/SWD/PL/electrical qualification, no programming.**

## Decision

The 190 existing, ST-authorized exact STM32H5 orderable MPNs already reside in the Production Catalog with `no_mapping`. The independent ST OpenOCD fork *source* includes an `stm32h5x` Flash Driver and one `stm32h5x.cfg`, but the packaged PLASMA Production OpenOCD upstream 0.12.0 does **not** include that H5 target. Do not promote or enable any of these 190 records in Production.

This work creates **one queryable, deterministic research row per commercial ICPN** from the retained SHA256-verified exact Production CSV and the fixed ST source commit. Expected DBGMCU Device ID is inferred from the *family name and driver database*, **not measured from a device**.

## Source identity

- ST OpenOCD Git repository: `https://github.com/STMicroelectronics/OpenOCD.git`
- Fixed commit: `c8d973bdad9a6fddb51459eda109b3b95d23b57a`
- Flash driver: `src/flash/nor/stm32h5x.c` Git blob `b5f24a39da05e5235167ff91c110ed89c2e3f9c5`
- Driver header: `src/flash/nor/stm32h5x.h` Git blob `980ed4673939dd31b14efc74941bbcb10ddbe7ed`
- Target Tcl configuration: `tcl/target/stm32h5x.cfg` Git blob `b9e67c604f7d824fefca03b42d0b112e1785235a`
- Current authoritative exact identities and Flash sizes: `data/device-catalog/research/stm32h5-commercial-icpn.csv`, content SHA256 bound by `data/device-catalog/production/icpn-v1-manifest.json`.
- Machine-readable reviewed source facts: `st-h5-offline-flash-matrix-v1.json`.

The reviewed facts are a **summary**, not a vendored source-code copy. Source revision and file blob identities must match existing `st-h5-c5-runtime-gap-v1.json`; if not, the offline validator fails closed. The CI does not fetch/compile vendor source or upload binaries.

## Five ST driver device groups

| Driver group | Expected low 12-bit DBGMCU ID | Exact ICPNs | Family series | Driver max Flash | TrustZone flagged | WPS sectors/group |
| --- | --- | ---: | --- | ---: | --- | ---: |
| STM32H50xx | `0x474` | **14** | H503 | 128 KiB | No | 1 |
| STM32H52/H53xx | `0x478` | **53** | H523, H533 | 512 KiB | Yes | 4 |
| STM32H54/H55xx | `0x47C` | **6** | H543, H553 | 1024 KiB | Yes | 4 |
| STM32H56/H57xx | `0x484` | **82** | H562, H563, H573 | 2048 KiB | Yes | 4 |
| STM32H5E/H5Fxx | `0x47A` | **35** | H5E4, H5E5, H5F4, H5F5 | 4096 KiB | Yes | 4 |
| **Total** | **5 device ID groups** | **190** | **12 series** | | | |

Pinned code specifies `DBGMCU_IDCODE=0x44024000` and applies `idcode & 0xFFF` for driver-group selection. The flash base is `0x08000000`; `0x0C000000` is an alternative secure alias, **not** evidence that the current security configuration allows access. All five driver cases currently select 8 KiB sectors and dual-bank geometry, with 16-byte Flash write alignment. Write-protection group unit is 1 or 4 sectors as indicated. The actual memory layout, protection and security state require safe probe evidence.

### Important driver risk: Flash-size fallback

The pinned `stm32h5x.c` driver reads a 16-bit Flash size at `0x08FFF80C`. If that read fails, or the value is zero, `0xFFFF`, or above the group maximum, **the vendor driver substitutes the group's *maximum* size**. Its optional user-size override can also bypass the hardware read.

**PLASMA must never treat that fallback size as confirmed target geometry.** An order code advertising 256 KiB or 3072 KiB can be assigned a larger geometry on an invalid read. In a future real hardware runtime, mismatches, unreadable IDs, inaccessible security state or missing option-byte evidence must be explicitly rejected before any erase/program/verify. Never perform erase or mass erase to discover geometry.

The JSONL `estimated_sector_count_if_catalog_size_confirmed`, `estimated_per_bank_sectors_if_confirmed` and `estimated_protection_blocks_if_confirmed` are arithmetic estimates based on *declared* official catalog size and *source-reviewed driver sector properties*. They are **not readback or physical validation**. Every row retains `actual_silicon_device_id=null`, `actual_flash_size_register_kib=null`, `programming_write_authorized=false`, `hardware_runtime_ready=false`, and `production_mapping_status=no_mapping`.

The ST Tcl file also contains security/provisioning commands (option writes, OBK, irreversible lock/state transitions). This offline evidence grants **no** permission to call these commands. A future production-safe backend must apply an explicit command allowlist, prohibit security mutations and fail closed when security state is ambiguous.

## Reproduce (no hardware)

At repository root:

```bash
python data/device-catalog/research/validate_st_h5_offline_flash_matrix_v1.py
python data/device-catalog/research/validate_st_h5_offline_flash_matrix_v1.py --icpn STM32H503CBT6
python data/device-catalog/research/validate_st_h5_offline_flash_matrix_v1.py --icpn STM32H5E4IKT6
python data/device-catalog/research/validate_st_h5_offline_flash_matrix_v1.py --output-dir /tmp/st-h5-offline-matrix
python -m unittest discover -s data/device-catalog/research -p test_validate_st_h5_offline_flash_matrix_v1.py -v
```

The output is a **190-row sorted JSONL** plus SHA256-bound summary. CI runs the same deterministic verifier and negative tests and publishes metadata-only evidence to GitHub Actions. Existing Production manifest and exact ICPN CSV remain unchanged.

## Next gates and residual gap

The original unbound ST ICPN count remains **465** (H5 **190**, C5 **172**, WL3 **47**, N6 **32**, WB0 **24**). This research **reduces uncertainty about H5 source capabilities but does not reduce the no_mapping count**.

Next software-only priority: document and protect future read-only IDCODE/Flash-size comparison against the vendor fallback, prove option/state sensitive commands are denied by an isolated adapter, and qualify actual Flash-driver invocation only in an explicitly approved hardware phase. A physical DUT must validate the exact expected 12-bit device group, real Flash size, bank geometry, security state and per-Site electrical limits before any programming transaction. Host/ARMv7-QEMU compilation of the ST fork (prior PRs #793/#796) is separate software evidence, not an H5 target measurement.
