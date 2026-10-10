# STM32H5 OpenOCD ARMv7 cross-build + QEMU execution v1

**Status: experimental, research-only.** This follow-up Draft PR #796 targets Host PR #793 and does not depend on either PR being merged.

## Scope and rationale

The initial run used QEMU ARMv7 userspace for **the entire vendor C toolchain compilation**, which was still running beyond 20 minutes. The corrected approach separates CPU-intensive compilation from architecture-specific runtime verification:

1. In a temporary **x86_64 Debian bookworm** container, use `gcc-arm-linux-gnueabihf`, GNU Autotools and a fixed ST source revision `c8d973bdad9a6fddb51459eda109b3b95d23b57a`. Check H5 target CFG, Flash driver and registration source Git blob SHAs; compile and install into a disposable prefix. Build includes the `dummy` JTAG adapter, **not** the Plasma FPGA SWD adapter.
2. In a temporary **Debian bookworm ARMv7 QEMU-user** container, execute that ARM ELF and parse the H5 target Tcl configuration under **dummy JTAG, without `init`**. This is not a physical IDCODE probe.
3. Run the existing PLASMA `scripts/openocd-runtime.py build` and `verify` from inside ARMv7 QEMU; verify ELF architecture, `--version`, shared library resolution and the archive/payload SHA256 match. Report `hardware_runtime_ready=false`.
4. Upload **JSON evidence only**, not a compiled vendor binary or tarball; never install into the deployed Z2 image, change Production profiles, enable the device, or issue any erase/flash/security operation.

## Qualification limitations

Cross-compilation targets ARMv7 but is **not equivalent to a real PYNQ-Z2**. Debian bookworm (glibc ABI) may differ from the Z2 OS; binary execution under QEMU is only a software smoke test. The dummy JTAG adapter does **not** exercise the intended FPGA SWD transport or demonstrate flash programming.

If the cross-build fails, inspect its exact toolchain/config/target dependency error rather than asserting H5 ARMv7 support. A passed build must have an independent selected Z2 PS native ABI/build/provenance check and a qualified FPGA SWD adapter *before* hardware readiness can change.

## Review gates

The canonical Production source baseline remains **4,629 exact IC identities: 4,164 mapped and 465 no_mapping**, including H5 190 and C5 172, all still route blocked. The PR stays Draft; merger requires separate authorization. Source-locked host and ARMv7 smoke evidence is not a legitimate change of IC backend mapping.

See workflow [device-catalog-st-h5-armv7-build-v1.yml](../../../.github/workflows/device-catalog-st-h5-armv7-build-v1.yml).

## Verified CI evidence — 2026-10-10

Both methods compile the same fixed ST source commit `c8d973bdad9a6fddb51459eda109b3b95d23b57a`. Both are **software-only**, and both run the H5 CFG under **dummy JTAG** with no hardware `init`.

| Verification | Original full QEMU ARMv7 compile | x86_64→ARMv7 cross-compile + QEMU |
| --- | --- | --- |
| GitHub CI | [run 38033390094](https://github.com/physicslu/plasma/actions/runs/38033390094) | [run 38034789548](https://github.com/physicslu/plasma/actions/runs/38034789548) |
| Core job result | `armv7-container-build: PASS` | `armv7-cross-compile-and-qemu-smoke: PASS` |
| Runtime ID | `0.12.0-c8d973bdad9a` | `0.12.0-c8d973bdad9a` |
| Artifact SHA-256 | `c56245e22af86cd64f8621c72da1d08058ea93c53224d7dfa210da4194f6e606` | `f3a60db251a53bd18bf2a5acb80625abfc47c2eb298bb8a3a17112827cb502cd` |
| Payload SHA-256 | `2a6c3ca118bf547244efecaa94eb40048180741eb17b77eaf02cdcdf3366964c` | `a7216d585358faf2710444b04d004c2aa531a16ef105d04129268883f0fc863d` |
| Physical programming claims | **none** | **none** |

The differing SHA-256 values are expected: the build environments and compilers are not pinned as identical reproducible toolchains. Do **not** assert binary reproducibility from the shared `runtime_id`; each measured archive/payload pair passes the existing PLASMA artifact verifier independently.

The original QEMU emulated compilation required approximately **25 minutes** on its CI run; the cross-compile + QEMU smoke completed in approximately **3 minutes**. This is a CI-throughput improvement, **not** an improvement in target-programming throughput or a compatibility claim.

Current promotion gates remain closed:
- Selected Z2 PS glibc/library ABI compatibility: **unverified** (Debian bookworm is not a substitute for deployed PYNQ Linux).
- FPGA SWD adapter transport and real DUT IDCODE: **unverified**.
- Electrical Programming Profile, per-Site protection, reset and flash read/write: **unverified**.
- Production Catalog backend mapping and physical Flash erase/write/verify: **unchanged / unauthorized**.

Only JSON audit evidence was uploaded by either run. No compiled vendor OpenOCD archive, binary, STLDR, or device programming artifact was distributed through the workflow.
