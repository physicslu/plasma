# Plasma FPGA Verification Guide

> Project: `physicslu/plasma`  
> Scope: RTL functional, temporal, regression, and hardware-validation strategy  
> Updated: 2026-08-17

---

## 1. Verification goals

Plasma FPGA verification uses two complementary layers:

```text
Python / cocotb / pytest
    -> functional behavior, transactions, randomized stimulus, reference models

SystemVerilog Assertions (SVA)
    -> cycle-level protocol, ordering, invariants, bounded timing, illegal states
```

The two layers answer different questions and should not replace one another.

The target flow is:

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

---

## 2. Current repository status

At the time this architecture is defined, `pl/tests/` contains repository/source-layout pytest
checks, not a complete RTL simulator regression.

Therefore:

- do not claim cocotb regression exists until it is actually added;
- do not claim SVA coverage exists until assertion sources and a supporting simulator flow are
  configured;
- do not block documentation-only work on tools that have not yet been selected/installed;
- add the verification infrastructure together with the first production RTL that needs it.

---

## 3. Python-first functional verification

New production RTL should use `cocotb` as the primary active functional testbench layer and
`pytest` as the repository-level Python test runner.

Typical test responsibilities include:

- generating clocks and resets;
- driving module interfaces;
- constructing protocol transactions;
- checking outputs/status;
- randomized stimulus;
- boundary and error cases;
- timeout behavior;
- back-to-back operations;
- comparing DUT output with Python reference models;
- regression parameterization and reporting.

A typical future test shape is:

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

    # Drive one transaction.
    # Compare DUT behavior with the expected result.
```

Exact APIs and simulator integration must be defined by the first real module rather than
copied blindly from an unrelated project.

---

## 4. Minimal HDL simulation harness

Python-first does not mean HDL-free.

A minimal SystemVerilog simulation harness is allowed when needed for:

- top-level clock/interface wiring;
- vendor simulation primitives;
- interfaces that are awkward to expose directly to cocotb;
- SVA `bind` attachment;
- simulator-specific initialization;
- reusable wrappers around a production DUT.

Keep the harness structural and small.
Do not recreate a second functional test framework in SystemVerilog unless a concrete tool or
IP requirement justifies it.

The preferred separation is:

```text
pl/rtl/                    production synthesizable design
pl/sim/                    minimal HDL harnesses
pl/verification/cocotb/    functional tests
pl/verification/sva/       temporal/protocol assertions
pl/verification/models/    Python reference/golden models
```

---

## 5. SystemVerilog Assertions

SVA should capture rules that are easiest and most valuable to check at the exact cycle where
they can fail.

Good assertion candidates include:

- request eventually receives an acknowledge/done within a bounded interval;
- `busy` and `idle` states are mutually consistent;
- no illegal FSM state is entered;
- a command is not accepted while the block cannot accept it;
- a signal remains stable during a required protocol window;
- write/read handshakes occur in legal order;
- clock/output toggling only occurs while an engine is active;
- reset returns architectural state to a known legal condition;
- FIFO overflow/underflow is never requested;
- channel-local operations do not accidentally alter unrelated channel state.

Example pattern:

```systemverilog
property request_completes;
    @(posedge clk)
    disable iff (!rst_n)
    request |-> ##[1:MAX_LATENCY] done;
endproperty

assert property (request_completes);
```

Do not treat example syntax as a substitute for checking simulator support for the exact SVA
features used.

---

## 6. Keep SVA out of production synthesis

Assertions should normally live in separate files, for example:

```text
pl/verification/sva/swd_engine_sva.sv
```

Use a checker/bind style when appropriate:

```systemverilog
bind swd_engine swd_engine_sva checker_i (
    .clk   (clk),
    .rst_n (rst_n),
    ...
);
```

The key rule is structural, not merely stylistic:

> Verification assertion sources must not be included in the production synthesis/bitstream
> source set unless an assertion is intentionally being implemented as synthesizable debug
> hardware and that exception is explicitly designed and reviewed.

This prevents verification-only logic from silently becoming FPGA resource usage.

---

## 7. Simulator strategy

Do not assume one simulator is equally good at every verification layer.

The intended strategy is:

### Fast regression simulator

Use a fast simulator for frequent compile/elaboration and cocotb regression when it supports
the RTL constructs required by the design.

Desired properties:

- fast startup;
- command-line automation;
- cocotb integration;
- deterministic CI behavior;
- waveform output on failure;
- enough SystemVerilog support for the production RTL.

### Assertion/sign-off simulator

If the fast simulator does not support an SVA feature used by Plasma, run that assertion set in
a simulator that does support the required semantics.

For the AMD/Xilinx flow, Vivado/XSIM is an available integration candidate because the project
already depends on Vivado for implementation. A different simulator may be selected later if
it provides better automation/licensing/coverage.

The repository must document the exact supported command once the first simulator flow is
implemented.

Do not mark an unsupported assertion as "passed" merely because the simulator ignored or did
not elaborate it.

---

## 8. pytest integration

The repository uses pytest as the Python test runner.

The long-term goal is that FPGA functional regression can be invoked from a predictable
pytest-facing command or wrapper, while keeping simulator build details encapsulated.

A future structure may use:

```text
pl/verification/cocotb/test_swd_engine.py
pl/verification/cocotb/test_spi_engine.py
pl/verification/cocotb/test_channel_controller.py
```

The exact Makefile/runner/plugin mechanism should be selected when the first test is added.
Avoid defining a fake command in documentation before it exists.

Once configured, CI and developer documentation must use the same supported entry point.

---

## 9. Reference and golden models

Python reference models are strongly recommended when expected behavior can be written more
simply and independently than the RTL implementation.

Good Plasma candidates include:

- CRC/checksum calculation;
- SPI/I2C transaction models;
- SWD packet/parity behavior;
- memory/flash content transformations;
- address/map logic;
- command/status sequencing;
- image/data processing if such blocks are introduced later.

Conceptual pattern:

```python
expected = reference_model(input_data)
actual = await run_dut_transaction(dut, input_data)
assert actual == expected
```

The reference model should not simply duplicate the RTL algorithm line-for-line. Independence
is valuable because the model can catch a shared misunderstanding in implementation structure.

---

## 10. Randomized testing

Randomized tests are useful for exploring combinations humans are unlikely to write by hand,
but failures must be reproducible.

Rules:

- use/report deterministic seeds;
- print the seed and relevant generated transaction on failure;
- keep a fixed regression set of important directed corner cases;
- convert important discovered random failures into permanent regression cases;
- do not rely on random testing as a substitute for protocol assertions or formal reasoning.

Focus randomization on meaningful dimensions such as:

- length boundaries;
- address alignment;
- data patterns;
- command spacing;
- backpressure/stall timing;
- repeated operations;
- reset near legal transaction boundaries;
- multi-channel interleaving where the architecture permits concurrency.

---

## 11. Coverage expectations

The first verification goal is correctness, not a vanity coverage number.

For each production block, review at least:

- reset behavior;
- normal transaction path;
- minimum/maximum/boundary parameters;
- invalid or rejected command behavior;
- timeout/error behavior where defined;
- repeated/back-to-back operation;
- state recovery after completion/error;
- interaction with shared resources;
- multi-channel independence when applicable.

Later, code/functional/assertion coverage tooling can be added if it provides actionable value.
Do not set a numeric coverage threshold before the chosen simulator and coverage model are
actually established.

---

## 12. Waveforms and failure artifacts

A failed regression should make diagnosis easy.

When simulator support is added, prefer the ability to retain on failure:

- waveform (`.vcd`, `.fst`, `.wdb`, or tool-appropriate format);
- seed;
- simulator stdout/stderr;
- failing test name and parameters;
- assertion message/time;
- relevant build/elaboration log.

CI may avoid uploading large waveforms for every passing test, but failures should preserve
enough information to reproduce the problem.

Generated simulation artifacts belong in ignored build/output directories, not alongside the
source of truth.

---

## 13. Verification tiers and claims

Use precise language when reporting results.

### Source/layout verified

Means only repository/layout/static checks passed.
It does not mean RTL simulated.

### Functional simulation verified

Means cocotb/pytest (or another explicitly named functional simulation) passed for the stated
simulator/configuration.
It does not mean SVA coverage, synthesis, timing, or hardware passed.

### Assertion verified

Means the named SVA set was elaborated and evaluated by a simulator supporting the required
constructs.

### FPGA build verified

Means the stated Vivado synthesis/implementation/timing/bitstream stages actually ran and
passed.
Report which stages ran.

### Hardware verified

Means the bitstream was actually loaded on the approved Z2/hardware setup and the stated test
was observed to pass.

Never collapse these labels into one generic "all tests passed" claim.

---

## 14. Merge gate

Before an RTL PR is called merge-ready, run all currently configured and applicable automated
verification.

The expected long-term set is:

```text
lint/static
RTL compile/elaboration
cocotb functional regression
SVA temporal/protocol regression
repository pytest
applicable synthesis/implementation/timing checks
```

If a stage is not yet configured, state that clearly in the PR instead of fabricating a pass.

CI green still requires human approval before merge according to the root `AGENTS.md`.

---

## 15. Deploy and hardware validation gate

After merge, physical validation is a separate decision.

The intended flow is:

```text
main
  -> reproducible Vivado build
  -> implementation/timing checks
  -> artifact identified
  -> explicit user deploy/hardware approval
  -> load bitstream on Z2
  -> hardware-in-the-loop test
  -> record observed result
```

Typical future hardware-in-the-loop tests may include:

- AXI/register read/write sanity;
- channel enable/disable behavior;
- SWD transaction against a known target;
- SPI Flash read/program/verify;
- I2C EEPROM read/write/verify;
- multi-channel concurrency/isolation;
- abort/error recovery;
- throughput and timing measurements.

Hardware tests must use known-safe electrical configuration and remain behind the repository
hardware approval gate.

---

## 16. First production RTL checklist

When the first real Plasma FPGA module is introduced, complete these items together rather than
leaving verification as a later retrofit:

- choose and document the command-line simulator used for fast regression;
- add cocotb to the development/test dependency path;
- add the first cocotb functional test;
- define a repeatable local/SWPC test entry point;
- add SVA if the module has meaningful temporal/protocol invariants;
- confirm how those assertions are run and that unsupported features are not silently ignored;
- configure failure logs/waveforms;
- add CI only after the same command works reproducibly outside CI;
- document what remains SWPC/Vivado-only;
- keep Z2 hardware loading behind explicit approval.

This is the point where the architecture becomes executable rather than documentation-only.
