# Blue Pill OpenOCD remote-bitbang → Z2 AXI / PMODB (Gate 1 Path 1)

**Status: independent Draft source-only candidate.** No BIT/HWH has been
built by this PR; no Vivado, FPGA load, physical target, SWD or Flash HIL PASS.
This branch starts from main `0c1cf9b434b96d7ade530e31344196cb8b86437e`
and imports 18 exact Git blobs from Draft PR #1126, excluding its stale
`docs/README.md`. This is a superseding/integration candidate, **not**
independent qualification of those copied modules. Never merge both PRs
without resolving the duplicate patches and doing a fresh delta review.

## Exact single-Site design

WEB /api/jobs → PS Protocol v3.3 / SiteWorker → opt-in real OpenOCD 0.12.0+dev
→ private UNIX socket → RemoteBitbangSWD → **qualified, injected Linux
word-port** → Zynq PS7 M_AXI_GP0 → `plasma_poc_swd_gpio_axi_lite`
→ `plasma_poc_swd_pmod` → PMODB JB. This design does not use EMIO GPIO
or the ST-LINK reference programmer; it does not replace the eight-Site
fixed PPU production ABI.

- Board: `xc7z020clg400-1`, pinned PYNQ-Z2 board files SHA
  `e02d6a3866b5465218f777168cdc51344ac94e07`.
- PS7: actual board preset, PS clock 50 MHz, FCLK0 100 MHz, GP0 only.
- Candidate AXI: `swd_0`, base `0x40008000`, 4 KiB;
  `0x00` ID/RO, `0x04` ABI/RO, `0x08` DRIVE/WO,
  `0x0C` SAMPLE/RO. Mapping must be checked against the **built HWH**.
- JB[0] W14 = SWCLK driven low after AXI reset; JB[1] Y14 = SWDIO
  via genuine IOBUF, where T=NOT(OE), Hi-Z on AXI reset.
  **NRST is absent and must not be assumed connected.**
- XDC is LVCMOS33 only. No voltage sensing, target power, level shifting,
  isolation, contention measurement or automatic power-off; never infer
  target safety from nominal 3.3V labels.

## Files and source-only verification

`create_project.tcl` and `create_block_design.tcl` are isolated from
legacy Z2 build trees and require existing pinned board files. The AXI map
must be exported to `pl/build/z2-bluepill-rbb/generated/`.
`build_bitstream.tcl` is an **offline manual Vivado candidate**, not
automatically executed. If executed in a separately approved host build,
review synth/impl/timing/DRC and require `verify_hwh.py` on actual HWH
and nonempty bitstream before any physical qualification claim.

`BluepillZ2WordPort` reuses `LinuxMMIO`, `SiteMMIO` and the SHA-pinned
`ARMv7DMBBarrier`. No `/dev/mem`, `/dev/uio`, FPGA Manager or service
is opened by its constructor. Site 1 must already be exclusively leased.
The host-test barrier is accepted **only for a regular-file fixture**.
On a real ARMv7, instruction-width/disassembly and mapping attributes
remain independently unqualified.

## Hardware Admission and original FPGA image recovery contract

An external trusted FPGA Configuration Owner is REQUIRED; no Job request,
environment variable, test flag or manifest alone grants authority.
Before opening the real MMIO port or driving PMODB, owner evidence must
bind an immutable candidate source commit + BIT/HWH hashes + boot/board
identity + exact GP0 range + physical pin map + valid target VTref/GND,
voltage ranges, board isolation and ownership + intended disposable
STM32F103C8T6 geometry. SWDIO/OE turnaround and clock edges must be
measured with a passive analyzer; NRST is not supported by this design.

A separately retained **original known-good FPGA image** with exact SHA,
restoration authority and method, rollback receipt, stop conditions,
and verified safe target disconnection is mandatory. On any admission
failure, ambiguous MMIO, SIGBUS, wrong pins, contention or lost owner:
**no retry, no more target access**, return to trusted root-executor
recovery; restore the original image and independently verify recovery.
This source-only PR never runs recovery or changes FPGA configuration.

### Evidence separation

- Host source/python/RTL tests = eligible for GitHub-hosted PASS.
- Vivado synth/impl/timing, generated BIT/HWH, ARMv7 actual store
  width and PS7→PL transactions = **NOT_RUN / pending artifacts**.
- SWPC, Z2 target voltage, LA SWCLK/SWDIO, target DPIDR, Flash
  Erase/Program/Readback Verify, CDC post-flash = **NOT_RUN**.
- Until all required real hardware and restoration evidence exists,
  Gate 2 readiness is **NO-GO**, the default runtime remains off, and
  this Draft must never be merged or deployed as qualified production SWD.
