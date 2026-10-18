# PLASMA Fixed PPU Unified 64KiB AXI4-Lite — Site 1 Gate 1

**REVIEW CANDIDATE — HOST-ONLY / M1 ARCHITECTURE FREEZE = NO-GO.**
Not a Vivado bitstream, Zynq PS AXI integration, real Kernel UIO/DevMem,
FPGA reload, DUT electrical circuit or approval to touch hardware.

## Deliverable and layout

The existing fixed-ABI Global Identity and SWD Site1 were separately tested
slaves. This Gate creates one simulation-only **top-level AXI4-Lite Slave**
`fixed_ppu_unified_axi_site1.sv`, with a single 64KiB register aperture
relative to reviewed Board Descriptor example `0x40000000`:

| Relative address | Routed to | Claim |
| --- | --- | --- |
| +0x0000–+0x0FFF | read-only Global Identity slave | real instantiated RTL, candidate v1 |
| +0x1000–+0x1FFF | read-only Global Health slave | real instantiated RTL, candidate v1 |
| +0x2000–+0x3FFF | no child | AXI SLVERR; reserved |
| +0x4000–+0x4FFF | Site1 SWD RTL | single physical *simulation* Site only |
| +0x5000–+0xBFFF | no child | AXI SLVERR; Site2–8 absent |
| +0xC000–+0xFFFF | no child | AXI SLVERR; reserved tail |
| Outside selected aperture | no child | AXI SLVERR |

Global Site Present is **0x01**. Site Ready and Fault are connected to
actual RTL output signals from SWD Site1, not synthetic constant inputs:
`site_ready_o = reset released && SWD_master_ready && !Site_active`;
`site_fault_o = fault_latched`; global readiness is not electrical DUT
Power/Reset assurance. Global Identity reports SWD capability only, no SPI
and no fabricated eight-Site or physical I/O claim.

## Router transaction safety

- AXI AW and W are **independent**. A one-slot channel pair captures AWADDR,
  WDATA and WSTRB separately, then irrevocably binds both to the same target
  before forwarding. A slow or missing W cannot cause AW data to be sent to
  the default child, and W-before-AW is accepted.
- The router forwards both child channels only for the pinned region;
  child AWREADY/WREADY handshake completion is tracked independently.
  Invalid region writes receive one held BVALID/SLVERR; **no child access**.
  Global RO writes reach only the Global slave and return SLVERR.
- At most one incomplete write and one incomplete read are supported. B and
  R responses are held stable by the child (or router-generated error) until
  the upstream BREADY/RREADY. External request backpressure does not change
  selected Site or response. Reset clears upstream pending AW, W and read
  transaction ownership in both router and children.
- The independent read AR routing state holds its selected child until R
  handshake. Reserved/absent/out-of-window/unaligned addresses never probe
  unbuilt Sites. Upstream must not access reserved physical AXI addresses on
  real hardware; invalid-vector tests are **simulation-only**.
- **Not a formal AXI compliance proof.** High throughput/AXI outstanding
  reordering, asynchronous clock-domain crossing, physical bus resets, slave
  hang and global timeout isolation remain unqualified. A hung child still
  can stall an AXI transaction; kernel/user safety cannot be inferred.

## End-to-end Host-only verification

`pl/verification/test_fixed_ppu_unified_axi_rtl.py` compiles unified router
+ Global Identity + fixed SWD Site1 + existing SWD transaction/waveform engines
with Icarus and Cocotb. The virtual target is from existing SWD-03 simulation,
not a physical external DUT. Directed cases include:

1. Identity/ABI/capabilities/bitmap readback using the **same external** AXI.
2. Reserved/out-of-window/error read and write, paired AW/W in either arrival
   order; one child cannot accidentally accept a transaction for another.
3. Host Python simulation Driver checks Site1 ABI, sends 64-clock Line Reset,
   reads virtual DPIDR `0x2BA01477`, reads DONE_SEQ/STATUS/ACK/metadata and
   confirms Global status/ready intact.
4. SWD timeout latches Site FAULT, propagates to Global Fault Bitmap, disables
   Site READY and blocks Site admission **even after matching ACK_SEQ**.
5. Standalone Global and SWD Cocotb regression and Host ABI/Admisson contract
   tests remain required in dedicated hosted CI.

## ABI doc consistency

Normative candidate remains JSON
`pl/verification/fixed_image_abi_v1_gate1.json`:
SWD Line Reset **64 active driven-high clocks** excluding the 64-clock Hi-Z
preamble; CLOCK_DIV means **SWD half-period FCLK cycles, 2..65535**;
`NEED_RESET=10`, `PHY_ERROR=11`, metadata at Site +0x06C and raw status
at Site +0x070. An older prose section containing 50..128 or CLOCK_DIV=1
must not override the current candidate machine contract.

## Gates / exclusions

**Gate 1 = software-only RTL and Host CI.** Gate 2 requires fresh explicit
owner authorization pinned to exact PR HEAD and latest main, mergeability
and completed GitHub CI. Do **not** merge or deploy from this Gate.
Legacy `pl_identity_axi_lite.sv`, legacy SWD-03, Dispatcher and PR #972
are not modified. No /dev/uio*, /dev/mem, Vivado RTL synthesis/build or
FPGA Manager Reload in this PR, and absolutely no Z2 or DUT hardware action.

**M1 remains NO-GO** pending complete PPU/SPI support, physical resource
admission, actual PS/PL bus connection, clock/resource/timing, electrical
power/reset safety, owner/broker provenance and independently scoped HIL.
