# Plasma FPGA Development Guide

> Project: `physicslu/plasma`  
> Scope: Zynq PL / FPGA RTL architecture and implementation policy  
> Status: architecture baseline before production Plasma RTL begins  
> Updated: 2026-08-17

---

## 1. Purpose

This document defines the default FPGA development architecture for Plasma before the first
production programmer RTL is implemented.

The design principle is:

> Hardware remains hardware; functional verification is Python-first; temporal/protocol rules
> are checked close to the RTL; merge and physical deployment remain human-controlled gates.

The resulting development model is:

```text
SystemVerilog RTL
        |
        v
Static / lint checks
        |
        +-------------------+
        |                   |
        v                   v
SVA checks            cocotb + pytest
Temporal rules        Functional behavior
Protocol rules        Random/reference-model tests
        |                   |
        +---------+---------+
                  |
                  v
             CI / regression
                  |
                  v
             Merge gate
           Human approval
                  |
                  v
      Vivado synthesis / implementation
             timing analysis
                  |
                  v
             Deploy gate
           Human approval
                  |
                  v
                 Z2
                  |
                  v
         Hardware validation
```

This is the target architecture. The current repository does not yet have every simulator,
assertion, or CI stage wired up. New production RTL should adopt the architecture incrementally
instead of pretending unconfigured checks already exist.

---

## 2. Repository ownership

Current PL source ownership remains:

```text
pl/
├── rtl/             synthesizable RTL source of truth
├── constraints/     XDC source of truth
├── projects/        reproducible Vivado project/build Tcl and project notes
├── tests/           repository/source-layout tests that do not require Vivado
└── build/           generated Vivado output; not committed
```

As production RTL begins, use this target verification structure:

```text
pl/
├── rtl/
│   ├── common/
│   ├── channel/
│   ├── bus/
│   ├── top/
│   ├── swd/
│   ├── spi/
│   └── i2c/
├── constraints/
├── projects/
├── verification/
│   ├── cocotb/
│   │   ├── test_<module>.py
│   │   └── ...
│   ├── sva/
│   │   ├── <module>_sva.sv
│   │   └── ...
│   └── models/
│       ├── <protocol>_model.py
│       └── ...
├── sim/
│   └── minimal simulator harnesses when required
└── tests/
```

Do not create directories until they are useful. The structure is a placement rule, not a
requirement to commit empty folders.

---

## 3. RTL language baseline

### 3.1 New RTL uses SystemVerilog

All new production RTL should use `.sv` unless a vendor/IP integration forces another format.

Preferred style:

```systemverilog
logic [7:0] next_value;
logic [7:0] value_q;

always_comb begin
    next_value = value_q;
    if (load)
        next_value = load_value;
end

always_ff @(posedge clk) begin
    if (!rst_n)
        value_q <= '0;
    else
        value_q <= next_value;
end
```

Avoid introducing new code such as:

```systemverilog
reg [7:0] value;
always @(*) begin
    ...
end
```

`logic` is the normal default, but `wire` is not forbidden. Use a net type when net semantics
are actually required, such as appropriate tri-state, `inout`, or multi-driver structures.

### 3.2 Combinational logic

Use `always_comb` for procedural combinational logic.

Rules:

- Assign every output/temporary on every path.
- Use explicit defaults at the top of a block when that makes coverage clear.
- Avoid intentional latches unless the design genuinely requires one and the reason is
  documented.
- Keep combinational blocks small enough that ownership and priority are obvious.

`always_comb` improves semantic checking but does not replace lint, review, or simulation.

### 3.3 Sequential logic

Use `always_ff` for clocked state.

Rules:

- Use nonblocking assignments (`<=`).
- One state element should have one clear procedural owner.
- Reset polarity and synchronous/asynchronous behavior must be explicit.
- Do not mix unrelated clock domains in one sequential block.
- Avoid derived/gated clocks unless the architecture explicitly requires them; prefer enables
  when appropriate.

### 3.4 Types and intent

Prefer intent-rich SystemVerilog constructs where they improve correctness:

- `typedef enum logic [...]` for FSM states.
- `parameter` / `localparam` for configurable or internal constants.
- packed structs for strongly related bus fields when tool compatibility is verified.
- explicit widths rather than unsized assumptions in hardware-visible arithmetic.
- explicit signedness for arithmetic that depends on sign extension/comparison.

Do not introduce clever syntax merely because SystemVerilog allows it. Synthesis portability,
reviewability, and simulator consistency matter more than language novelty.

---

## 4. Clock and reset policy

Clock/reset decisions are architectural contracts.

For each RTL block, document or make obvious:

- clock domain;
- reset signal and polarity;
- synchronous vs asynchronous assertion/deassertion behavior;
- power-up assumptions, if any;
- enable/stall behavior;
- clock-domain crossings.

Avoid assuming two signals are synchronous merely because they are generated on the same FPGA.
If data crosses clock domains, use an appropriate CDC structure and verify the transfer model.

Typical choices include:

- two-flop synchronizers for single-bit level signals;
- toggle/pulse synchronizers for events;
- handshake schemes for controlled multi-bit transfers;
- asynchronous FIFOs for sustained multi-bit streams.

The implementation must match the data semantics. A multi-bit bus must not be passed through
independent two-flop synchronizers and assumed coherent.

---

## 5. Interfaces and module boundaries

Plasma is intended to support multiple programming channels. RTL should preserve that
independence.

Guidelines:

- Keep per-channel state local to the channel wherever practical.
- Make genuinely shared resources explicit rather than serializing unrelated channels by
  default.
- Parameterize repeated channel logic when it improves reuse without obscuring debug.
- Keep protocol engines (for example SWD/SPI/I2C) separate from policy/orchestration logic when
  practical.
- Keep host-facing register/bus behavior stable and documented.
- Treat register addresses, bit definitions, interrupt/status semantics, and software-visible
  timing as interfaces, not implementation details.

When RTL-visible behavior changes, check Python/PYNQ register access and higher software layers
for corresponding changes.

---

## 6. Constraints are source code

XDC files are part of the design contract.

For new clocks and I/O:

- define clocks accurately;
- define I/O pins and I/O standards deliberately;
- add timing exceptions only when the underlying path semantics justify them;
- document non-obvious false paths, multicycle paths, asynchronous clock groups, or generated
  clocks;
- do not use broad timing exceptions merely to make implementation pass.

A design that generates a bitstream but violates timing is not considered validated.

Timing closure belongs before physical deployment in the target flow.

---

## 7. Generated Vivado files

Vivado project output is generated state, not the design source of truth.

Keep checked-in sources focused on:

- RTL;
- XDC;
- Tcl needed to recreate/build the project;
- intentional block-design/IP configuration sources when required;
- documentation;
- selected deliverable artifacts only when repository policy explicitly calls for them.

Do not hand-edit `.xpr`, `.runs`, `.srcs`, implementation databases, or other generated output
as the primary way to make a design change.

A clean checkout should be reproducibly buildable from the maintained source inputs once the
required Vivado environment is present.

---

## 8. Static analysis and lint

Static checks are the first guardrail, not the only guardrail.

The intended checks should catch or flag issues such as:

- syntax/elaboration errors;
- width truncation/extension mistakes;
- unintended latches;
- multiple procedural drivers;
- unused or undriven signals;
- suspicious signed/unsigned operations;
- incomplete state/case behavior;
- selected CDC/reset issues where supported by the chosen tooling.

The exact linter/tool is not frozen by this document. When one is added, its configuration must
be checked into the repository and its warnings must be handled intentionally rather than
blanket-disabled.

---

## 9. Verification architecture

Functional verification and temporal verification are complementary.

Use:

```text
cocotb + pytest    -> What result did the design produce?
SVA                -> Did the design obey the required cycle/protocol rule while producing it?
```

Detailed policy is in:

```text
docs/development/fpga-verification-guide.md
```

Do not move all correctness checking into Python and lose cycle-local protocol checks.
Do not move all correctness checking into SVA and lose high-level reference-model comparison.

---

## 10. CI and build tiers

The recommended long-term split is:

### Tier A — fast checks

Run frequently on development branches:

```text
source-layout tests
static/lint checks
fast RTL compile/elaboration
cocotb/pytest functional regression
supported fast assertion checks
```

### Tier B — FPGA build/sign-off checks

Run when appropriate for the change and before hardware deployment:

```text
Vivado synthesis
Vivado implementation
DRC
clock/timing analysis
bitstream generation when required
full assertion simulation where the selected fast simulator is insufficient
```

Do not make Tier A falsely report Tier B success.
Keep validation reports explicit about what ran and where.

---

## 11. Merge and deploy gates

The repository root `AGENTS.md` defines protected operations.

The intended FPGA lifecycle is:

```text
AI / developer change
    -> automated verification
    -> reviewable feature branch / PR
    -> CI green for configured checks
    -> human merge approval
    -> main
    -> implementation/timing/artifact validation
    -> human deploy approval
    -> load on Z2
    -> hardware-in-the-loop validation
```

A merge decision and a hardware-deploy decision are deliberately separate.
Passing CI authorizes neither automatically.

---

## 12. AI-assisted FPGA development

AI agents are useful for:

- implementing synthesizable RTL;
- writing assertions;
- writing cocotb tests and reference models;
- generating boundary/randomized test cases;
- reviewing interfaces and state machines;
- diagnosing simulation failures and waveforms;
- maintaining build/verification scripts and documentation.

They must not invent:

- register addresses;
- pin assignments;
- clocks or target timing;
- voltage/electrical limits;
- protocol behavior that conflicts with a source specification;
- hardware validation results.

For a new RTL feature, the preferred agent workflow is:

```text
read AGENTS.md + pl/AGENTS.md
    -> inspect interfaces/constraints/specification
    -> implement SystemVerilog RTL
    -> add/update cocotb functional tests
    -> add/update SVA for important temporal rules
    -> run available focused regression
    -> run full applicable validation
    -> review diff and validation claims
    -> publish feature branch/PR
    -> stop at merge gate
```

---

## 13. Adoption plan

Because production Plasma FPGA work has not started, adopt the architecture cleanly from the
first real module rather than planning a later wholesale migration.

Recommended sequence:

1. Keep the existing `btled` flow as a simple build/environment example.
2. When the first production module is created, add the minimum simulator + cocotb integration
   needed for that module.
3. Add `pl/verification/cocotb/` and a first Python test.
4. Add `pl/verification/sva/` when the module has temporal/protocol invariants worth asserting.
5. Add a Python reference model where behavior is easier to express independently in software.
6. Add CI checks only after the selected simulator/tool commands are reproducible locally/SWPC.
7. Add Vivado synthesis/implementation/timing jobs at the appropriate integration tier.
8. Keep physical Z2 validation behind the explicit deploy/hardware gate.

This avoids both extremes: carrying legacy testbench habits into new code, and installing a
large verification framework before there is RTL that benefits from it.
