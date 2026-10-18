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
