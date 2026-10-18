# PLASMA V2 — PS Driver → AXI BFM → Real PL RTL (Gate 1)

**Classification:** Host-only verification increment. **M1 remains NO-GO.**
No Vivado, SWPC, Z2, FPGA reload, real UIO/MMIO, physical DUT, power
or hardware operations are authorized by this change.

## Existing pathways are not interchangeable

- **Legacy SWD-06:** production Python SWDTransactionDriver reaches
  real SWD-03 SystemVerilog via the Cocotb AXI/MMIO bridge. Existing
  regressions cover DPIDR, WAIT, FAULT, PARITY, ABORT and TIMEOUT.
- **Fixed ABI v1 Site 1:** candidate fixed-image RTL is driven by
  FixedSWDSiteSimDriver, which is a **simulation-only** driver, not
  the production Linux/UIO driver. The fixed ABI register map and
  result semantics differ from legacy SWD-03.

SWD-06 therefore does not prove fixed ABI v1 production-driver parity.

## Added real RTL scenarios

| Scenario | Real RTL evidence | Driver behavior |
| --- | --- | --- |
| Short FCLK timeout | TIMEOUT and sticky Site FAULT remain after matching ACK_SEQ | Poison owner, refuse silent retry |
| Partial WSTRB on SEQUENCE | AXI SLVERR, Site remains IDLE with zero transactions | Poison driver before COMMAND write |

These scenarios use real simulated RTL, not a fabricated register backend.
An AXI WSTRB error in simulation does not prove ARMv7 instruction width,
Linux mmap attributes, memory ordering, or actual PS7 interconnect behavior.

## Automated verification lane

- Runner: GitHub-hosted Ubuntu 24.04 (not SWPC).
- Python: 3.12.
- pytest: 8.4.2; Cocotb: 1.9.2; cocotb-test: 0.2.6.
- Icarus Verilog: installed from Ubuntu apt; exact distro package version
  remains unpinned and must not be described as hermetically reproducible.
- Existing workflow: .github/workflows/ppu-fixed-swd-site1-rtl-host.yml.
- Existing runner: pl/verification/test_fixed_fpga_swd_site_rtl.py.
- Existing retained checks: fixed ABI JSON contract and Site source tests.

## Gate 1 acceptance and exclusions

PASS requires both new Cocotb tests, retained DPIDR and strict AXI
cases, and the existing fixed ABI contract checks to pass. Report
the exact PR HEAD SHA and CI status before asking for Gate 2.

This change does not edit candidate Site-1 RTL, SWD-03 RTL, register
offsets, fixed ABI JSON, firmware, UIO, FPGA Manager, or Board Descriptor.
It does not claim eight physically instantiated sites or production
fixed-ABI driver qualification. No merge is authorized by Gate 1.

## Next design prerequisite

Qualify an injectable **production fixed-ABI v1 PS control driver**
with read32/write32 backend interfaces, then execute that same driver
against the real fixed-ABI Site RTL via a Cocotb AXI BFM. Only after
the eight physical engine instances exist can true eight-Site
parallelism and per-Site fault isolation be qualified in RTL.

Real ARMv7 MMIO width/barriers, XSim/Vivado and Z2 HIL need their own
separate authorization and verification evidence.

## Follow-up Gate 1 — Production fixed-ABI control code over real RTL

The original Gate 1 above qualified a **simulation-only driver**. The
follow-up user-approved Gate 1 introduces:

- `software/python/plasma_interfaces/fixed_abi_swd.py`:
  transport-neutral **production PS control logic** for fixed ABI v1;
  one owned Site; exact identity/capability preflight; serialized
  command sequencing; explicit write_barrier before COMMAND; dual DONE_SEQ
  snapshot; metadata validation; matching ACK; fail-closed ambiguous I/O;
  no auto-retry or in-band recovery.
- `software/python/tests/test_fixed_abi_swd_control.py`: fast Host-only
  negative contracts for ordering, identity, bad arguments, stale
  completion, partial-store rejection and sticky fault.
- `pl/verification/cocotb/test_fixed_fpga_swd_site_axi.py`: three
  additional Cocotb scenarios that call the **same synchronous production
  control class** from an external worker with `cocotb.function`
  callbacks: full AXI4-Lite AW/W/B and AR/R to the existing real RTL;
  successful line-reset + virtual DPIDR; RTL timeout/fault; partial
  WSTRB/SLVERR with no command launch.

### Controlled interface and limitations

Production **control algorithm** does not mean production **MMIO device
access is qualified**. The injected port requires read32, write32, and
write_barrier. The Cocotb port supplies a no-op in-order simulation
barrier; this does NOT prove an ARMv7/PS7/Kernel Device-memory ordering
barrier. Existing Host-only UIO backend refuses real character devices
and has not been integrated or authorized as a live port. Actual board
admission, mapped ownership, external DUT power/OE/NRST and real MMIO
are separate work requiring Gate approval.

Only the actual simulated Site 1 RTL is tested. The fixed-ABI v1 map
describes eight logical Sites but does not instantiate eight engines.
Hardware ABI fields, candidate RTL, M1 Freeze and Hardware Broker
admission rules remain unchanged. All tests run GitHub-hosted; SWPC,
Vivado, Z2, FPGA reload, DUT and deployment are excluded.

**Gate 2:** requires explicit owner approval after checking the exact
PR HEAD, CI PASS, mergeability and retained ABI contract coverage.
