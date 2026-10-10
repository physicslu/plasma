# Exact ICPN OpenOCD Backend Source Provenance — v1

**Scope: source attribution and deterministic audit only.** No Production Catalog CSV/manifest mutations; no programming backend promotion, PPU deployment, FPGA, Z2 or real-silicon operations.

## What is actually authoritative?

The exact commercial ICPN, Catalog mapping and vendor-identity source remain authoritative in `data/device-catalog/production/icpn-v1-manifest.json` and its SHA256/Git-blob-locked admitted CSV rows.

Backend *mapping source provenance* is a **read-only join**, not a new device catalog:

1. A currently mapped exact ICPN has `openocd_target_config` from its immutable admitted CSV and is attributed to the **pinned upstream runtime source** declared in `release/openocd.json`: `openocd-org/openocd` version 0.12.0, commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`.
2. An ICPN with `no_mapping` has **no Production OpenOCD provider**. In particular, it must not inherit the upstream distribution merely because the product uses upstream OpenOCD by default.
3. The existing SHA-bound research report `data/device-catalog/research/st-h5-c5-runtime-gap-v1.json` supplies two distinct, **unpromoted research candidates** from `STMicroelectronics/OpenOCD` commit `c8d973bdad9a6fddb51459eda109b3b95d23b57a`:
   - STM32H5: `tcl/target/stm32h5x.cfg`, native `stm32h5x` Flash driver, source Git blob SHAs. Host and QEMU-ARMv7 software-only evidence exists.
   - STM32C5: `tcl/target/stm32c5x.cfg` and `stldr` driver, Git blob SHAs. Known loader table/Tcl/RAM gaps remain; static source research only.
4. STM32N6, STM32WB0 and STM32WL3 have **no attributed Production provider or pinned ST research candidate** under this v1 authority. Do not fabricate one.

The audit does **not** equate the ST vendor identity's datasheet URL (`identity_evidence_reference`) with the OpenOCD repository (`production_binding.source_repository`). A catalog route is not device programming validation.

## Exact-record contract

Each of the 4,629 Production exact ICPNs is deterministically represented by one schema-v1 JSON line, with keys such as:

```json
{
  "icpn": "STM32H503CBT6",
  "family": "STM32H5",
  "mapping_status": "no_mapping",
  "production_binding": {
    "provider_id": null,
    "source_distribution": null,
    "source_commit": null,
    "target_config": null,
    "flash_driver": null,
    "hardware_runtime_ready": false
  },
  "research_candidate": {
    "status": "research_only_not_production_mapped",
    "provider_id": "openocd-st-h5-research",
    "source_distribution": "STMicroelectronics/OpenOCD",
    "source_commit": "c8d973bdad9a6fddb51459eda109b3b95d23b57a",
    "target_config": "tcl/target/stm32h5x.cfg",
    "flash_driver": "stm32h5x",
    "production_binding_authorized": false
  },
  "installed_runtime": {
    "runtime_id": null,
    "binary_sha256": null,
    "artifact_sha256": null,
    "status": "not_attested_by_catalog"
  },
  "physical_programming_qualified": false
}
```

This example shows a subset of the actual fields. The CLI generates the complete record. For a mapped STM32F3, `production_binding` instead has provider `openocd-upstream`, upstream source repository/commit/runtime_id and the exact target CFG from Production. A per-IC `flash_driver` or per-target config blob SHA is **null unless independently evidenced**—do not infer it from the target config name. Actual installed PPU ELF/runtime artifact hashes are likewise **unknown** in the Catalog; provenance of source is not attestation of deployment.

## Reproduce and query

At the repository root, with Python 3.11+ available:

```bash
PYTHONPATH=software/python python3 scripts/device-catalog-backend-provenance.py
PYTHONPATH=software/python python3 scripts/device-catalog-backend-provenance.py --icpn STM32F301C6T6
PYTHONPATH=software/python python3 scripts/device-catalog-backend-provenance.py --icpn STM32H503CBT6
PYTHONPATH=software/python python3 scripts/device-catalog-backend-provenance.py --out-dir /tmp/plasma-backend-provenance
PYTHONPATH=software/python python3 -m unittest discover -s software/python/tests -p test_icpn_backend_provenance_v1.py -v
```

The export writes `icpn-backend-provenance-v1.jsonl` and `icpn-backend-provenance-v1-summary.json`. The summary contains `records_jsonl_sha256` binding the **exact deterministic complete 4,629-row output** to its content and current Catalog revision. No manual 4,629-row duplicate table is committed, which would otherwise drift from Production.

The dedicated GitHub Actions workflow `device-catalog-backend-provenance-v1.yml` runs the full audit, baseline regression checks, and negative source-commit tests on PR/main changes; it uploads only the metadata receipts, **no OpenOCD binaries or release artifacts**.

## Qualification bounds and follow-up

Expected v1 partition: Production mapped **4,164** (upstream), Production no_mapping **465** (unbound). ST-source research candidates H5 **190**, C5 **172**. Other blocked families N6 **32**, WB0 **24**, WL3 **47**. These are auditable exact-record facts, not new IC admission.

Future independent work is needed for: (1) independent Flash Driver per-family/per-device evidence on mapped upstream routes; (2) a versioned Backend Provider Capability Registry and runtime selection contract; (3) PPU deployed-artifact attestation and physical/electrical programming qualification. None is implied by this audit.

Production IC source schema, hardware readiness, physical status, release/openocd.json, existing routing, and Production mapping are unchanged.
