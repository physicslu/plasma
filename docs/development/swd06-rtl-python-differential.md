# SWD-06 — SWD-05 Python Driver ↔ SWD-03 Real RTL Differential Co-simulation

**Scope:** Host-only, offline verification of the merged SWD-05 software
driver against **the original SWD-03 SystemVerilog implementation**.
SWD-04 Z2 HIL remains PENDING because the PYNQ-Z2 is powered off and
not physically accessible. No hardware loading, services, OpenOCD,
external SWD IO or programming action is authorized by these tests.

## Verification topology

```text
SWDTransactionDriver (merged SWD-05 Python code, synchronous)
    |
    | cocotb.external worker thread
    v
Explicit WordMMIO adapter
    |
    | cocotb.function callback, awaited in simulator thread
    v
AXIBench real AXI4-Lite Master BFM
    | AW/W/B, AR/R, BRESP/RRESP checks, response backpressure
    v
swd_transaction_axi_lite.sv (UNMODIFIED SWD-03 RTL)
    |
    v
swd_transaction_master.sv + swd_waveform_engine.sv
    | SWCLK/SWDIO/OE
    +--> swd03_dpidr_responder.sv (synthesizable fixture)
    |
    +--> VirtualSWDTarget (independent edge-level Python wire fixture)
```

**Critical distinction:** The Python SWD-05 driver is actually invoked,
and every `read32` or `write32` runs real AXI transactions in Icarus.
This is not another canned `FakeAXI` register state machine and not
a static source contract. We keep synthesizable and independent wire
fixture tests distinct; neither fixture is a production IC.

## Minimum Gate 1 acceptance

- SWD-05 ABI v1 initialization reads real `0x40003000`, does not
  change registers or invoke implicit reset.
- Line Reset through the AXI4-Lite command register changes real
  SWD link status; DPIDR Read returns `0x2BA01477`.
- Every START is acknowledged and consumed exactly once, with retained
  response META/data and AXI BRESP/RRESP checked by the BFM.
- Synthesizable fixture rejects unsupported DP reads/writes with FAULT,
  surfaced to the Python Driver. Do not treat FAULT or write OK as
  successful Flash programming.
- Independent wire-level target injects WAIT→WAIT→OK, WAIT_LIMIT,
  FAULT, read-data parity fault, then software-explicit line recovery;
  verify SWD ACK/attempt count and no software command replay.
- In-flight Python `request_abort()` is translated by the owner thread
  to AXI COMMAND ABORT. Real RTL reports ABORTED, response is consumed,
  then explicit line-reset and DPIDR recovery succeeds.
- Configure an intentionally insufficient SWD hardware FCLK timeout;
  verify real RTL returns TIMEOUT, does not trigger implicit software retry,
  and the caller can explicitly change timing, reset link and read DPIDR.
  Verify AXI SLVERR for an RTL read-only register write crosses the Cocotb
  bridge as an exception, rather than appearing to the driver as AXI OKAY.
- Simulators must exit cleanly; tests and CI must preserve a failing
  build/log. Do not weaken assertions to obtain green checks.
- SWD-03 existing Cocotb regressions and SWD-05 61 Python fake-MMIO
  tests must remain passing.

## CI and evidence

`pl/verification/test_swd06_rtl_python.py` launches an Icarus simulation
per Cocotb scenario; the new test module is
`pl/verification/cocotb/swd06_driver_cocotb.py`.
`.github/workflows/pl-swd06-differential.yml` installs the software
package, Icarus, Cocotb 1.9.2 and Cocotb-Test 0.2.6, runs all
new scenarios and retained SWD-03/SWD-05 regressions.

An explicit PASS from this workflow qualifies *host co-simulation of
the real SystemVerilog AXI/SWD transport with Python*; it is NOT
Vivado timing, PS AXI/DDR, electrical/PHY physical target, cross-process
MMIO lock ownership, production `FPGAInterface`, OpenOCD adapter,
multi-Site physical integration or IC programming. Real Z2 HIL requires
SWD-04 P0 and supervised restore/recovery.

## Gate boundaries

- Gate 1: approved in conversation for host differential design/tests.
- Gate 2: human approves merge after CI PASS and review.
- No third approval gate; no hardware operations are in SWD-06 scope.
- Do not modify SWD-03 RTL or change SWD-05 ABI semantics just to
  satisfy an incorrect test. Any necessary architectural change is
  a separate revised Gate 1 decision.
