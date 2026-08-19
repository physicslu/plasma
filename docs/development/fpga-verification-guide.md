# Plasma FPGA Verification Guide

> Scope: RTL functional, temporal, regression, and hardware-validation strategy  
> Updated: 2026-08-19

## 1. Verification goals

Plasma FPGA verification uses complementary layers:

```text
Python / cocotb / pytest
    -> functional behavior, transactions, randomized stimulus, reference models

SystemVerilog Assertions (SVA)
    -> cycle-level protocol, ordering, invariants, bounded timing, illegal states
```

Target flow:

```text
RTL change
   |
   +--> cocotb + pytest --> functional result checks
   |
   +--> SVA ------------> temporal/protocol checks
   |
   v
Regression
   |
   v
Synthesis / implementation / timing
   |
   v
Human deploy approval
   |
   v
Z2 hardware validation
```

These layers answer different questions and must not be collapsed into one generic "all tests passed" claim.

## 2. Site terminology and isolation

The independently controlled programming resource is a **Programming Site**. Verification for repeated programming resources therefore uses Site terminology:

```text
SITE 1 .. SITE N
```

Important invariants include:

- Site-local operations do not alter unrelated Site state;
- unrelated Sites may progress concurrently unless a real shared resource requires arbitration;
- Site-local cancel/abort does not cancel unrelated Sites;
- shared-resource arbitration preserves defined fairness/backpressure/safety behavior;
- host-visible Site selection maps to the intended hardware resource.

Use `channel` only for a genuine lower-level protocol/bus channel distinct from Programming Site identity.

## 3. Current repository status

At the current baseline, `pl/tests/` contains repository/source-layout pytest checks, not a complete production RTL simulator regression.

Therefore:

- do not claim cocotb regression exists until it is actually added;
- do not claim SVA coverage exists until assertion sources and a supporting simulator flow are configured;
- do not block documentation-only work on tools not yet selected/installed;
- add executable verification infrastructure together with the first production RTL that needs it.

## 4. Python-first functional verification

New production RTL should use `cocotb` as the primary active functional-test layer and `pytest` as the repository-level Python runner.

Typical responsibilities:

- clocks and resets;
- module-interface stimulus;
- protocol transactions;
- output/status checking;
- randomized stimulus;
- boundary/error cases;
- timeout behavior;
- back-to-back operations;
- multi-Site interleaving/concurrency when applicable;
- Python reference-model comparison;
- deterministic regression reporting.

A typical future test shape:

```python
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

@cocotb.test()
async def test_basic_transaction(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    dut.rst_n.value = 0
    for _ in range(2):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    # Drive one transaction and compare with expected behavior.
```

Exact APIs and simulator integration must be defined by the first real module, not copied blindly from an unrelated project.

## 5. Minimal HDL simulation harness

Python-first does not mean HDL-free. A minimal SystemVerilog harness is allowed for:

- top-level clock/interface wiring;
- vendor simulation primitives;
- interfaces awkward to expose directly to cocotb;
- SVA `bind` attachment;
- simulator-specific initialization;
- reusable structural wrappers around a production DUT.

Preferred separation:

```text
pl/rtl/                    production synthesizable design
pl/sim/                    minimal HDL harnesses
pl/verification/cocotb/    functional tests
pl/verification/sva/       temporal/protocol assertions
pl/verification/models/    Python reference/golden models
```

Keep the harness structural and small. Do not create a second functional verification framework in HDL without a concrete need.

## 6. SystemVerilog Assertions

SVA should capture rules most valuable to check at the exact cycle of failure. Good candidates include:

- request receives acknowledge/done within a bounded interval;
- `busy` and `idle` states are consistent;
- illegal FSM states are never entered;
- commands are not accepted while a block cannot accept them;
- signals remain stable through required protocol windows;
- write/read handshakes occur in legal order;
- clock/output toggling occurs only while an engine is active;
- reset returns architectural state to a legal condition;
- FIFO overflow/underflow is never requested;
- Site-local operations do not alter unrelated Site state.

Example:

```systemverilog
property request_completes;
    @(posedge clk)
    disable iff (!rst_n)
    request |-> ##[1:MAX_LATENCY] done;
endproperty

assert property (request_completes);
```

Do not treat example syntax as proof that the selected simulator supports the exact SVA features used.

## 7. Keep SVA out of production synthesis

Assertions should normally live in separate files, for example:

```text
pl/verification/sva/swd_engine_sva.sv
```

Use checker/bind style when appropriate. Verification assertion sources must not enter the production synthesis/bitstream source set unless an assertion is intentionally implemented as synthesizable debug hardware and that exception is explicitly designed/reviewed.

## 8. Simulator strategy

Do not assume one simulator is equally strong at every layer.

### Fast regression simulator

Desired properties:

- fast startup;
- command-line automation;
- cocotb integration;
- deterministic CI behavior;
- waveform output on failure;
- enough SystemVerilog support for production RTL.

### Assertion/sign-off simulator

If the fast simulator does not support an SVA feature used by Plasma, run that assertion set in a simulator that does. Vivado/XSIM is one integration candidate because the project already depends on Vivado for implementation; another simulator may be selected if it gives better automation/licensing/coverage.

Never mark an unsupported assertion as passed because the simulator ignored it.

## 9. pytest integration

The long-term goal is a predictable pytest-facing FPGA regression entry point while keeping simulator build details encapsulated.

Future examples may include:

```text
pl/verification/cocotb/test_site_controller.py
pl/verification/cocotb/test_swd_engine.py
pl/verification/cocotb/test_spi_engine.py
```

Do not document a command as supported before it exists. Once configured, CI and developer documentation must use the same entry point.

## 10. Reference and golden models

Python reference models are strongly recommended when expected behavior can be written more simply and independently than RTL.

Good candidates include:

- CRC/checksum;
- SPI/I2C transaction models;
- SWD packet/parity behavior;
- memory/flash transformations;
- address/map logic;
- command/status sequencing.

The reference model should not simply mirror the RTL line-for-line; independence is what gives it defect-detection value.

## 11. Randomized testing

Randomized tests are useful only if failures are reproducible.

Rules:

- use/report deterministic seeds;
- print seed and relevant generated transaction on failure;
- keep important directed boundary cases;
- convert important random failures into permanent regression cases;
- do not replace protocol assertions/formal reasoning with random testing.

Meaningful dimensions include length boundaries, address alignment, data patterns, command spacing, backpressure/stall timing, repeated operations, reset near legal boundaries, and multi-Site interleaving.

## 12. Coverage expectations

The first goal is correctness, not a vanity number. For each production block review at least:

- reset behavior;
- normal transaction path;
- min/max/boundary parameters;
- invalid/rejected command behavior;
- timeout/error behavior where defined;
- repeated/back-to-back operation;
- recovery after completion/error;
- shared-resource interaction;
- multi-Site independence when applicable.

Add code/functional/assertion coverage tooling only when it provides actionable value and the simulator/coverage model is established.

## 13. Waveforms and failure artifacts

When simulator support exists, preserve enough failure evidence to reproduce problems:

- waveform (`.vcd`, `.fst`, `.wdb`, or tool-appropriate);
- seed;
- simulator stdout/stderr;
- failing test/parameters;
- assertion message/time;
- relevant build/elaboration log.

Generated artifacts belong in ignored build/output directories, not beside source-of-truth files.

## 14. Verification tiers and claims

**Source/layout verified** means repository/layout/static checks passed. It does not mean RTL simulated.

**Functional simulation verified** means the explicitly named simulation passed for the stated simulator/configuration. It does not mean SVA, synthesis, timing, or hardware passed.

**Assertion verified** means the named SVA set was elaborated and evaluated by a simulator supporting the required constructs.

**FPGA build verified** means the stated Vivado synthesis/implementation/timing/bitstream stages actually ran and passed.

**Hardware verified** means the bitstream was loaded on the approved Z2/hardware setup and the stated test was actually observed to pass.

Never collapse these into one generic pass claim.

## 15. Merge gate

Before an RTL PR is merge-ready, run all currently configured/applicable automated verification. Long-term target:

```text
lint/static
RTL compile/elaboration
cocotb functional regression
SVA temporal/protocol regression
repository pytest
applicable synthesis/implementation/timing checks
```

If a stage is not configured, state that instead of fabricating success. CI green still requires explicit merge approval under root `AGENTS.md`.

## 16. Deploy and hardware-validation gate

Physical validation is separate from merge:

```text
main
  -> reproducible Vivado build
  -> implementation/timing checks
  -> artifact identified
  -> explicit deploy/hardware approval
  -> load bitstream on Z2
  -> hardware-in-the-loop test
  -> record observed result
```

Future HIL tests may include:

- AXI/register read/write sanity;
- Site enable/disable behavior;
- SWD transaction against a known target;
- SPI Flash read/program/verify;
- I2C EEPROM read/write/verify;
- multi-Site concurrency/isolation;
- abort/error recovery;
- throughput/timing measurements.

Hardware tests must use known-safe electrical configuration and remain behind the hardware approval gate.

## 17. First production RTL checklist

When the first real Plasma FPGA module is introduced:

- use `pl/rtl/site/` for per-Site controller/logic;
- choose/document the command-line simulator for fast regression;
- add cocotb to the development/test dependency path;
- add the first functional test;
- define a repeatable local/integration-host test entry point;
- add SVA when meaningful temporal/protocol invariants exist;
- confirm assertions are actually evaluated, not silently ignored;
- configure failure logs/waveforms;
- add CI only after the same command is reproducible outside CI;
- document what remains Vivado-only;
- keep Z2 loading behind explicit approval.

This is where the verification architecture becomes executable rather than documentation-only.
