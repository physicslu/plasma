# Plasma PL Agent Rules

This file applies to all work under `pl/` and supplements the repository-root `AGENTS.md`.
The root `AGENTS.md` remains authoritative for Git workflow, approval gates, deployment,
security, and hardware-affecting operations.

Read these documents before changing FPGA/PL behavior:

- `docs/development/fpga-development-guide.md`
- `docs/development/fpga-verification-guide.md`

## 1. RTL language and coding policy

New synthesizable RTL shall use SystemVerilog (`.sv`).

For new code:

- Prefer `logic` for ordinary signals and variables.
- Use `always_comb` for combinational procedural logic.
- Use `always_ff` for sequential procedural logic.
- Use nonblocking assignments (`<=`) in `always_ff` blocks.
- Keep `wire` or other net types when actual net semantics are required, including
  appropriate multi-driver, tri-state, or `inout` cases.
- Do not introduce new Verilog-style `reg` declarations or `always @(*)` blocks.
- Make widths, signedness, reset polarity, clock domain, and interface ownership explicit.
- Avoid inferred latches unless a latch is intentionally part of the design and documented.

Do not refactor existing RTL solely to conform to the current style unless the assigned task
requires it. Behavior-preserving cleanup must not silently expand the task scope.

## 2. Synthesizable RTL and verification must remain separate

Production RTL belongs under `pl/rtl/`.
Verification code must not be mixed into synthesizable modules merely for test convenience.

Target verification layout:

```text
pl/
├── rtl/
├── constraints/
├── projects/
├── verification/
│   ├── cocotb/
│   ├── sva/
│   └── models/
├── sim/
└── tests/
```

The repository may adopt these directories incrementally as the first production Plasma RTL
modules are added; do not create empty structure solely for appearance.

## 3. Assertion policy

Temporal, protocol, and invariant checks should use SystemVerilog Assertions (SVA) when
practical.

- Keep SVA in separate verification files, normally under `pl/verification/sva/`.
- Prefer `bind` for attaching assertion modules/checkers to RTL when it keeps production RTL
  clean and interfaces understandable.
- SVA sources are verification-only and must be excluded from synthesis/bitstream source sets.
- Do not claim a simulator supports the required SVA semantics without verifying the selected
  tool and assertion features actually used by the test.
- If a fast simulator does not support a required assertion feature, keep the fast functional
  regression and run the affected assertion set in a simulator that does support it.

Assertions are especially valuable for rules such as request/response timing, illegal state
transitions, protocol ordering, stable-signal requirements, and bounded completion.

## 4. Functional verification policy

Python is the primary functional verification language for new Plasma RTL.
Use `cocotb` with `pytest` for active stimulus, checking, randomized cases, regression, and
reference-model comparison.

- Prefer Python test code over a large self-checking Verilog/SystemVerilog testbench.
- A minimal SystemVerilog simulation harness is allowed when required for clock/interface
  wrappers, vendor primitives, simulator setup, or SVA binding.
- Keep functional test intent in Python whenever practical.
- Use deterministic seeds for randomized regression or report/reproduce the seed on failure.
- Prefer Python golden/reference models for data-path, protocol, packet, CRC, memory, image,
  or programming-algorithm verification.
- Boundary, reset, error, cancellation/abort, timeout, and back-to-back transaction cases must
  be considered in addition to happy-path tests.

## 5. RTL change requirements

For a behavioral RTL change, the agent must consider all of the following before declaring the
change complete:

1. Functional verification through cocotb/pytest where applicable.
2. SVA coverage for important timing/protocol invariants where practical.
3. Register-map, Python/PYNQ, software API, and documentation impact.
4. Clock/reset and CDC impact.
5. XDC/timing-constraint impact.
6. Synthesis/implementation/timing validation when the change reaches that stage.
7. Hardware validation only when explicitly approved under the root `AGENTS.md`.

Do not weaken a failing checker merely to obtain a green test.
Fix the smallest correct design or verification layer.

## 6. Validation and CI policy

The target FPGA validation flow is:

```text
SystemVerilog RTL
    -> static/lint checks
    -> cocotb + pytest functional regression
    -> SVA temporal/protocol checks
    -> synthesis
    -> implementation
    -> timing checks
    -> merge approval
    -> deploy approval
    -> Z2 hardware validation
```

Not every stage is configured in CI yet. Report the exact stages that were actually run.
A passing source-layout pytest does not prove simulation, synthesis, timing closure, bitstream
creation, or Z2 behavior.

When CI support is introduced, keep fast regression separate from longer Vivado/sign-off jobs
where practical so routine feedback remains quick without sacrificing hardware-quality gates.

## 7. Human approval gates

FPGA work inherits the repository approval model:

- AI may inspect, edit, test, commit, push feature branches, and prepare PRs within scope.
- Merge to `main` requires explicit user approval unless the root contract explicitly allows a
  documentation-only direct-main workflow requested by the user.
- Loading a new bitstream on Z2, changing FPGA I/O behavior on connected hardware, changing DUT
  power/voltage, or programming a real IC requires the protected hardware approval defined by
  the root `AGENTS.md`.

Never turn a software/simulation pass into a claim of hardware validation.