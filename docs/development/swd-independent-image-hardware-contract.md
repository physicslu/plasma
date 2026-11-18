# Independent SWD v5 Image: Host-only hardware contract audit

Status: Host-only source contract. This document grants no Z2 MMIO, FPGA load,
Device Tree change, DUT operation or deployment authority.

## Pinned provenance

Current audited Image (since 2026-11-03, PR #1285; `ab79b04e` and `bd976140`
retired under Replace-by-Default — removed from the Root devmem table, B2
contracts, releases and fixtures):

- Vivado Host Build run 41648270405, project `pl/projects/z2-swd-independent`,
  source `d0add58c3e36ce930b812ec9eb1e37f22c95a615` (PR #1285: per-command
  `0x68 IDLE_CYCLES`, RW 8..255, reset/MODE-OFF value 8). WNS 0.320 ns, TNS 0,
  WHS 0.031 ns; TIMING-18 external SWD I/O omissions (2 in, 4 out) unchanged.
- BIT SHA256 `8419dfff8cb634a47738cf6cecf8e332f70f820e61e87326013daf21635bb2f3`.
- HWH SHA256 `0b0e32c2129c08c8bcdcf66fb8ab9ae2ee7c37f204415b50fb0608c23f488acd`.
- BIN SHA256 `0d99ecafcb570c39217aa39723ccfcf593ae2021158599085a01436665374bc7`.
- devmem release Manifest SHA256 `4e33fee583611f70c60d30f971cc8499c165486b4621119a6b219da6fd3f1d78`
  (`pl/hil/releases/swd-independent-d0add58c/`).

The exact HWH and release Manifest are retained as CI fixtures
(`pl/tests/fixtures/swd-independent-d0add58c/`). The Host-only verifier checks
their bytes and topology. The BIT/BIN digests are pinned provenance from the
Vivado run; these large files are not bundled. An SHA match does not prove live
FPGA configuration. (Z2 HIL 2026-11-03: B3 IDENTITY_PASS and Blue Pill Flash
PASS on Site 2, see the runbook §9.)

Historical: `bd976140` (PR #1255 sample-point fix, run 41469421780, BIN
`19143158…`) was the audited Image from 2026-11-02 until PR #1285; its geometry
is identical. The first audit (this document's original version) used
`ab79b04efb2c38401103876043e39d4745284163` (Draft PR #1189, HWH `5309c05b…`,
BIN `d3b65a81…`, uio-variant Manifest `b3a3643f…`). That Image is no longer
trusted anywhere.

## Address contract and the SIGBUS

The HWH has exactly two PS7 GP0 AXI MEMRANGEs: Site 1
`0x43C01000..0x43C01FFF` and Site 2 `0x43C02000..0x43C02FFF`.
The first word of each Site is respectively `0x00050001` and `0x00050002`.
There is no Global Identity AXI slave at `0x43C00000`. That address must
never be probed as Identity for this Image. The Host-only Manifest's
`identity_words` offsets 0 and 4096 are relative to `axi_base=0x43C01000`,
not `owner_base=0x43C00000`. `fpga_image_root.read_identity` already uses
`axi_base + offset`; its address calculation is preserved and covered by a
regression test. The original command or diagnostic that caused the reported
ARM External Abort was not present in current main, Draft #1189 or the
retained build package, so its precise call site is unverified. Any such
external diagnostic must use this Image's admitted Site address, after owner
admission, and must not retry the faulting `0x43C00000` read.

## Linux owner and admission

The original (retired ab79b04e) Host-only Manifest assumed `uio1` covers `0x43C00000/64KiB`.
The reported Z2 state instead maps `uio0` to `43c00000.audio-codec-ctrl` and
`uio1` to `40000000.fabric`. This is a **kernel-resource observation**, not
proof that `audio-codec-ctrl` owns the SWD IP or is available to the Driver.
The original Manifest remains a historical fixture and is **not** a corrected,
deployable Manifest. The exact `0x43C01000/8KiB` extent is preferable if a
reviewed Device Tree can expose it, but engineering `/dev/mem` does not
automatically require changing Device Tree or Kernel Driver.

For a future reviewed Manifest, Root accepts an exact `expected_uio` shape
with `platform_node`, `driver`, `maps`, and `runtime`, omitting `uio_name`.
Root discovers the unique matching UIO device at runtime and checks its
physical map, driver, platform overlap, process census, manager provenance,
Boot ID, image and Golden hashes. Legacy manifests retain their exact UIO
index rule. The new shape does not claim that a suitable Device Tree node
already exists. Without an exact, uniquely admitted platform owner or the
explicitly audited engineering `/dev/mem` contract below, MMIO admission
fails closed.

### Explicit controlled `/dev/mem` engineering alternative

Root also accepts an **opt-in** `expected_uio` shape with a literal
`"backend": "devmem"`, `platform_node`, `driver`, `maps` and `runtime`, but
only for the exact SHA-pinned independent ABI-v5 Image. The name
`expected_uio` is retained for compatibility: its fields report the
**conflicting kernel resource** to audit, not a UIO index used for I/O and
not proof of SWD IP ownership. Example **only if the live Z2 facts confirm
every item**:

```json
{
  "backend": "devmem",
  "platform_node": "43c00000.audio-codec-ctrl",
  "driver": "uio_pdrv_genirq",
  "maps": [[1136656384, 65536]],
  "runtime": "suspended"
}
```

Omit `uio_name` from such a Manifest. Keep `owner_base` and `owner_bytes`
at the actual resource extent (`0x43C00000/0x10000` in this example), but
**never** read Identity from `owner_base`. The two read addresses remain
`0x43C01000` and `0x43C02000` and must match the pinned HWH/firmware.
This example is not a deployed release or a waiver based on `audio-codec`
being the enclosing address. The manifest must be root-owned/protected;
Root must verify the exact platform node, UIO class link, driver, resource
extent, power/runtime state, exclusive process census, Boot ID, loaded
Image provenance and Golden hash on the real board before `/dev/mem` opens.
Any competing user of `/dev/uio*`, `/dev/mem` or the PL resources denies
the test. The Image download has its separate G1–G4 gate and is not blocked
by UIO ordinal changes.

For the Root `test` identity child, the parent now passes its already-held
exclusive FPGA reload-fence file descriptor to a bounded subprocess. The
child validates that this FD matches the protected canonical lock inode;
it must not reopen and contend with the parent's `flock`. The only permitted
mapping is a read-only `0x43C01000/8KiB` AXI aperture with two allowlisted
Identity words. An independent process cannot take the Root's lock while
this validation runs. Both reads, however, remain **NOT_RUN on real ARMv7**.

The historical Root Manifest parser alone checks geometry and values; the
Independent SWD Host-only verifier additionally binds its two identity
addresses to the exact HWH. Do not infer a Global Identity from a covering
UIO resource. Do not substitute the Fixed Unified PPU ABI, which is a
different Image architecture.

## Remaining hardware gap

The source-pinned `scripts/swd_abi5_path2_readonly_preflight.py` is a
**non-mutating** first Path 2 Work Order. Using the existing enrolled SSH
helper and pinned Z2 Bootstrap identity, it returns current Boot/Manager,
Kernel UIO/platform overlap, firmware/Golden digest and Root installation
facts. It intentionally does not run the protected process-consumer census,
authorize `/dev/mem`, load PL, touch AXI, control DUT or read DPIDR. Its
success means `PASS_READ_ONLY_FACTS_ONLY`, never HIL/Identity PASS. Stage
load/Root G5 and actual DPIDR require subsequent reviewed, source-pinned
steps and the live results from this first observation. No arbitrary
SSH/script selection or new generic transport is introduced.

Read-only DT/kernel ownership audit, a separately reviewed DT/driver change
**only if** live facts require it, current-boot owner and process
verification, source-pinned Root installation, ARMv7 MMIO/adapter
validation, electrical checks, and bounded Site Identity then Blue Pill
DPIDR HIL remain NOT_RUN in this Gate.
External SWD input/output timing is still not qualified by the old Build.
No new Bitstream is required to use the two existing Site Identity registers;
adding a Global Identity Slave would change the FPGA design and require a
new Vivado BIT/HWH/BIN/Manifest and revised architecture approval.
