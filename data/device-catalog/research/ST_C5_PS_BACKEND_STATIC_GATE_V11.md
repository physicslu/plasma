# STM32C5 PS Backend Static Gate v1.1

**As of 2026-09-29 · research only · no Production Catalog or executable programming change.**

## Finding: PS runtime is not equivalent to an OpenOCD source tree

Review of Plasma `main` merge of #681 (`ce79556d852eb9e1b0a261d25c6d956d25743cd4`):

- `software/python/plasma_interfaces/openocd_executor.py` (Git blob `062fefa79926535e8c89dddcd55bee95b65b22c3`) declares `process_launcher: ProcessLauncher | None = None`, and explicitly refuses `execute()` without an injected software-validation launcher.
- `software/python/plasma_interfaces/openocd.py` (blob `3d12cc658b6d71adf8b8dfc14ea07ac4a0c5cab7`) blocks direct erase/program/verify/read.
- `software/python/plasma_server/execution_router.py` (blob `6ce78bb4421448327a844171d97ffe7995ca8fbd`) reports `backend_implementation_state=plan_compiled_not_executable` and `hardware_runtime_ready=false`.
- These are source-code facts, **not an inventory of any physical Z2/PS installation**. Its deployed OpenOCD executable version, build options, actual `stldr` registration, interface adapter, flash algorithm availability, manufacturer binary redistribution permissions and real attached silicon status remain UNVERIFIED. The preflight from merged #681 only verifies source/locally-staged bytes and caller-supplied, unauthenticated DEV_ID/size assertions.

**Conclusion:** no C5 hardware-ready or executable route can be inferred from frozen source and a matching loader SHA256 alone.

## Minimal two-keyword Tcl proposal — not deployed

The [pinned ST OpenOCD fork](https://github.com/STMicroelectronics/OpenOCD/blob/c8d973bdad9a6fddb51459eda109b3b95d23b57a/tcl/target/stm32c5x.cfg) contains the **two independently verified scalar/list vs indexed-array Tcl defects**:

```diff
-    set die_max_flash_size {
+    array set die_max_flash_size {
...
-set dev_id_loader {
+array set dev_id_loader {
 }
```

`validate_st_c5_ps_backend_static_gate_v11.py` accepts ONLY the exact vendor CFG Git blob (`03bce02b166b669ca0d7515656bca68ff4db8b84`) before making the two replacements **in memory**. It does not commit a generated manufacturer script or touch deployed production target configurations.

Critically, the proposed `dev_id_loader` remains **EMPTY**; not one of the three official vendor `.xldr` paths is installed or registered through this proposal. The host-only Tcl fixture evaluates **only** the extracted `stm32c5x_get_size` procedure and empty array declaration using a fake memory-read function and fake shutdown, not the full target script and not an OpenOCD process.

Tests assert: fallback for invalid FLASH_SIZE read (0 or 0xFFFF) produces 0x44E→512 KiB, 0x44F→256 KiB, 0x45A→1 MiB; a valid size register wins over fallback; an unknown die fails closed; no loader array entry can be used after the fix.

## Separate DFP algorithm RAM versus target default WORKAREASIZE

The original ST C5 target config default work area is `0x8000 = 32 KiB`, while manufacturer DFP v2.1.0 PDSC independently declares:

| C5 group | Pinned DFP loader | DFP `algorithm RAMsize` | ST target default work area |
| --- | --- | ---: | ---: |
| C53/C54 | `STM32C5[34]x.xldr` | 64 KiB | 32 KiB |
| C55/C56 | `STM32C5[56]x.xldr` | 128 KiB | 32 KiB |
| C59/C5A | `STM32C5[9A]x.xldr` | 256 KiB | 32 KiB |

**This is an unresolved compatibility question, not proof that the target necessarily fails.** DFP `RAMsize` is a pack-declared flash-algorithm reservation; ST's customized OpenOCD driver manages its own sections and memory. Prove actual allocation and SRAM limits in an isolated compiled backend and later read-only physical qualification before choosing WORKAREASIZE or trusting fallback Flash geometry. Do not overcommit on marketing RAM numbers or shrink loader requirements just to pass CI.

The fixed-commit ST `stldr_driver.c` and `drivers.c` original Git blobs are verified. The source parser looks for ELF `StorageInfo` and mandatory `Init`, `SectorErase`, `Write`; fixed-commit vendor loader ELF32 headers and symbol tables are tested separately. This **does not prove actual Plasma binary includes this flash driver, the algorithm fits target RAM, nor that execution succeeds**.

## Reproduction

```bash
python data/device-catalog/research/validate_st_c5_ps_backend_static_gate_v11.py
python -m unittest discover -s data/device-catalog/research \
  -p test_validate_st_c5_ps_backend_static_gate_v11.py -v
```

The separate GitHub CI job temporarily fetches exact-commit manufacturer CFG, driver source, registry and three vendor `.xldr` binary samples for offline replay, builds a **host-only Tcl test fixture** and runs it with `tclsh`. It neither installs OpenOCD nor executes any physical-programming sequence. Upstream binaries and generated patched CFG are not committed or uploaded.

## Next actual PS/HIL evidence gate

1. Inventory the **selected deployment PS image**, installed OpenOCD `--version`, binary SHA256 and origin/build configuration, installed scripts and `stldr` flash-driver registration. Repository source alone is insufficient; no SWPC/Z2 access is claimed in this PR.
2. Independently confirm manufacturer redistribution terms for the three original loader binaries and any selected fork/build license obligations.
3. Stage only locally source-hash-locked loader files, with no runtime upstream URL fetch; qualify a full isolated target configuration including the two-array fix, actual working-area calculations and adapter transport.
4. Obtain genuine read-only device-ID and flash-size observations under an approved Site reset/power sequence. A software fake DEV_ID is not HIL evidence.
5. Complete the 33 missing exact DFP commercial metadata and separately seek owner approval before **any** Production ICPN publication.

**Frozen ST Production remains 2,683 exact ICPNs across 23 source families.** The entire C5 172 observed eStore research cohort remains non-executable and absent from Production. Security mutation/option bytes/RDP/OTP, erase, programming and mass erase are NOT authorized by this gate.
