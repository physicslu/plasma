# Fixed ABI v1 — Gate 1A dual-Site host-only vertical slice

Status: **Development Mode / GitHub-hosted simulation only**. Neither the
current board bitstream nor physical Z2/SWPC installation includes Site2.
No timing, pin, electrical, real Linux MMIO or HIL sign-off is claimed.

## Scope and unchanged contracts

- The existing `fixed_ppu_unified_axi_site1` top and its regressions stay intact;
  `fixed_fpga_swd_site_axi_lite` gains a defaulted `SITE_ID=1` parameter only.
- The separate `fixed_ppu_unified_axi_dual_site` top instantiates **two real**
  copies of the SWD Site engine, each with separate SWDIO/SWCLK signals,
  command/completion/fault state and virtual SWD target. No eight-Site claim.
- The fixed 64-KiB AXI4-Lite window and ABI v1 registers do not change:

  | Window | Behavior |
  | --- | --- |
  | `PPU_BASE + 0x0000..0x1FFF` | RO Identity + Global, `SITE_PRESENT=0x03` |
  | `PPU_BASE + 0x2000..0x3FFF` | Reserved; `SLVERR` |
  | `PPU_BASE + 0x4000..0x4FFF` | Real SWD Site1, ID=1 |
  | `PPU_BASE + 0x5000..0x5FFF` | Real SWD Site2, ID=2 |
  | `PPU_BASE + 0x6000..0xFFFF` | Absent Site3..8/tail; `SLVERR` |

- `FixedABIHardwareDriver` is a protocol-neutral admission/routing boundary:
  explicit trusted board base, exact Image/Build IDs, ABI/capability/presence,
  ready/identity checks and per-Site 32-bit allowlists. It does not implement
  SWD policy. Each admitted `FixedABISitePort` is consumed by the **same**
  production `FixedABISWDController` used by the Site1 regression.
- Hardware identity words are simulation placeholders, **not** signed
  provenance; the owner/supervisor must independently authorize device,
  manifest, map and electrical/power state. No device path is opened here.
- Shared AXI transport accepts one read and one write at a time; Site
  engines themselves can run concurrently and retain independent faults.
  Host software bus serialization and controller Site-local locks are distinct.

## Acceptance and limitations

GitHub-hosted `ubuntu-24.04` extends the **existing**
`ppu-fixed-unified-axi-host.yml`; no self-hosted runner, dispatcher, workflow
or hardware resource is introduced.

| Check | Required observed evidence |
| --- | --- |
| Static | Verilator elaboration lint; `-Wall` currently also reports pre-existing intentionally unused AXI inputs, so no warning-clean claim |
| SIM-1 | Icarus/Cocotb actual dual RTL decode, bitmap=3, Site IDs, both engines simultaneously BUSY, distinct completion and virtual target resets |
| SIM-1 negative | missing Site3..8/reserved windows, global RO, unaligned addresses, split AW/W, partial WSTRB, invalid COMMAND |
| SIM-2 | `FixedABIHardwareDriver` + unmodified `FixedABISWDController` drive real AXI BFM and independent RTL/virtual-SWD paths; Site1 and Site2 DPIDR, bounded barriers and ACK |
| SIM-2 negative | Site1 TIMEOUT poison/sticky fault without poisoning Site2; Site2 bad WSTRB fail-closed before COMMAND, Site1 still usable |
| Host PS driver | Reject wrong/missing Image/Build, ABI/version, presence/ready, Site ID, capabilities, duplicate ownership, cross-Site writes, invalid widths and untrusted arguments |
| Regression | Unchanged original Site1 RTL, Global Identity, SWD and driver tests continue passing |

`pl.tools.verification_evidence` produces and validates a separate measured
`SIM-2` source-linked receipt and upload artifact for dual-Site closed loop.
The explicit SIM-1 step runs the dual RTL test suite as ordinary pytest.
The SIM-2 receipt re-runs the suite and binds the real RTL source list.

**Not in Gate 1A:** eight RTL Sites; SPI/JTAG; Linux `SiteMMIO` Site2 mapping;
ARMv7 access-width/DMB qualification of the new fixed ABI; Vivado synthesis,
timing, HWH, bitstream, pins, Z2/physical DUT; real power/NRST.
Host-only simulation passes cannot lift these stop conditions.

## Gate 2 readiness criteria

Retain the PR as Draft until exact HEAD, all relevant GitHub-hosted checks,
regression, review threads, protection rules and mergeability are reported.
No merge, deployment or hardware action is authorized by Gate 1A.
