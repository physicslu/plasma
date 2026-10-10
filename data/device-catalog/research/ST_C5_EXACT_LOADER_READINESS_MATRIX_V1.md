# STM32C5 — 172 exact ICPNs / three STLDR loader-source readiness groups v1

**2026-10-10. Research-only offline audit. No Z2/SWPC deployment, real silicon, OpenOCD execution, vendor binaries, Production backend mapping or Programming Profile promotion.**

## Key correction: 33 absent DFP exact variants are not missing Production metadata

Historical C5 research reports v0.9–v1.1 (2026-09-29) predate merged STM32C5 Layer-1 Production publication v4.4. Today **all 172** official exact C5 commercial MPNs have officially sourced order-code / Flash metadata in Production, still with mapping_status=no_mapping.

A separately pinned official STM32C5 DFP 2.1.0 (commit a5f65bc64535cfa723e9d25f58d7ce23d0937aed) has **139** matching exact Dvariant records; **33** match one Base Device only. The 33 still lack exact DFP algorithm-applicability evidence. Their prior DFP absence does not invalidate current Production identity/metadata, imply lifecycle status, or authorize a programming route.

## Three official loader candidates (not deployed)

| DFP candidate loader | Series | Expected silicon DEV_ID, never measured | Exact ICPNs | DFP exact | DFP base-only | Pack algorithm RAM | Default ST workarea |
|---|---|---|---:|---:|---:|---:|---:|
| Flash/STM32C5[34]x.xldr | C531/532/542 | 0x44F | **63** | 48 | 15 | 64 KiB | 32 KiB |
| Flash/STM32C5[56]x.xldr | C551/552/562 | 0x44E | **60** | 46 | 14 | 128 KiB | 32 KiB |
| Flash/STM32C5[9A]x.xldr | C591/593/C5A3 | 0x45A | **49** | 45 | 4 | 256 KiB | 32 KiB |
| **TOTAL** | 9 series | 3 groups | **172** | **139** | **33** | | |

Source authorities:
- Production exact C5 CSV: data/device-catalog/research/stm32c5-commercial-icpn.csv, SHA256 = 23ab7db39a1ebc8d1c4d4f90f042d695e77533f35206454a737d9dfd31579069, locked by Production manifest.
- Official DFP commit a5f65bc64535cfa723e9d25f58d7ce23d0937aed: source fingerprints of three official Xldr and PDSC tracked by st-c5-dfp-commercial-loader-crosswalk-v0.9.json.
- Official ST OpenOCD fork commit c8d973bdad9a6fddb51459eda109b3b95d23b57a: stm32c5x.cfg target CFG Git blob 03bce02b166b669ca0d7515656bca68ff4db8b84; stldr_driver.c blob 99d51e696cd5cfa64948e479102472fb126afafa. This is **not** the packaged/upstream PLASMA OpenOCD runtime.
- Existing pinned v1.1 C5 PS static gate: data/device-catalog/research/st-c5-ps-backend-static-gate-v1.1.json.

## Existing Tcl and runtime blockers

The pinned fork source defines both die_max_flash_size and dev_id_loader as scalar Tcl lists using 'set', while later reading them as Tcl arrays. Prior v1.1 proposes two **in-memory-only** changes to 'array set'; these were never deployed to Production. Even after the syntax proposal, the **dev_id_loader table remains empty**. A matching manufacturer loader SHA256 is not evidence of installed or selected executable code.

Flash-size fallback on an invalid read is 256 KiB for 0x44F, 512 KiB for 0x44E, and 1 MiB for 0x45A; it is not actual silicon geometry. The 172 rows deliberately retain observed_silicon fields as null and never elevate fallback size to observed memory size.

The official DFP's algorithm RAM declaration (64/128/256 KiB) exceeds the fork's default WORKAREA (32 KiB). This **does not itself prove runtime incompatibility**, because the driver may manage SRAM separately. The actual C5 SRAM allocation, loader ABI and target state remain unverified.

**Every exact C5 ICPN remains no_mapping; no loader runtime staging, production packaging/distribution license approval, active stldr runtime, real probe, erase/program/verify or hardware readiness has been demonstrated.** No binary or source-derived patched CFG is generated or uploaded by this research PR.

## Reproduction — no hardware

Commands from repository root:

    python data/device-catalog/research/validate_st_c5_exact_loader_matrix_v1.py
    python data/device-catalog/research/validate_st_c5_exact_loader_matrix_v1.py --icpn STM32C531CBT3TR
    python data/device-catalog/research/validate_st_c5_exact_loader_matrix_v1.py --icpn STM32C531CBT6
    python data/device-catalog/research/validate_st_c5_exact_loader_matrix_v1.py --output-dir /tmp/st-c5-matrix
    python -m unittest discover -s data/device-catalog/research -p test_validate_st_c5_exact_loader_matrix_v1.py -v

Output is one deterministic JSONL entry per 172 exact Production C5 MPNs plus a SHA256 summary. The three loader source SHA256 values stay pinned in v0.9. All generated evidence is metadata-only and retains erase_program_verify_authorized=false and hardware_runtime_ready=false.

## Next engineering stages, separate admission gates

1. Independently build a dedicated pinned ST-fork OpenOCD host/ARMv7 binary, verify actual stldr registration and dependency ABI; never replace Production upstream OpenOCD by default.
2. Under an isolated non-deployable Tcl fixture, test the exact two array repairs and locally hash-pinned loader lookup for all three die IDs with dummy transport and no hardware init, no runtime downloads.
3. Validate RAM compatibility and legal loader packaging obligations separately.
4. With a separate hardware-safe plan, read genuine device ID, Flash size, security and Site electrical limits on explicitly selected silicon. All destructive operations remain blocked.
5. Seek separate exact-ICPN backend/Programming Profile admission approval only with actual evidence. Source mapping alone is not real programming.

**Effect on metrics: 172 C5 candidates documented; 0 newly Production-mapped; total outstanding ST backend no_mapping remains 465.**
