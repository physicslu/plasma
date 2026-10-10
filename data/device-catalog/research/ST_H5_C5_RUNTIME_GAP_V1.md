# ST H5/C5 OpenOCD Runtime Gap Analysis v1

**Reference:** 2026-10-10. **State:** research-only; no Production backend binding, no runtime deployment, no PPU/HIL or electrical-readiness claim.

## Executive decision

**Prioritize an isolated, pinned ST-fork STM32H5 OpenOCD backend trial. Do not migrate all 4,629 ICs to ST's fork.** H5 has a native flash driver in the fixed ST source; C5 instead uses an `stldr` driver with an initially empty loader table and known Tcl syntax/lookup defects. Both require real PS/adapter qualification before promotion.

A target CFG and native flash implementation in a *source tree* do not prove that the actual deployed Plasma PS binary includes them or that the Plasma FPGA SWD adapter can use them.

## Immutable current catalog baseline (after v6.31 / PR #791)

| Boundary | Count/state |
| --- | --- |
| Production exact ICPNs / sources | **4,629 / 28** |
| Mapped / no_mapping | **4,164 / 465** |
| Active mapped route / denominator | **4,085 / 4,550** |
| STM32H5 / STM32C5 blocked | **190 / 172** |
| Other runtime-blocked | N6 **32**, WB0 **24**, WL3 **47** |

All **362** H5/C5 exact identities are **already in the Production catalog as Layer-1 metadata**, but remain completely unbound to programming backends. Earlier C5 v0.8–v1.1 reports (2026-09-29) correctly recorded an earlier 2,683-exact Production snapshot; **do not reuse that historical count as today's baseline**.

The exact 465-IC `openocd-final-runtime-blocked-v6.31.csv` remains the fail-closed authority.

## Candidate source provenance (not installed)

- Packaged upstream baseline: `openocd-org/openocd` 0.12.0, commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`.
- ST candidate fork: [STMicroelectronics/OpenOCD](https://github.com/STMicroelectronics/OpenOCD/tree/c8d973bdad9a6fddb51459eda109b3b95d23b57a), commit `c8d973bdad9a6fddb51459eda109b3b95d23b57a` (branch `openocd-cubeide-r7`, observed 2026-04-03).
- H5: [`tcl/target/stm32h5x.cfg`](https://github.com/STMicroelectronics/OpenOCD/blob/c8d973bdad9a6fddb51459eda109b3b95d23b57a/tcl/target/stm32h5x.cfg) (blob `b9e67c604f7d824fefca03b42d0b112e1785235a`) and [`src/flash/nor/stm32h5x.c`](https://github.com/STMicroelectronics/OpenOCD/blob/c8d973bdad9a6fddb51459eda109b3b95d23b57a/src/flash/nor/stm32h5x.c) (blob `b5f24a39da05e5235167ff91c110ed89c2e3f9c5`); driver registered in `src/flash/nor/drivers.c` and listed in `Makefile.am`.
- C5: [`tcl/target/stm32c5x.cfg`](https://github.com/STMicroelectronics/OpenOCD/blob/c8d973bdad9a6fddb51459eda109b3b95d23b57a/tcl/target/stm32c5x.cfg) (blob `03bce02b166b669ca0d7515656bca68ff4db8b84`), `flash bank ... stldr ...`, plus `src/flash/nor/stldr_driver.c` (blob `99d51e696cd5cfa64948e479102472fb126afafa`). The C5 target's `dev_id_loader` declaration is *empty* and its scalar-vs-array lookups require an isolated, verified fix.
- Fork is licensed GPL-2.0-or-later; inspect dependent binaries, local .xldr redistribution permissions, notices, and delivery obligations before any shipped artifact.

## H5 — first candidate (190 research candidates, zero admitted)

The fixed fork has **native** `stm32h5x` flash implementation, including `probe`, `erase`, `write`, `read`, security-related `option` commands and `mass_erase`. Target script declares both non-secure and secure-alias banks. Five device-ID groups are defined by driver source: `0x474`, `0x478`, `0x47A`, `0x47C`, `0x484`. Actual die-ID, revision, Flash geometry, security/product state and allowed flash access still require *independent hardware observations*. Presence of an entry point is not proof of correct behavior across all 190 commercial part numbers.

Recommended first silicon: **STM32H503CBT6**, a Production admitted exact identity (128 KiB Flash, LQFP-48), chosen to constrain the first probe. This is a *test candidate*, not a verified Plasma target or a procurement requirement. At a later stage test the other H5 device-ID groups and protected configurations separately.

### H5 integration gates, in order

1. **Artifact provenance:** reproduce fixed-source host build and target PS **ARMv7** build in an isolated branch; record OpenOCD version, source commit, toolchain, configuration options, binary + script-tree SHA256 and packaged artifact SHA256. Do not replace existing 0.12.0 artifact or silently reuse its runtime_id.
2. **Process and transport:** confirm selected Z2/PPU image, how the Plasma adapter exposes SWD/JTAG, and whether the fork can be built with this adapter. Use only loopback-bound Tcl RPC under the Site supervisor; verify independent PPU hardware/recovery ownership and per-Site isolation. A stock ST-Link binary alone does not qualify the FPGA adapter.
3. **Non-destructive tests:** `--version`, Tcl target script parsing, registered `stm32h5x` flash driver, offline command help, then approved read-only real IDCODE/flash size/flash bank enumeration. No erase/write during this phase.
4. **Physical programming:** only after verified Electrical Programming Profile, site voltage/current limits, reset and level shifting, evaluate reversible scratch-image `erase → program → readback/verify` on the approved exact silicon. Require negative tests for incompatible die IDs, security states, cancellation and per-Site recovery.
5. **Promotion:** evidence-backed exact-ICPN backend mapping and Programming Profile are *separate* gates. An owner-approved PR must update the registry and tests. Do not mark every H5 SKU ready just because one device works.

**Safety:** no automated mass erase, option-byte, OBK provisioning, RDP/TrustZone/security state transitions, OTP or irreversible state changes in the first H5 backend. Driver source contains these operations, but PLASMA must deny them by policy and tests.

## C5 — reuse existing research rather than restart (172 blocked)

- Existing [C5 DFP/loader crosswalk](ST_C5_DFP_LOADER_CROSSWALK_V09.md) pinned three official `.xldr` groups and their source hashes. Research cohort: **139** exact DFP variants, **33** base-device-only matches; the 33 require exact commercial metadata evidence, not fabricated equivalents.
- Existing [PS static gate v1.1](ST_C5_PS_BACKEND_STATIC_GATE_V11.md) isolates two Tcl `set` → `array set` corrections **without** changing deployed CFG. The unchanged vendor CFG's loader table is empty.
- C5 vendor loaders require differentiated pack-declared RAM reservation: 64/128/256 KiB while CFG defaults to a 32 KiB work area. These are not interchangeable quantities; qualify the actual STLDR allocation and SRAM limits on a compiled backend.
- Verify `stldr` registration in the selected PS binary; load exact SHA-pinned local loader files, never download remote binaries at physical-programming time.
- Independent license/distribution review, read-only real silicon DEV_ID and Flash readback, and safe HIL are still required. **No new C5 Production identity publication is needed** to acknowledge the 172: they are already Layer-1 admitted. Only backend/physical admission remains blocked.

## Runtime strategy and deliverables

Adopt **versioned, capability-gated multiple backend artifacts** rather than an in-place global upgrade:

```text
exact IC -> candidate backend provider + pinned runtime artifact
        -> Programming Profile + electrical profile
        -> PPU/Site capabilities and verified adapter
        -> read-only qualification -> controlled physical execution
```

- Keep current upstream OpenOCD `0.12.0` serving existing mapped families.
- Stage a separate experimental `openocd-st-h5` provider, not enabled for Production jobs.
- Run an independent `openocd-st-c5-stldr` experiment only after C5 Tcl, loader and redistribution gates are satisfied.
- Expose supported target driver, flash driver, enabled transports, executable/binary checksum and mutually exclusive Site worker configuration in a machine-readable provider capability manifest.
- If a profile has no independently verified provider + electrical compatibility, the Site remains **hardware_runtime_ready=false**, regardless of catalog mapping.

### Definition of done for next engineering PR

Build and inspect an isolated H5 fork candidate on host and Z2 ARMv7 (or mark blocked with exact diagnostics), verify that required driver and SWD transport are available in the artifact, publish content-hash-locked **non-deployable** test evidence and fail-closed CI. Do not deploy to Z2, enable DUT power or issue destructive commands without a separate qualification plan/approval.

## Machine-readable source-only validation

```bash
python data/device-catalog/research/validate_st_h5_c5_runtime_gap_v1.py
python -m unittest discover -s data/device-catalog/research \
  -p test_validate_st_h5_c5_runtime_gap_v1.py -v
```

Source-pin assertions guard research continuity; GitHub CI does **not** build vendor OpenOCD, fetch ST binaries, qualify physical SWD or grant permission to program any IC. H5/C5 Production rows and the manifest remain unchanged by this research PR.

### ARMv7 follow-up experiment

Draft PR #794 carries the next bounded H5 gate: compile, package, install and execute the same pinned ST fork in the PLASMA ARMv7 userspace class, while keeping FPGA SWD, physical target access, Production mapping and `hardware_runtime_ready` explicitly out of scope. See `ST_H5_ARMV7_BUILD_V1.md`.
