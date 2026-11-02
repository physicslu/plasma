# Independent SWD v5 Image: Host-only hardware contract audit

Status: Host-only source contract. This document grants no Z2 MMIO, FPGA load,
Device Tree change, DUT operation or deployment authority.

## Pinned provenance

- Vivado 2026.1, project `pl/projects/z2-swd-independent`, source
  `ab79b04efb2c38401103876043e39d4745284163` (Draft PR #1189).
- BIT SHA256 `ac89d58b41bbfa1eafd4b51a389b7953186fc8e2ed8b1629bfc0a92f51797e88`.
- HWH SHA256 `5309c05beb8a17c9b13e8e2ba3d3c23d8264ca4adc38649bab6391e896577eb6`.
- BIN SHA256 `d3b65a818c03ef1f73a3f0026357d6ed6a9fd903f2f041bc09b89d6b6ba3b773`.
- Host-only Manifest SHA256 `b3a3643f46ac6eb861c288ae20dc78abe62852281709f1a5d94705acc1856669`.

The exact HWH and original Manifest are retained as CI fixtures. The Host-only
verifier checks their bytes and topology. The BIT/BIN digests are pinned
provenance from the SWPC Build and Bootgen receipt; these large files are not
bundled into this PR. Their bytes must be checked against the digests before
any future staging. An SHA match does not prove live FPGA configuration.

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

The original Host-only Manifest assumes `uio1` covers `0x43C00000/64KiB`.
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

Read-only DT/kernel ownership audit, a separately reviewed DT/driver change
**only if** live facts require it, current-boot owner and process
verification, source-pinned Root installation, ARMv7 MMIO/adapter
validation, electrical checks, and bounded Site Identity then Blue Pill
DPIDR HIL remain NOT_RUN in this Gate.
External SWD input/output timing is still not qualified by the old Build.
No new Bitstream is required to use the two existing Site Identity registers;
adding a Global Identity Slave would change the FPGA design and require a
new Vivado BIT/HWH/BIN/Manifest and revised architecture approval.
