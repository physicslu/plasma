# STM32H5 host-only synthetic readback guard v1

**Research-only, no Z2 / FPGA / SWD / real silicon / deployed binary / programming.**

## Objective

The pinned ST `stm32h5x` driver may substitute the **driver group's maximum Flash size** if its Flash-size register read fails, returns zero, returns `0xFFFF`, or exceeds the group maximum. The existing 190-IC static matrix is not hardware readback. This guard formalizes a fail-closed *host test model* for a future read-only observation contract.

## Implemented

- Exactly 190 Production-admitted STM32H5 orderable identities, all **no_mapping**, are looked up through the immutable Production Catalog and existing source-locked Backend Candidate Registry.
- The model only accepts **host-supplied synthetic** `idcode` and 16-bit Flash-size values with explicit independent `ok` read states and `direct_register` origin. It checks low 12 DBGMCU ID bits against the exact ICPN's pinned driver group, and verifies Flash size equals the official catalog size, is sector-aligned and within the group maximum.
- Failed, unknown, invalid, fallback, manually overridden, mismatched, or absent reads are **blocked**, even if a fallback numerically matches an SKU's official size (e.g., H503 128 KiB).
- All 190 synthetically matching cases and negative cases are tested. A 3072 KiB H5E4 example must not accept the 4096 KiB group maximum.
- The model cannot create OpenOCD commands, talk to an adapter or modify Production mappings. Every result explicitly has `physical_readback_verified=false`, `hardware_runtime_ready=false`, `production_write_authorized=false`, `executable=false`, `security_state_verified=false` and no hardware operations.

**Important:** `synthetic_consistent` is NOT a verified silicon result. It only says that caller-supplied test integers agree with pinned metadata. Never use it as a Programming Profile, Job/Batch admission, flash-plan authorization or security state attestation.

This work does not change the ST vendor driver itself. Its fallback behavior remains a risk requiring a separately implemented runtime pre-operation guard if a hardware integration is later authorized. A successful host model does **not** prove any security/TrustZone state or supported erase/program sequence.

## Reproduce without hardware

```bash
python -m pip install -e software/python
python scripts/ci/device-catalog-production-invariants.py
python -m unittest discover -s software/python/tests -p 'test_h5_host_readback_guard_v1.py' -v
```

The dedicated GitHub Actions workflow runs these checks without fetching vendor binaries or touching any Z2/PPU.

## Later gates (not claimed)

Authentic read-only sample provenance, installed OpenOCD binary/ABI/target transport identity, robust security-state handling, actual silicon ID/Flash readback and protection policy, full Site electrical verification, and erase/program/verify qualification all remain **unverified**. Exact-ICPN Production routing needs separate approval. ST baseline remains **4,164 mapped / 465 no_mapping**.
