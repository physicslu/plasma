# Phase 2C — Z2 Kernel source lineage and PS–PL AXI isolation review

**Gate 1: public-source review and offline Host-only validation.**
**M1 Architecture Freeze: NO-GO. ADR-0003: Proposed.**
This document does not qualify a Kernel driver, FPGA Bridge, DT overlay,
FPGA programming procedure or external DUT electrical safe-state. No Z2
SSH/UART, kernel-device MMIO, FPGA load, service operation or deployment
was performed in this phase.

## 1. Disambiguate the three evidence identities

| Identity | Evidence actually established | Proof class / gap |
| --- | --- | --- |
| **Target as observed previously** | PYNQ-Z2 ARMv7, `6.6.10-xilinx-v2024.1-g3c0eca68c652`, boot-matched `/proc/config.gz` SHA-256 `842cd4d4f17487123ca33c7b04f593dc85340df11da59c2059ccc12b699a5169` | Recorded real-target inventory under Issue #975/#977. **Not a fresh observation this phase.** |
| **Public reference source** | Xilinx `linux-xlnx` tag `xilinx-v2024.1` at commit `e475cc1c9432587298212570c2af2be66b820c41`, with four Git blob SHA-1 IDs pinned under `pl/verification/z2_kernel_source_reference_v1.json` | Verified GitHub reference, **not** necessarily the target source. |
| **Source used to build deployed Z2 kernel** | `g3c0eca68c652` did **not** resolve through the public Xilinx repository's commit lookup; exact source/patch series, deployed kernel ELF/Image digest, deployed DTB digest and build recipe are not supplied | **UNRESOLVED**; no source-to-running-binary attestation exists. |

The distinction matters. A kernel `uname` suffix is not a cryptographic
source reference or proof that the board booted a reproducible artifact.
A boot-matched config hash attests only the recorded config bytes. A Git
blob object ID identifies file contents, **not** whether an arbitrary
checkout belonged to the specified commit, nor any running Kernel behavior.

### Pinned public Xilinx sources (commit `e475cc1`)

- [Zynq Manager driver, `zynq-fpga.c`](https://github.com/Xilinx/linux-xlnx/blob/e475cc1c9432587298212570c2af2be66b820c41/drivers/fpga/zynq-fpga.c).
- [Generic Manager interface, `fpga-mgr.c`](https://github.com/Xilinx/linux-xlnx/blob/e475cc1c9432587298212570c2af2be66b820c41/drivers/fpga/fpga-mgr.c).
- [FPGA Region implementation, `fpga-region.c`](https://github.com/Xilinx/linux-xlnx/blob/e475cc1c9432587298212570c2af2be66b820c41/drivers/fpga/fpga-region.c).
- [OF FPGA Region implementation, `of-fpga-region.c`](https://github.com/Xilinx/linux-xlnx/blob/e475cc1c9432587298212570c2af2be66b820c41/drivers/fpga/of-fpga-region.c).

## 2. Source-level call-path review (REFERENCE, not Z2 binary behavior)

| Path / lines in pinned reference | Verified source behavior | Unsupported extrapolation |
| --- | --- | --- |
| `zynq-fpga.c:251–315` | In full configuration `zynq_fpga_ops_write_init` writes `SLCR_FPGA_RST_CTRL` and `SLCR_LVL_SHFTR_EN`, then uses PCAP prepare sequence. The three `regmap_write` return values in this block are not checked. | Register operations do **not** establish that an already outstanding AXI transaction completed/drained or that the target binary follows this path. |
| `zynq-fpga.c:485–525` | `zynq_fpga_ops_write_complete` polls `PCFG_DONE`, then writes shifter-enable and AXI reset-deassert registers for full configuration; these two `regmap_write` results are not checked. | A successful manager return is **not** independent evidence that every SLCR write took effect or all endpoints are safe. |
| `fpga-mgr.c:713–735` | `firmware_store` calls `fpga_mgr_firmware_load` directly. | A direct Manager `firmware` sysfs write cannot inherit FPGA Region's bridge-list orchestration by assumption. |
| `fpga-region.c:97–160` | `fpga_region_program_fpga` gets Manager lock, gathers optional bridge list, disables bridges, loads the image, and enables bridges on success. | A bridge list may be **empty** and even a registered bridge needs physical bus-drain qualification. |
| `of-fpga-region.c:74–141` | OF region bridge collection can succeed with an empty list, including when no `fpga-bridges` property is present. | Having a Region registered is not evidence of any effective isolated AXI path. |

**Existing target snapshot:** FPGA Manager `fpga0` and FPGA Region
`region0` were bound; Region did not expose `fpga-bridges` and
`/sys/class/fpga_bridge` had no entries. `uio0` exposed `map0`
for `0x40000000–0x4000FFFF`. This is a read-only *observation*; there
was no deliberate AXI drain, bridge toggling, DMA audit or bus-stall test.
Neither compiled `CONFIG_FPGA_BRIDGE=y` nor the UIO driver binding creates
physical isolation.

**Source-lineage finding:** An unchecked `regmap_write` in the public
reference is an actionable review risk, not a proven bug in the deployed
target or evidence of a real failure. Confirm exact target implementation
first. Separately, direct Manager firmware-load and Region programming
are different call paths.

## 3. New Host-only reproducibility checks

Inputs:

- Pinned **reference-only** manifest:
  `pl/verification/z2_kernel_source_reference_v1.json`.
- Optional existing, offline `linux-xlnx` checkout matching the
  independently reviewed tag/commit; the tool never clones or updates Git.
- `pl/tools/runtime_fpga_kernel_lineage.py`: checks manifest cannot be
  promoted to `target-matched`, requires unresolved source/patch/kernel
  binary/DTB evidence, and optionally checks exact Git **blob** SHA-1 for
  the four reference files. Symlinks, paths escaping `drivers/fpga`,
  incomplete files, wrong object IDs and oversized inputs are rejected.

```sh
python -m pl.tools.runtime_fpga_kernel_lineage \
  --manifest pl/verification/z2_kernel_source_reference_v1.json

# Optional independent local checkout (not required for CI):
python -m pl.tools.runtime_fpga_kernel_lineage \
  --manifest pl/verification/z2_kernel_source_reference_v1.json \
  --reference-root /path/to/already-reviewed/linux-xlnx
```

The CLI always returns `M1_NO_GO`, `reload_authorized=false` and
`hardware_ready=false`. With the optional checkout it may report
`reference_files_verified=true`, which means **the four blobs matched**
only; it does not establish Git tree ancestry or target binaries.
The dedicated GitHub Actions workflow tests the manifest and offline
adversarial scenarios. CI does not possess the physical source/binary
attestation or a full Xilinx checkout; **do not mislabel this as an actual
Z2 Kernel source match**.

## 4. Smallest useful *future* Z2 read-only provenance work

This requires a **new explicitly scoped Gate 1 hardware plan** and current
operator/exclusive-access conditions; it was **NOT RUN** here.

1. Record current boot ID, `uname -a`, `/proc/version`,
   `/proc/config.gz`, package/build metadata and Kernel image location,
   without publishing private identifiers. Compare to the **recorded**
   Issue #977 snapshot, not to a presumed unchanged board.
2. Identify board DTB as booted (including overlays), hash raw DTB/DT
   source where available, and collect only relevant DevCfg `syscon`,
   Region `fpga-mgr`/`fpga-bridges`, UIO and AXI-master/DMA binding
   facts. A live DT node listing is not an atomic hardware-owner audit.
3. Obtain source repository + full 40-char commit + **all patches** and
   exact booted Kernel binary. If unavailable, record
   `SOURCE_BINARY_UNMATCHED`. Do **not** treat a public `v2024.1` tag
   as an exact match merely because the printed name resembles it.
4. Draw each PS GP/HP/ACP → PL / PL → PS AXI master and relevant reset
   and interconnect route on this precise board and bitstream. Identify a
   measurable **all-requests-completed** or controlled-abort criterion
   separately from SLCR reset and shifter register values.
5. Compare immutable external DUT power/OE/NRST safe state, independent
   UART/power recovery, and Kernel/SSH/Gateway liveness observations.
   These are separate **future HIL measurements**, not prerequisites
   already qualified by this document.

### Admission for a later controlled HIL (not granted here)

**STOP** if target source/binary provenance is unresolved; any non-cooperating
or Kernel/DMA MMIO consumer may race; a retained VMA or pending AXI master
is unknown; no qualified independent safe IO or recovery; or a real
bitstream's ABI/source hash is unmatched. A Python timeout cannot cancel a
blocked AXI CPU transaction. Avoid deliberate AXI-fault injection without
a fully qualified isolation/recovery plan.

## 5. Architectural option to benchmark

A single fixed RTL image with capability-oriented SWD/SPI engines and
software-selectable IC algorithms may satisfy the no-reboot product
requirement while eliminating most full-reconfiguration hazards. It should
be compared using actual RTL resource/timing and Site throughput evidence,
not ideological preference for dynamic partial/full FPGA loading.

**Gate 1 completion criterion:** publication of these Host-only source
review/manifest/checks under a separate Draft PR with offline CI.
**Gate 2 requires separate explicit owner approval to merge.**
PR #972 remains untouched; M1 remains NO-GO.
