# PPU Runtime interface module inventory (Phase 1)

**Status:** Source classification only; not a packaging change or retirement authorization.  
**Source baseline:** `main` at `082f018941b508a1310556a2242b112a6ad57dfe` (2026-11-10).  
**Scope:** The 29 Python files directly under `software/python/plasma_interfaces/`, including `__init__.py`.

## Evidence levels and packaging boundary

- `CONFIRMED`: a directly inspected source-level fact, with exact file/line evidence. It does **not** assert that the code was exercised on Z2 or DUT.
- `EXPECTED_BY_BUILD_RULE`: `scripts/ppu-runtime.py:L30-L38` includes `plasma_interfaces` in `PPU_PACKAGES`, and `L147-L175` copies its tree into the ZipApp build root. Its `CATALOG_ONLY_MODULES` list (`L43-L64`) excludes no `plasma_interfaces` file. Thus **all 29 current files are expected in a successfully built runtime ZipApp from this source baseline**, absent a different release process.
- `NOT_VERIFIED`: no authoritative released `ppu.pyz` ZIP member list, Artifact SHA256, running Z2 module inventory, or complete dynamic-call reachability has been established. **No row below is `CONFIRMED_IN_ARTIFACT`.**

Classification is about *observed source intent and known callers*, not permission to delete a module. `Production` means a current Runtime import/selection or execution seam; `Engineering/HIL` includes host-only test models, contracts and physical-path development modules; `Mock` remains a supported Runtime option; `Reserved` is a callable stub. Unknown consumers remain `NOT_VERIFIED`, not `LEGACY` by name.

## Module-by-module inventory

Every file below is **`EXPECTED_BY_BUILD_RULE`** for a build from the pinned source. The last column gives source evidence for the narrower role; Artifact inclusion and unlisted dynamic consumers remain **`NOT_VERIFIED`**.

| Module (`plasma_interfaces/`) | Source-intent classification | Known role / limit | Exact evidence |
| --- | --- | --- | --- |
| `__init__.py` | Production package/export surface | Exports base, FPGA, Mock and OpenOCD interfaces; an export is not proof that hardware runs | `software/python/plasma_interfaces/__init__.py:L1-L10` |
| `base.py` | Production interface contract | Abstract programming interface used by SiteManager | `software/python/plasma_server/site_manager.py:L18-L22`; `software/python/plasma_interfaces/base.py:L1-L10` |
| `bluepill_remote_bitbang.py` | Engineering/HIL physical-path candidate | Injected word-port; no automatic device open | `software/python/plasma_interfaces/bluepill_remote_bitbang.py:L1-L9` |
| `bluepill_z2_word_port.py` | Engineering/HIL physical-path candidate | Explicit Z2 WordPort; device admission remains caller-owned | `software/python/plasma_interfaces/bluepill_z2_word_port.py:L1-L9` |
| `configuration_owner.py` | Engineering/Host-only simulation | Synthetic configuration owner, not real FPGA admission | `software/python/plasma_interfaces/configuration_owner.py:L1-L10` |
| `configuration_safety_contract.py` | Engineering/Host-only contract | Validation model without physical I/O | `software/python/plasma_interfaces/configuration_safety_contract.py:L1-L8` |
| `fixed_abi_hardware_driver.py` | Engineering/HIL contract | Injected qualified word port; does not open a device | `software/python/plasma_interfaces/fixed_abi_hardware_driver.py:L1-L9` |
| `fixed_abi_mmio_port.py` | Engineering/HIL adapter | Fixed ABI port with explicit LinuxMMIO/barrier prerequisites | `software/python/plasma_interfaces/fixed_abi_mmio_port.py:L1-L9` |
| `fixed_abi_swd.py` | Engineering/HIL control contract | Transport-neutral SWD logic, no autonomous hardware access | `software/python/plasma_interfaces/fixed_abi_swd.py:L1-L9` |
| `fpga.py` | Reserved Runtime stub | `interface: fpga` is selectable, but operations reject as not ready; **not** proven retired | `software/python/plasma_server/site_manager.py:L112-L122`; `software/python/plasma_interfaces/fpga.py:L9-L52` |
| `linux_mmio.py` | Privileged/HIL-capable backend | Explicit `/dev/mem` mapping; also copied as Bootstrap privileged source, not confirmed directly reachable from Production SiteManager | `software/python/plasma_interfaces/linux_mmio.py:L155-L175`, `L235-L258`; `scripts/ppu-bootstrap-installer.py:L125-L135` |
| `mmio_loop_test.py` | Engineering/HIL test | Injected MMIO scratchpad experiment; no implicit device open | `software/python/plasma_interfaces/mmio_loop_test.py:L1-L8` |
| `mock.py` | Mock (Runtime-selectable) | SiteManager officially permits `interface: mock`; not dead code | `software/python/plasma_server/site_manager.py:L18-L22`, `L112-L122` |
| `mpe_swd.py` | Engineering/Host-only candidate | MPE transaction model with injected port; no automatic device open | `software/python/plasma_interfaces/mpe_swd.py:L1-L8` |
| `native_bluepill_word_port.py` | Engineering/HIL physical-path candidate | Native C bridge inside an already-owned MMIO lease | `software/python/plasma_interfaces/native_bluepill_word_port.py:L1-L9` |
| `openocd.py` | Production execution interface | Runtime `flash_cycle` requires C-3 client; isolated operations reject | `software/python/plasma_interfaces/openocd.py:L19-L34`, `L48-L65`, `L112-L132` |
| `openocd_rpc.py` | Exported RPC utility; consumer scope `NOT_VERIFIED` | TCL RPC primitive exported by package; cannot classify as retired | `software/python/plasma_interfaces/__init__.py:L4-L9`; `software/python/plasma_interfaces/openocd_rpc.py:L1-L10` |
| `openocd_worker.py` | Exported worker utility; consumer scope `NOT_VERIFIED` | OpenOCDWorker exported by package; live use not fully traced | `software/python/plasma_interfaces/__init__.py:L4-L10`; `software/python/plasma_interfaces/openocd_worker.py:L1-L10` |
| `package_provider.py` | Production Provider seam | Runtime imports PackageProviderInterface; successful child exit alone does not prove Flash PASS | `software/python/plasma_server/site_manager.py:L18-L22`; `software/python/plasma_interfaces/package_provider.py:L1-L9` |
| `site_safety.py` | Safety contract; consumer scope `NOT_VERIFIED` | Abstract safety interface, not direct hardware authorization | `software/python/plasma_interfaces/site_safety.py:L1-L13` |
| `site_worker_c3.py` | Production C-3 client | AF_UNIX Runtime client; C-3 owns admission/OpenOCD/SAFE_OFF/seal | `software/python/plasma_interfaces/site_worker_c3.py:L1-L17`, `L35-L70` |
| `swd_mmio32_contract.py` | Engineering/Host-only contract | Native 32-bit MMIO ordering model; no device open | `software/python/plasma_interfaces/swd_mmio32_contract.py:L1-L8` |
| `swd_native_linux_mmio.py` | Engineering/HIL candidate | Inert ABI-v5 adapter over admitted LinuxMMIO lease | `software/python/plasma_interfaces/swd_native_linux_mmio.py:L1-L9` |
| `swd_native_normal_contract.py` | Engineering/Host-only contract | NORMAL transaction contract, not compiled OpenOCD or real I/O | `software/python/plasma_interfaces/swd_native_normal_contract.py:L1-L9` |
| `swd_opencd_5088_command_contract.py` | Engineering/Host-only contract | Pinned OpenOCD SWD command translation; no physical I/O | `software/python/plasma_interfaces/swd_opencd_5088_command_contract.py:L1-L9` |
| `swd_site.py` | Engineering/HIL candidate | Injected MMIO site logic; no autonomous device/socket access | `software/python/plasma_interfaces/swd_site.py:L1-L9` |
| `swd_transaction.py` | Engineering/HIL candidate | Injected ABI transaction transport; no implicit device open | `software/python/plasma_interfaces/swd_transaction.py:L1-L9` |
| `uio_backend.py` | Engineering/Host-only simulation | **Regular-file-only** fake UIO mapping; real character device is deliberately refused | `software/python/plasma_interfaces/uio_backend.py:L1-L9`, `L123-L133`, `L226-L235` |
| `wordport_stage_monitor.py` | Engineering/HIL observability | Read-only stage snapshot monitor, not SWD executor | `software/python/plasma_interfaces/wordport_stage_monitor.py:L1-L7` |

## Release and reachability caveats

1. **Packaging is not activation.** Presence in a build tree says nothing about whether a module executes or carries root authority. The Bootstrap installer separately ships privileged `linux_mmio.py` source (`scripts/ppu-bootstrap-installer.py:L125-L135`); this is not an extra Runtime process.
2. **No actual Release member evidence.** The source builder uses `shutil.copytree` followed by `zipapp.create_archive` (`scripts/ppu-runtime.py:L147-L175`), but the CI/Release Artifact ZIP Central Directory and hash remain **`NOT_VERIFIED`**. Do not label any row `CONFIRMED_IN_ARTIFACT` yet.
3. **No fully proven global hardware-path negative.** Standard SiteManager selects Mock, OpenOCD and a reserved FPGA stub (`software/python/plasma_server/site_manager.py:L112-L122`). An absence of direct UIO/LinuxMMIO imports in this factory is not a complete proof against dynamic imports elsewhere. It does not justify removing those modules.
4. **No confirmed retired module in this inventory.** Compare each proposed legacy deletion with [SWD retirement](../development/swd-legacy-path-retirement.md), active build/consumer links, and HIL requirements first. A module name or host-only test docstring is insufficient to retire it.

## Later evidence and separate gates

| Candidate follow-up | Current classification | Evidence required before action |
| --- | --- | --- |
| Actual runtime `.pyz` member inventory | `NOT_VERIFIED` | Existing Release Artifact identity, SHA256 and ZIP member list; no rebuild claim |
| Production versus HIL dynamic reachability | `NOT_VERIFIED` outside traced entry points | Exhaustive config/registry/import/subprocess call graph plus Host-only negative tests |
| Prune interfaces or shrink Bootstrap scripts | **Not authorized** | Independent Gate 1 scope, complete dependency and recovery tests, and appropriate Z2/DUT Gate evidence |

This Phase 1 inventory changes no packaging rules, import path, Runtime logic, tests, service unit or device state. Classification labels are not permission to prune files.
