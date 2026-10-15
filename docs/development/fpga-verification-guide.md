# Plasma FPGA Verification Guide

> Scope: RTL functional, temporal, regression, and hardware-validation strategy  
> Updated: 2026-10-15

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
Z2 hardware validation (when already authorized in Gate 1 scope)
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

The repository contains both source-layout pytest checks and implemented
Cocotb/RTL regressions for selected PS/PL blocks (including PSPL-02
CONTROL and SWD waveform logic). Coverage is **per design and per layer**,
not a blanket FPGA sign-off. In particular, a Cocotb run that drives AXI
signals does not establish that CPython on the Zynq ARM emits the same
transactions through Linux MMIO.

Therefore:

- report which exact Cocotb/SVA modules, simulator and RTL variant ran;
- identify any unimplemented driver/architecture-integration coverage;
- never infer RTL, timing, PS/Linux MMIO or HIL PASS from source-only tests;
- do not block documentation-only changes on unrelated FPGA tools.

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

## 4A. Production PS driver reuse across Cocotb and Linux (required for AXI-Lite)

**Design requirement:** one production PS driver/control layer implements
register definitions, programming order, status/error processing and state
transitions. Tests **reuse that implementation** instead of recoding the
same sequence solely in Cocotb.

```text
                  Shared production PS driver logic
              (register map, sequence, checks, state)
                               |
                       injected MMIO interface
                     read32 / write32 / ...
                           /         \
         Cocotb AXI BFM backend     Real Linux MMIO backend
           (simulation-time I/O)     (/dev/mem or vetted driver)
                   |                         |
              actual PL RTL          ARMv7 + Linux + PS7/AXI + PL
                   |                         |
           transaction simulation             Z2 HIL
```

**Scope of reuse:** share the real PS control algorithm; not necessarily
the physical MMIO transport or all coroutine/synchronous glue.
Cocotb's AXI bus-functional model normally emits transactions on HDL
ports; it does **not** run CPython inside the ARM core or execute actual
`/dev/mem` accesses. If the production driver is synchronous and the
Cocotb bus driver asynchronous, provide an explicit thin adapter or
software-driver test harness rather than copy/paste the algorithm.
Where a layer cannot run unchanged, report that limitation.

**Validation matrix:**

| Layer | Execute/observe | Can claim | Cannot claim |
| --- | --- | --- | --- |
| PS driver pytest | Actual control/sequence code with fake MMIO/trace backend | Correct call order, offsets, values, expected errors | Hardware bus cycles or CPU access width |
| Shared PS logic + Cocotb RTL | Same driver operations through Cocotb AXI BFM | Address/value semantics, real RTL response to modeled transactions | Actual ARM stores, Linux `mmap` attributes or PS7 interconnect behavior |
| Target MMIO backend verification | Inspect real target binary/disassembly and controlled memory access implementation | Verified ARMv7 instruction width/alignment for the tested build and mapping assumptions | That a specific PL received the expected AXI transaction |
| Bounded Z2 HIL | Real PS application/driver through Linux, PS7 and loaded FPGA | Observed PS-to-PL behavior with stated bitstream and board | Untested boundary/error cases or future hardware revisions |

For each AXI-Lite peripheral, simulate representative aligned 32-bit
reads/writes; defined sub-word accesses and WSTRB combinations; legal and
illegal offsets; independent AW/W arrival order; OKAY/SLVERR BRESP and
RRESP; valid/ready stalls; reset and back-to-back requests. Explicitly
compare the **protocol the production driver expects** with the RTL
response. Unsupported widths are a documented interface decision, not an
unexamined assumption. An RTL-only test of invented ideal full-word
transactions is insufficient PS/PL integration coverage.

**Linux backend-specific requirement:** `struct.pack_into("<I", buffer,
offset, value)` promises a little-endian four-byte representation,
**not** one atomic/aligned 32-bit ARM device-store instruction.
Inspect the actual CPython/native implementation or its ARMv7 disassembly,
confirm `STR` versus `STRB` (and offsets), address alignment and MMIO
mapping/cacheability/barrier requirements; use a verified access primitive
for device registers. A C `volatile uint32_t` access alone is not proof
of the entire PS7/AXI transaction. Confirm the relevant path in HIL.

**Failure evidence rule:** an ARM external-abort fault address within a
register's byte range (for example CONTROL `base+1`) alone does **not**
prove the slave observed the same AWADDR or emitted SLVERR. Establish the
instruction, fault status and access mapping first; use bus-level evidence
when needed. For the current PSPL-02 development incident, treat
MMIO-width/decode mismatch as a hypothesis pending confirmation; do not
repeat the bus-faulting write blindly. Deliberately malformed AXI
transactions belong in Cocotb or an explicitly authorized separate
qualification experiment, **not** the normal development HIL.

For Prototype, do **not** build a full ARM/Linux/FPGA co-simulation
platform just to satisfy this policy. Reuse the existing PS driver,
augment the focused offline checks, and reserve a short real-board smoke
test for the physical integration boundary.

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
  -> load bitstream on Z2 (if included in the approved Gate 1 scope)
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

Hardware tests must use known-safe electrical configuration and remain within the hardware operations explicitly authorized by the root AGENTS.md Gate 1. No separate hardware approval gate is created.

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
- keep Z2 loading within the approved Gate 1 scope; no third approval gate.

This is where the verification architecture becomes executable rather than documentation-only.
