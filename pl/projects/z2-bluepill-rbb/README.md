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

## 2026-10-24 Gate 1 — One Generic FPGA Configuration Stage + Image Descriptor

**Current architecture:** exactly one Host-only configuration Stage policy,
`pl/hil/fpga_configuration_policy.py`, with PYNQ-Z2 Site 1 SWD GPIO
specifics stored **only as data** in
`pl/projects/z2-bluepill-rbb/image-descriptor.json`.
There is **no `bluepill_protected_stage.py` and no separate Blue Pill
Root Executor**. This replaces the earlier two-module experiment.
The stage has no real hardware backend and direct execution exits 2
(`GENERIC_FPGA_CONFIGURATION_LIVE_BACKEND_NOT_IMPLEMENTED`) without a
`PLASMA_PATH2_STAGE=` receipt. `SIMULATED_*` outputs are *never*
hardware evidence.

The descriptor is **not** the final universal product image. It identifies
the exact one-Site experimental FPGA image: board `xc7z020clg400-1`,
PS7 GP0 `0x40008000`/4 KiB, FCLK0 100 MHz, W14 SWCLK, Y14 SWDIO,
and the 3 read-only identity/safe-IOBUF register expectations.
The historical SWPC Path 3 [Run #40090390292](https://github.com/physicslu/plasma/actions/runs/40090390292)
produced real BIT/HWH/BIN at exact source
`65555410f171e425e61d87ebd42dc4709755f389`, artifact
[#12558474564](https://github.com/physicslu/plasma/actions/runs/40090390292/artifacts/12558474564).
The artifact was downloaded and independently hashed:
- `system.bit` SHA256 `f2e59f31bacf6e8ab0ee9325a07125bc155647a261db3f84e67ba71bb0105891`;
- `system.hwh` SHA256 `84894ae5791a65ec16bd6146779faec4496d47833fd0ad294149d5c46571b510`;
- `system.bit.bin` SHA256 `bfbd3d872caeff05a8f9daa0829b6292e5b5036c6b927d6c779e13fe9ec1a1`.
This is **historical offline-image evidence**, not a source lock for
the newer current PR HEAD. A separately authorized actual Vivado
rebuild on the final source SHA is required before any physical image
admission. External `TIMING-18` SWD pin timing warnings remain
NOT_QUALIFIED.

The descriptor deliberately records `recovery_sha256: null`,
`runtime_admitted: false` and one physical Site. The generic Stage
**rejects use of this exact descriptor for stage planning**
(`RECOVERY_IMAGE_NOT_QUALIFIED`) until an independently reviewed
recovery image is locked; it cannot assert a synthetic boolean to turn
a real read-only image into an admitted hardware action.
Test fixtures may make a *synthetic copy* with fake hashes and
recovery to exercise the entire policy, but the original evidence
file stays unchanged and inadmissible.

**Root integration:** Latest `main` already contains the generic
Root Entry / project-aware Stage Transport from merged PR #1143.
Do not recreate or use #1142's outdated F1-B-only transport.
No Stage may be installed, invoked by the real root executor or
allowed access to FPGA Manager or MMIO without a separate qualified
AXI isolation/current-boot/owner/rollback admission and fresh
explicit hardware scope. Do not inherit F1-B's UIO risk exception.

**Universal fixed-image product boundary (ADR-0003 still Proposed,
M1 NO-GO):** FPGA configuration is maintenance/provisioning at PPU
level, never a normal per-IC programming Job. Selecting a different
ST/NXP/Microchip/other target or SWD/SPI profile must not imply
reloading the FPGA. The generic Stage rejects `probe`, `erase`,
`program`, `read`, `verify` and provider/IC switching as
FPGA configuration commands. The planned eight-Site Universal Image,
hardware capabilities and runtime Driver are not implemented by this
one-Site PoC.

Host-only verification files:
`pl/tests/test_fpga_configuration_policy.py` tests independent
generic Projects, source-locked image bytes and denial of image reload
from normal jobs; `pl/tests/test_fpga_image_descriptor_stage.py`
preserves the earlier 60 Blue Pill PoC negative/positive scenarios
under the *same generic Stage*, and verifies that incorrect/missing
descriptor/provenance and rollback evidence fail closed.
These tests cannot verify real AXI isolation, bitstream loaded-image
identity, OS privilege ownership, readback or physical recovery.

Physical boundary: The owner has a valid prior **SWPC + ST-LINK +
LA2016** reference SWD test. **Pmod BB J1 is not yet connected to
Z2 JB**. Do not connect or drive Z2 until separately authorized
hardware preflight. Never let ST-LINK and Z2 drive SWCLK/SWDIO
simultaneously. NRST remains unconnected. In this Path 1 no SWPC,
Z2, FPGA Manager, MMIO, ST-LINK, LA2016, USB or DUT was operated,
and no deployment or merge was performed. PR remains Draft;
Gate 2/HIL **NO-GO**.
