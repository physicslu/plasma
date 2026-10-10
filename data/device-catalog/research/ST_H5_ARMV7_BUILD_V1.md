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
