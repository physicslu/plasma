# Blue Pill OpenOCD remote-bitbang → Z2 AXI / PMODB (Gate 1 Path 1)

**Status: independent Draft offline-image candidate.** The owner-approved
SWPC Path 3 Vivado 2026.1 offline build on source HEAD
`6feaa8842f0a92e34030e281f4455a9447fe46b2` passed on Run
[#40087670192](https://github.com/physicslu/plasma/actions/runs/40087670192),
producing BIT/HWH/BIN with independently checked SHA256 and internal 100 MHz
timing. This is historical evidence for **that exact source revision** only.
A source change requires a fresh build and new artifact identities.
No FPGA load, physical target, SWD or Flash HIL PASS exists.
This branch starts from main `0c1cf9b434b96d7ade530e31344196cb8b86437e`
and selectively reuses only the direct SWD bridge, OpenOCD source
build, RTL, protocol tests and low-level configuration from Draft PR #1126.
WEB-specific Job/REST implementation remains solely in Draft PR #1126.
This candidate is **not** independent qualification of reused code; merging
must resolve duplication and revalidate latest main delta.

## Direct PS → PL SWD first (WEB explicitly deferred)

Engineering execution order is now **direct PS/PL SWD**, *not* WEB
`/api/jobs`: Z2 Linux PS → existing owner-admitted native word-port →
PS7 GP0 AXI GPIO → PMODB JB[0]/JB[1] → STM32F103C8T6.
The host workflow tests upstream real OpenOCD against a separate virtual
SWD target, plus actual RTL simulation and native regular-file word-port
contracts. This deliberately does not execute the WEB admission, WEB Job
or WEB-to-OpenOCD test cases. Their earlier evidence is historical only.

The physical HIL sequence is staged: first prove trusted Z2 boot and PS/PL
BIT/HWH/source identity with the original FPGA image recoverable; then
independently confirm VTref/GND and SWDIO turnaround, directly read a real
Blue Pill DPIDR via PS/PL, and only then consider a bounded owner-authorized
Flash erase/program/readback SHA256 compare. **Do not erase or modify a
connected chip without a separately reviewed physical admission and the
current hardware scope.** The existing Gate 1 explicitly forbids loading
FPGA, SWPC/Z2/Blue Pill operation or Flash writing. Any such activity is a
material scope change requiring revised Gate 1 approval under AGENTS.md.

## Exact single-Site design

Z2 Linux PS → explicitly authorized real OpenOCD 0.12.0+dev
→ private UNIX socket → RemoteBitbangSWD → **owner-qualified, injected Linux
word-port** → Zynq PS7 M_AXI_GP0 → `plasma_poc_swd_gpio_axi_lite`
→ `plasma_poc_swd_pmod` → PMODB JB.
The direct path currently has source/test primitives, not a proven
hardware-admitted PS launch, production Flash executor, or Z2 HIL receipt.
The WEB /api/jobs → SiteWorker integration is deferred and is NOT
part of direct PS/PL acceptance. This design does not use EMIO GPIO
or the ST-LINK reference programmer; it does not replace the eight-Site
fixed PPU production ABI.

- Board: `xc7z020clg400-1`, pinned PYNQ-Z2 board files SHA
  `e02d6a3866b5465218f777168cdc51344ac94e07`.
- PS7: board preset crystal 50 MHz, FCLK0 100 MHz, M_AXI_GP0_ACLK on
  FCLK0 and PS7 `PCW_M_AXI_GP0_FREQMHZ=100`, GP0 only. The first
  offline build's HWH had 10 MHz GP0 parameter metadata despite a routed
  100 MHz ACLK; the reviewed source now rejects that mismatch. A new
  Vivado build must verify the corrected HWH before this revision is admissible.
- Candidate AXI: `swd_0`, base `0x40008000`, 4 KiB;
  `0x00` ID/RO, `0x04` ABI/RO, `0x08` DRIVE/WO,
  `0x0C` SAMPLE/RO. Mapping must be checked against the **built HWH**.
- JB[0] W14 = SWCLK driven low after AXI reset; JB[1] Y14 = SWDIO
  via genuine IOBUF, where T=NOT(OE), Hi-Z on AXI reset.
  **NRST is absent and must not be assumed connected.**
- The first offline timing report has three TIMING-18 methodology warnings:
  missing external SWDIO input delay and SWCLK/SWDIO output delays. Internal
  100 MHz timing PASS does not qualify external SWD edges or turnaround.
  Do not invent timing exceptions, virtual clocks or board delay values to
  silence warnings; qualify external edge timing and target setup/turnaround
  when the physical target/wiring is actually measured.
- XDC is LVCMOS33 only. No voltage sensing, target power, level shifting,
  isolation, contention measurement or automatic power-off; never infer
  target safety from nominal 3.3V labels.

## Files and source-only verification

`create_project.tcl` and `create_block_design.tcl` are isolated from
legacy Z2 build trees and require existing pinned board files. The AXI map
must be exported to `pl/build/z2-bluepill-rbb/generated/`.
`build_bitstream.tcl` is an **offline manual Vivado candidate**, not
automatically executed. If executed in a separately approved host build,
review synth/impl/timing/DRC; the source build recipe now refuses to
emit its success sentinel unless actual generated BIT/HWH are nonempty,
the `verify_hwh.py` GP0/PS7/IO contract passes, and a candidate JSON receipt
containing BIT/HWH SHA256 is written. Such offline evidence **does not**
prove bitstream↔handoff equivalence, runtime safety or physical HIL.

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
- Vivado synth/impl/timing, BIT/HWH/BIN = **historical offline PASS at
  exact source 6feaa884**; revised GP0-clock-metadata source build PENDING.
  ARMv7 actual store width and PS7→PL transactions = **NOT_RUN**.
- SWPC offline Build = **historical PASS**; Z2 target voltage, LA SWCLK/SWDIO, target DPIDR, Flash
  Erase/Program/Readback Verify, CDC post-flash = **NOT_RUN**.
- Until all required real hardware and restoration evidence exists,
  Gate 2 readiness is **NO-GO**, the default runtime remains off, and
  this Draft must never be merged or deployed as qualified production SWD.

## 2026-10-24 SWPC clock propagation diagnosis (Run #40089418642)

[Run #40089418642](https://github.com/physicslu/plasma/actions/runs/40089418642)
completed its dispatcher / Codex process, but its **exact input source SHA
`37a5c112e862ff99fb307f1061330597628d4bbe` was FAIL / NO-GO**:
Vivado `BD 41-737` rejected writing read-only PS7
`PCW_M_AXI_GP0_FREQMHZ` as a user value; synthesis was NOT_RUN for that exact
source.

The isolated, **uncommitted repair snapshot** used
`CONFIG.PCW_M_AXI_GP0_FREQMHZ.VALUE_SRC PROPAGATED` before
`validate_bd_design` and then asserted the derived value was 100 MHz.
Real isolated Vivado Synthesis / Implementation / BIT-HWH / Bootgen BIN passed.
That HWH reported both FCLK0 and M_AXI_GP0_ACLK at 100000000 Hz; internal
WNS +3.070 ns, WHS +0.072 ns, blocking DRC 0. The generated revised-snapshot
BIT/HWH/BIN are bound by the Run's artifact manifest, **not** admitted as
bitstreams built from any subsequently committed source SHA.

The repaired Tcl and source tests were then committed to this Draft. A new
SWPC image build against the precise resulting PR HEAD is still required for
formal image-source binding. Three `TIMING-18` external SWD timing warnings
remain **NOT_QUALIFIED**: without measured board/target timing, no guessed
I/O delays or false-path exceptions may be introduced. Z2 FPGA load,
protected Restore, PMODB connection, Blue Pill DPIDR and Flash stay NOT_RUN.
