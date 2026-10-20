# PYNQ-Z2 Fixed ABI Site1 PS7 integration

## Latest F1-B Gate 1 Host-only qualification — 2026-10-20

**PASS:** [new clean-build Run 39344221935](https://github.com/physicslu/plasma/actions/runs/39344221935) built exact source HEAD `00336106ad89eaa9fa0603dbe9e65024a27a6fe6` with Vivado 2026.1 from scratch. Synthesis, implementation, routing, bitstream generation, final DRC and methodology all PASS. WNS +1.829 ns, WHS +0.018 ns; TNS/THS zero, all twelve `check_timing` checks zero. HWH verifier passed on both original and delivered copies.

**Delivered binaries confirmed by independent hashing of the downloaded GitHub Artifact [12229639751](https://github.com/physicslu/plasma/actions/runs/39344221935/artifacts/12229639751):**

- `system_wrapper.bit` — 4,045,769 bytes, SHA256 `fdbde5c66999a9dab37339587d304b9c16e71a06f1890b24893c8391859cf075`
- `system.hwh` — 138,977 bytes, SHA256 `bf3690d69fefc8da3fc62964209776466894cd4353aec0a475b373257899ca76`

Full Vivado logs, reports, engineering root-cause ledger, manifests and verifier receipts are in the same Artifact. The previous missing-BIT/HWH upload problem is resolved. The 10 relevant GitHub-hosted CI workflows for the source HEAD passed; optional SWPC `pytest` did not execute because the system interpreter lacked pytest. This is **Host-only build acceptance**, not device-image load or product runtime acceptance. Physical Z2/HIL/DUT tests remain **NOT_RUN**, M1 **NO_GO**. PR #1064 Gate 2 merge still requires separate owner authorization.

## F1-B Host-only Vivado implementation — real SWPC run

**2026-10-20:** [Path 3 Run #39342622512](https://github.com/physicslu/plasma/actions/runs/39342622512)
ran Vivado 2026.1 build 6511674 on SWPC, using board-files commit
`e02d6a3866b5465218f777168cdc51344ac94e07`. Real synthesis,
implementation, routing and bitstream generation completed on attempt 03
(exit 0); existing HWH/artifact verifier exit 0, F1 host source contracts
22 passed. Reports independently recovered from Run Artifact
`12229802904`: routed setup slack +1.829 ns, hold slack
+0.018 ns; TNS and THS zero; final DRC and methodology reported zero
violations; all 12 check_timing categories were zero.

The first attempt failed at license discovery; the second identified
incorrect comparison of relative versus fully resolved Vivado BD pin paths.
Using `get_bd_pins` to resolve the expected FCLK and reset pins fixes
these two comparisons. No RTL/wiring changes or timing waivers were made.
See `docs/architecture/plasma-path2-fixed-host-build-capability.md` for
the dated problem/solution ledger.

**First-run historical evidence limitation (now resolved):** That run's
Artifact omitted the BIT/HWH raw files because they were stored under a hidden
evidence directory. The later Run 39344221935 independently built the
current corrected source and delivered verified raw binaries in its downloadable
GitHub Artifact, as recorded above. Physical image load and Z2 HIL remain
**NOT_RUN**, M1 **NO_GO**.

## Historical F1 source-only milestone

**State: HOST-ONLY Vivado project candidate; image BUILD/LOAD NOT_RUN; M1 NO_GO.**

This is a separate source-only PYNQ-Z2 integration candidate for the
already merged 64KiB unified FPGA ABI RTL. Do not substitute historical
PSPL-02, SWD-03, LT02 or PYNQ base.bin: they use different address/ABI contracts.

## What exists / what is missing

- Existing: LinuxMMIO native aligned 32-bit access and PYNQ-Z2 CONTROL/STATUS
  and LT02 2KiB real AXI HIL (including historical real recovery PASS).
- Existing: Real Cortex-A9 HIL-A2 1000 calls of exact SHA-pinned DMB SY.
- Existing: fixed unified 64KiB router, Global Identity, Site1 SWD
  synthesizable source RTL, simulated production controller/Cocotb.
- Missing: Vivado PS7→Fixed ABI image, real HWH/bitstream, implementation timing,
  kernel image ownership, actual image load and real Fixed ABI driver integration.
- The repository has no prior dedicated z2-fixed-unified-site1 Vivado build
  artifacts. SWPC-private work directories were NOT inspected in this Gate 1.

## Design contract

| Component | F1 source |
| --- | --- |
| PYNQ-Z2 board | xc7z020clg400-1; board part tul.com.tw:pynq-z2:part0:1.0 |
| Board files | reuse owner-pinned e02d6a3866b5465218f777168cdc51344ac94e07 (future Vivado build preflight) |
| PS7 AXI | GP0 master, exactly one 64KiB window 0x40000000..0x4000FFFF |
| Clock | 50MHz external board crystal, PS FCLK0 100MHz |
| Reset | PS FCLK_RESET0_N via rst_ps7_0_100M peripheral_aresetn |
| Site presence | RTL Site1 only, Sites2..8 physically absent |
| Programmable pins | None: only PS DDR/FIXED_IO external |
| Internal fixture | swd03_dpidr_responder only, connected to internal SWD nets |
| Excluded | external DUT/SWD pins, SPI, DUT power/OE/NRST, MMIO, FPGA Manager, JTAG and physical HIL |

Files:
- rtl/fixed_ppu_z2_internal_fixture_axi.sv: AXI4-Lite interface-decorated top
  with internal synthetic DPIDR fixture; ZERO external programmable pins.
- create_project.tcl: pinned board/part and exact seven synthesizable RTL files.
- create_block_design.tcl: applies PS preset; explicit GP0, 100MHz FCLK0 and
  synchronized reset; one 64KiB AXI region and no external PL IO.
- build_bitstream.tcl: future HOST Vivado synthesis, implementation,
  timing/DRC/methodology reports. It does not load FPGA or invoke PS7 init.
- verify_hwh.py: fail-closed inspection of a future actual implemented HWH,
  BIT and reports with hashes. Returning a candidate manifest is **not**
  actual Vivado or Z2 PASS.

## Gate 1 verification

Only the new GitHub-hosted workflow
.github/workflows/ppu-fixed-site1-f1-host.yml may run at this Gate.
It compiles the wrapper/top using Icarus, checks HWH XML synthetic mutations
(wrong decoder, five 4KiB legacy segments, clocks, reset, extra PL pins,
missing artifacts), and reruns the existing Unified Cocotb and four-module
host contracts. The synthetic HWH fixture is **never** claimed as a real HWH.

**Vivado 2026.1 BUILD = NOT_RUN**, no actual bitstream, no real HWH, no live
FPGA Manager or Z2 read/write, no SWPC/Codex dispatch, no LA, no DUT.
The build scripts are inert until a separate approved host-build scope.
Before any live MMIO: independently verify actual source/bit/hwh/BIN hashes,
exact board identity, image Build ID and current boot load receipt, physical
ownership, FCLK/reset and known-good original image and supervised recovery.
No invalid AXI offsets or auto-retry on real Z2.

## Next independent approvals

1. Separate approval for **isolated SWPC Vivado build** only, including pinned
   board files and reports; this does **not** authorize any hardware load.
2. Separately approved Z2 read-only FPGA image preflight and safety/recovery.
3. Separately approved one-shot real Site1 Driver→DMB→COMMAND HIL without DUT.

Gate 2 of this PR authorizes **Merge Commit only**, not step 1–3.
