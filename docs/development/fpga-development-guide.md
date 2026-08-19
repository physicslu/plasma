# Plasma FPGA Development Guide

> Scope: Zynq PL / FPGA RTL architecture and implementation policy  
> Status: architecture baseline before production Plasma RTL begins  
> Updated: 2026-08-19

## 1. Purpose

This document defines the default FPGA development architecture for Plasma before the first production PPU/Site RTL is implemented.

Design principle:

> Hardware remains hardware; functional verification is Python-first; temporal/protocol rules are checked close to the RTL; merge and physical deployment remain human-controlled gates.

Target flow:

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
Protocol rules        Random/reference models
        |                   |
        +---------+---------+
                  |
                  v
             CI / regression
                  |
                  v
             Merge gate
                  |
                  v
      Vivado synthesis / implementation
             timing analysis
                  |
                  v
             Deploy gate
                  |
                  v
                 Z2
                  |
                  v
         Hardware validation
```

Not every stage is wired into CI yet. Report only stages that actually ran.

## 2. Canonical Site terminology

The repeated independently controlled programming resource is a **Programming Site**:

```text
PPU
├── SITE 1
├── SITE 2
└── ... SITE N
```

Software/domain Site identity is one-based. Hardware RTL does not need to encode human-visible Site IDs internally unless the interface contract requires it, but module/directory naming for the repeated programming resource should use `site`, not the retired product-domain term `channel`.

Use `channel` only when it genuinely denotes a lower-level bus/protocol channel that is distinct from a Programming Site, and document that distinction.

## 3. Repository ownership

Source ownership:

```text
pl/
├── rtl/             synthesizable RTL source of truth
│   ├── examples/
│   ├── site/        per-Site production RTL
│   ├── bus/         shared bus/interconnect
│   └── top/         PPU PL top-level integration
├── constraints/     XDC source of truth
├── projects/        reproducible Vivado project/build Tcl and notes
├── verification/
│   ├── cocotb/
│   ├── sva/
│   └── models/
├── sim/             minimal simulator harnesses when needed
├── tests/           repository/source-layout checks
└── build/           generated output; not committed
```

As production RTL grows, protocol engines may be organized under directories such as `rtl/swd/`, `rtl/spi/`, and `rtl/i2c/`. Do not create directories until concrete modules require them.

## 4. RTL language baseline

All new production RTL should use SystemVerilog (`.sv`) unless a vendor/IP integration requires another format.

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

Rules:

- prefer `logic` for ordinary signals/variables;
- use `always_comb` for procedural combinational logic;
- use `always_ff` for sequential logic;
- use nonblocking assignments in `always_ff`;
- keep explicit widths and signedness where hardware-visible arithmetic depends on them;
- use `wire`/net types when actual net semantics are required;
- avoid inferred latches unless intentional and documented;
- make reset polarity, clock domain, enable/stall behavior, and interface ownership explicit.

Do not refactor working RTL merely for style unless the assigned task requires it.

## 5. Clock, reset, and CDC

Clock/reset decisions are architecture contracts. For each block make clear:

- clock domain;
- reset signal/polarity;
- synchronous/asynchronous behavior;
- power-up assumptions;
- enable/stall semantics;
- clock-domain crossings.

Use an appropriate CDC structure for the data semantics. Do not pass a multi-bit bus through independent two-flop synchronizers and assume coherence.

## 6. Site independence and shared resources

Plasma is designed for multiple independently controlled Programming Sites.

Guidelines:

- keep per-Site state local to the Site wherever practical;
- do not serialize unrelated Sites merely to simplify RTL;
- make genuinely shared resources explicit and arbitrate them deliberately;
- parameterize repeated Site logic when it improves reuse without hiding debug visibility;
- keep protocol engines (SWD/SPI/I2C) separate from higher-level Site policy/orchestration when practical;
- keep host-facing register/bus behavior stable and documented.

When a shared resource exists, define what concurrency is legal and what backpressure/arbitration guarantees software can rely on.

## 7. Software-visible interfaces

Treat register addresses, bit definitions, FIFO semantics, interrupts/status, command ordering, timeout behavior, and software-visible timing as interfaces rather than implementation details.

When PL-visible behavior changes, inspect impact on:

```text
RTL / SVA / cocotb
    ↕
register map / AXI/FIFO contract
    ↕
Python/PYNQ interface
    ↕
SiteManager / handler / higher software
```

Do not invent register addresses or interface behavior without a source specification or an explicitly approved design decision.

## 8. Constraints are source code

XDC is part of the design contract.

- define clocks accurately;
- define pins and I/O standards deliberately;
- add timing exceptions only when path semantics justify them;
- document non-obvious false paths, multicycle paths, asynchronous clock groups, and generated clocks;
- do not use broad timing exceptions merely to make implementation pass.

A generated bitstream that violates timing is not considered validated.

## 9. Generated Vivado files

Vivado project output is generated state. Keep checked-in source focused on RTL, XDC, reproducible Tcl, intentional IP/block-design configuration, documentation, and explicitly selected deliverable artifacts.

Do not hand-edit `.xpr`, `.runs`, `.srcs`, implementation databases, or similar generated output as the primary way to make a design change.

## 10. Static analysis and lint

Static checks should catch/flag issues such as:

- syntax/elaboration errors;
- width truncation/extension mistakes;
- unintended latches;
- multiple procedural drivers;
- unused/undriven signals;
- suspicious signed/unsigned operations;
- incomplete state/case behavior;
- selected CDC/reset issues supported by the chosen tooling.

The exact linter is not frozen here. Once selected, its configuration belongs in the repository and warnings must be handled intentionally rather than blanket-disabled.

## 11. Verification architecture

Functional and temporal verification are complementary:

```text
cocotb + pytest -> What result did the design produce?
SVA             -> Did the design obey cycle/protocol invariants while doing it?
```

Detailed verification policy is in `docs/development/fpga-verification-guide.md`.

Use Python reference/golden models for data-path/protocol behavior where independent software expression improves confidence. Keep SVA separate from production synthesis sources unless an assertion is intentionally implemented as synthesizable debug hardware.

## 12. CI and build tiers

### Tier A — fast regression

```text
source-layout tests
static/lint checks
RTL compile/elaboration
cocotb/pytest functional regression
supported fast assertion checks
```

### Tier B — FPGA build/sign-off

```text
Vivado synthesis
Vivado implementation
DRC
clock/timing analysis
bitstream generation when required
full assertion simulation where the fast simulator is insufficient
```

Do not report Tier A as Tier B success.

## 13. Merge, deploy, and hardware gates

The repository root `AGENTS.md` defines protected operations.

```text
AI / developer change
    -> automated verification
    -> feature branch / PR
    -> CI green for configured checks
    -> explicit merge approval
    -> main
    -> implementation/timing/artifact validation
    -> explicit deploy/hardware approval
    -> load on Z2
    -> hardware-in-the-loop validation
```

Merge and hardware deployment are separate decisions. Passing CI authorizes neither automatically.

## 14. AI-assisted FPGA development

AI agents may implement RTL, assertions, cocotb tests, reference models, boundary/random cases, interface reviews, and build/verification scripts.

They must not invent:

- register addresses;
- pin assignments;
- clocks or timing requirements;
- voltage/electrical limits;
- target/protocol behavior conflicting with authoritative specifications;
- hardware validation results.

Preferred workflow:

```text
read AGENTS.md + pl/AGENTS.md
    -> inspect interface/constraints/specification
    -> implement SystemVerilog RTL
    -> add/update cocotb tests
    -> add/update SVA for important temporal rules
    -> run available focused regression
    -> run full applicable validation
    -> review diff and claims
    -> publish feature branch/PR
    -> stop at merge gate
```

## 15. First production RTL adoption plan

Production Plasma FPGA work has not yet started, so establish the Site terminology cleanly from the first real module instead of carrying a legacy `channel` placeholder forward.

Recommended sequence:

1. Keep `btled` only as a build/environment example.
2. Implement the first per-Site block under `pl/rtl/site/`.
3. Add the minimum command-line simulator + cocotb integration required by that block.
4. Add SVA when temporal/protocol invariants justify it.
5. Add Python reference models where useful.
6. Add CI only after the same command is reproducible outside CI.
7. Add Vivado synthesis/implementation/timing checks at the appropriate integration tier.
8. Keep physical Z2 loading and target operations behind explicit hardware approval.

This avoids both legacy naming debt and premature verification-framework complexity.
