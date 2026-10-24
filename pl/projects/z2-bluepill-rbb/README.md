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

## 2026-10-24 Gate 1 Path 1 — Blue Pill Protected Stage (Host-only)

**Exact-source image evidence:** SWPC Path 3 Run
[#40090390292](https://github.com/physicslu/plasma/actions/runs/40090390292)
built the actual BIT/HWH/BIN for the **immutable input source**
`65555410f171e425e61d87ebd42dc4709755f389`, with Vivado 2026.1,
GP0/FCLK0 100 MHz in generated HWH, WNS +3.070 ns, WHS +0.072 ns and
zero blocking DRC. The authentic artifact is
[#12558474564](https://github.com/physicslu/plasma/actions/runs/40090390292/artifacts/12558474564).
Three TIMING-18 external pin timing warnings remain **NOT_QUALIFIED**.

**Important image identity boundary:** the new Protected Stage source/test
commits change PR #1142 HEAD beyond that image's input source commit.
The historical BIT/HWH/BIN may still be evidence of the *old* design, but
are **not an exact-source build for the current PR HEAD**. A newly authorized
SWPC Vivado build and independent artifact SHA256/metadata review are
required before considering the latest source for any Z2 deployment. Do
not silently rewrite build manifest or treat an unchanged RTL diff as
equivalent qualification.

`pl/hil/bluepill_protected_stage.py` is the **Blue Pill-specific pure
Host-only policy/transition model**, with tests in
`pl/tests/test_bluepill_protected_stage.py`.
It deliberately does not import F1-B's accepted development UIO exception,
does not install or call the trusted generic Root Entry, and cannot open
FPGA Manager, MMIO, sockets, USB, SWD or any external target. The CLI
entrypoint always exits nonzero with
`BLUEPILL_LIVE_STAGE_BACKEND_NOT_IMPLEMENTED`; **no authentic
`PLASMA_PATH2_STAGE=` receipt is emitted**.

- Lock model: exact 40-hex reviewed/installed/image-build Source SHA
  must all match; host-only BIT/HWH/BIN/original bytes must match
  independent SHA256 pins. Strings or mocked SHA alone never prove an
  installed root-owned immutable image.
- Simulated preflight: exact Board, current-boot ID, FPGA Manager identity,
  recovery/candidate hash, GP0 base `0x40008000` / 4 KiB, FCLK0 100 MHz,
  W14/Y14 pin assignment, isolated AXI, no conflicting consumers,
  exclusive owner, independently retained recovery and safe disconnected
  external PMOD. Synthetic positive fixtures are never hardware
  admission; unknown evidence fails closed.
- Three independent Host-only Stage plans: `download` (BASE→HELD),
  `test` (HELD→read-only ABI identity, no Flash/SWD output), `restore`
  (HELD→BASE or verified no-op). After-state checks enforce the exact
  image/boot and read-only `MAGIC`/`ABI`/SWDIO Hi-Z sample; failures
  or in-flight/UNKNOWN state require an independently qualified manual
  recovery path. The model emits only `SIMULATED_*` receipts with
  `real_z2=false` and `runtime_admitted=false`.
- The production-grade owner/auditor, actual installed root-owned
  source/manifest/profile, FPGA Manager transition journaling,
  AXI isolation/drain proof, actual ARMv7 MMIO/ABI, and independently
  restored original image remain **NOT_IMPLEMENTED / NOT_RUN** for
  Blue Pill. No live `download/test/restore` adapter is authorized.
  Current kernel-specific isolation is still unproven; F1-B waiver is
  explicitly not transferable.

The user confirms the existing breadboard, Blue Pill and LA2016 have been
wired for a previously successful **SWPC/ST-LINK reference SWD** observation.
**Pmod BB J1 remains DISCONNECTED from Z2 JB**, and must stay disconnected
until an explicit, separately reviewed physical-connection instruction.
Before changing the SWD master, ST-LINK output must not contend with Z2;
no PMOD 3.3 V feed, NRST remains unconnected and passive LA/electrical
checks precede real DPIDR. Nothing in this Gate 1 operates SWPC, Z2,
ST-LINK, LA2016, FPGA Manager, MMIO, Blue Pill, USB or DUT; PR remains
Draft, unmerged, Gate 2/HIL **NO-GO**.

## First-generation universal architecture alignment (Gate 1, Host-only)

**Status: generic source policy only; NO physical Universal Image qualification.**
The [ADR-0003 first-generation fixed-image amendment](../../../docs/adr/0003-runtime-fpga-driver-reconfiguration-boundary.md)
is **Proposed / M1 NO-GO**, not Accepted. It aims for **one fixed
Universal FPGA Image** during normal multi-Site programming (eventual
eight-Site SWD/SPI capacity), with IC/profile/algorithm/provider selection
performed in the PS/software data plane. The normal Programming Job
`Probe / Erase / Program / Read / Verify` **must not** write FPGA
Manager firmware or trigger a new FPGA image.

The established generic protected Root Entry and project-aware Stage
Transport live on the **latest main**, from merged PR #1143. Do not
recreate them in this branch. Because the #1142 branch forked before
that merge, its old F1-B-only transport must **never** be used as
Blue Pill production authority; first synchronize with latest main in
a separately reviewed, non-force step.

The new `pl/hil/fpga_configuration_policy.py` is the **shared,
hardware-inert** maintenance/provisioning image-source lock, SHA256
bundle validator and independent `download → read-only identity test →
restore` state policy. It is not an IC-specific engine, a root-capable
backend or a normal Job workflow; live CLI invocation fails with exit
2 and no trusted root receipt. `bluepill_protected_stage.py` is
only the Site 1 PYNQ-Z2 PS/PL SWD GPIO *PoC adapter* using this shared
policy; its `W14/Y14`, `0x40008000`/4KiB, GPIO identity and safe
IOBUF reset state are **evidence for this one FPGA image**, not the
canonical Universal Image or product eight-Site ABI.

The common SWD Provider is target-agnostic; Blue Pill STM32F103C8T6
is only the first physical DUT and its expected SWD DPIDR is not
hardcoded as a general provider qualification. Later ST, NXP,
Microchip and other ICs use per-exact-part applicability, target probe,
Flash geometry and algorithms, not separate FPGA configuration Stages.
No target family can inherit a historical F1-B risk waiver.

Source-only regressions:
`pl/tests/test_fpga_configuration_policy.py` covers multiple Projects,
exact source and original-image hashes, invalid transitions and
**rejects normal IC Job operations as FPGA reload triggers**.
The existing `pl/tests/test_bluepill_protected_stage.py` continues
to test the PoC-specific GPIO/IOBUF preflight and fail-closed
simulated stage results. Host-only booleans and image hashes do
**not** prove root permissions, AXI isolation/drain, image attestation,
real MMIO readback or successful restoration.

The last physically synthesized BIT/HWH/BIN belong *only* to source
SHA `65555410f171e425e61d87ebd42dc4709755f389`,
SWPC Run #40090390292. These policy/document/test changes make a
**newer PR HEAD, without an exact-source Vivado rebuild**. Preserve the
old evidence without promoting it to latest-head Image PASS.

The prototype remains **one Site** and is not electrically or
functionally a qualified eight-Site Universal Image. Hardware
configuration/load/rollback and external SWD remain NOT_RUN; current
Pmod BB J1 remains disconnected from Z2, and no owner-approved real
FPGA Manager, Z2, MMIO, SWPC or DUT work occurs in this change.
