# PLASMA Fixed FPGA v1 — Global Identity, UIO Resource and Broker Admission (Gate 1)

> **Candidate Host-only contract — M1 Architecture Freeze NO-GO.**
> Not a board image, production Linux UIO Driver, authenticated attestation,
> qualified Zynq-7020 implementation, or authorization to perform physical I/O.
> No FPGA Manager/Reload, /dev/mem, /dev/uio*, live DT/sysfs, DUT or deployment.

## Engineering decision

Do **not** repurpose legacy `pl_identity_axi_lite`: its MAGIC
(`0x504C534D`) and register offsets are incompatible with the full
fixed-image candidate (MAGIC `0x4D534C50`). The new independent
`fixed_fpga_ppu_global_identity_axi_lite.sv` is a **standalone AXI-Lite
simulation fixture**, not an addition to existing Z2 Vivado/HWH/FPGA images.

The new module decodes an example **64KiB PPU range at `0x40000000`**,
exposing RO Identity words in its +0x0000 block and global status words
in +0x1000. It **rejects the Site windows**, shared engine reservations,
out-of-window addresses and all writes. A future full PPU interconnect
must route +0x4000 to independent Site1 RTL, not let the Identity slave
absorb those accesses. Board physical base is selected only by a reviewed
Board Descriptor, never by REST or an arbitrary input file.

## Identity layout (PPU-relative byte offsets)

| Offset | Register | Candidate semantics |
| --- | --- | --- |
| +0x000 | MAGIC | `0x4D534C50`, not the legacy Identity magic |
| +0x004 | ABI_VERSION | major 1, minor 0 |
| +0x008..+0x014 | IMAGE_ID_W0..W3 | 128-bit image UUID convention, externally pinned |
| +0x018..+0x024 | BUILD_ID_W0..W3 | Build diagnostic, not a digest or attestation |
| +0x028/+0x02C | CAPABILITIES_LO/HI | Capability bits: SWD=0, SPI=1; unimplemented must be zero |
| +0x030/+0x034 | SITE_PRESENT/READY | Present is statically instantiated mask; READY dynamically masked by PRESENT and FAULT |
| +0x038/+0x040 | PPU_STATUS/ERROR | PL-ready bit0 and any fault bit1; ERROR reports fault |
| +0x03C/+0x044 | HW_REVISION/MAP_REVISION | exact board/revision pin, map rev=1 |
| +0x048/+0x04C | SITE_STRIDE/MAX_TRANSFER_BITS | 4096 and implemented transfer bound |
| +0x050 | RESET_CAUSE | currently zero: no trusted reset-cause provenance |
| +0x1000 | GLOBAL_STATUS | mirrors PL-ready/fault for this simulation |
| +0x1004/+0x1008 | FAULT_SITE_BITMAP/GLOBAL_EVENT | reported faults and diagnostic event bitmap |
| +0x100C | BROKER_EPOCH_HINT | zero (unavailable); Host broker epoch remains authoritative |

RTL read and write addresses are fully decoded. Little-endian
32-bit alignment is mandatory. Inputs `site_ready_i`, `site_fault_i`,
and `pl_ready_i` are **simulation wires**; their correctness and clock
domain crossings remain future RTL integration requirements. Example
Image/Build IDs and Site1 availability are synthetic default parameters.
Do not load this module into physical PL using those values.

## Pure Host Admission contract

Source: `pl/tools/fixed_ppu_global_admission_host.py`.
Machine schema:
`pl/verification/fixed_ppu_board_descriptor_host_v1.schema.json`.
Fixture:
`pl/verification/examples/fixed_ppu_board_descriptor_synthetic.json`.

1. **Descriptor checks:** fixed-image boot-only policy, reviewed SoC/Board,
   boot ID, owner epoch, generation, SHA256-format artifact-source/manifest
   expectations, EXACT UIO map0 64KiB physical resource and one unique
   driver/platform/label binding. Reject unknown fields.
2. **UIO discovery:** use synthetic UIO inventory, identify uniquely by
   resource and driver, **never pin uio0/uio1 ordinal**. Deny overlap,
   resource drift, invalid/duplicate UIO names. No sysfs/char device read.
3. **PPU register snapshot:** compare v1 MAGIC, exact major/minor, Image ID,
   Build ID, capabilities, Site present mask, physical hardware revision,
   map revision, site stride and max transfer bound. Confirm READY is a
   subset of PRESENT and excludes FAULT; PPU and Global status consistent.
   Deny global faults and absent/unknown PL-ready. A Site not READY may
   never be claimed.
4. **Broker model:** a HostAdmission receipt has explicit
   `hardware_authority=False`, unique descriptor fingerprint,
   boot/owner epoch, generation, and approved Site masks. Exclusive Site
   lease per Site; one Batch and one **canonical exact IC** at a time;
   1..8 Site leases possible only when the snapshot actually advertises
   those Sites. Threaded claims serialized with a lock, stale epoch
   or generation refused.
5. **No hardware access:** the Host-only functions are pure with synthetic
   snapshots; they do not open files or call MMIO. Firmware data/profiles,
   Site Power/Reset/OE, physical Broker IPC, Kernel Device memory ordering,
   actual FPGA Manager/provisioning remain outside this Gate.

## Authentication boundary that M1 must not ignore

A readable UUID, Build ID and source/image SHA256 **strings do not prove**
that the physical FPGA currently runs the approved bitstream. The
descriptor fingerprint is not a cryptographic signature. A separate
verified source artifact, bitstream hash, signed/reviewed provisioning
receipt, Kernel/DT resource provenance and firmware-loader lifecycle
are needed before any live programming authority. A vulnerable process
could forge synthetic register values: the Host tests prove contract
consistency, **not authenticity**.

## Evidence and separate gates

- Host-only Icarus/Cocotb: 21 Identity registers and four global status
  registers; AXI4-Lite split AW/W, stalls, reserved/unaligned/out-of-window
  denial, reset response cleanup, Site fault masking.
- Host-only Python: descriptor/schema, legacy-MAGIC rejection, image and
  capability mismatch, UIO ordinal changes/overlaps/drift, ready/fault,
  stale owner epoch, mixed Batch/IC, independent Site1/Site2 fixtures,
  threaded lease competition.
- Existing SWD-03/Legacy Identity and UIO Host-only CI must remain green.
- **M1 remains NO-GO**: no real v1 bitstream, full 64KiB interconnect,
  live UIO, electrical safe IO, image provenance, physical 2/8 Site
  isolation, resource/timing results or real HIL. Gate 2 separately
  requires latest pinned HEAD/main, all relevant CI PASS, mergeability.

Do not claim that a successful simulation represents a Z2 physical
Identity readback or a production-ready Firmware Programmer.
