# Plasma PL Agent Rules

This file applies to all work under `pl/` and supplements the repository-root `AGENTS.md`.
The root `AGENTS.md` remains authoritative for Git workflow, approval gates, deployment,
security, and hardware-affecting operations.

Read these documents before changing FPGA/PL behavior:

- `docs/development/fpga-development-guide.md`
- `docs/development/fpga-verification-guide.md`
- `docs/development/fpga-systemverilog-style.md` (new RTL and substantive RTL changes)

## Physical SWD path selection

The retired `z2-swd-gpio` and `z2-swd03-axi` image builds must never be selected for Blue Pill PoC or interpreted as real target DPIDR. Retained shared Identity/Board Files helpers and synthetic RTL are for dependent host-only tests. Follow root `AGENTS.md` and `docs/development/swd-legacy-path-retirement.md` for current Z2 PS-local OpenOCD + WordPort + PL SWD.

## New FPGA Project and SWPC build standard (ADR-0004)

For each **new deliverable FPGA Image family × Board target**, create a
separately reproducible Vivado Project under `pl/projects/<project-name>/`,
owning its explicit RTL/IP/BD/XDC sources, source/board pins, Vivado Tcl,
target-specific HWH/Bitstream verifier and Image Manifest. Common reviewed
RTL/tooling may be reused, but **new projects MUST NOT inherit the fixed
F1-B Site 1 build engine or its project-specific verification**.

The **canonical repeatable SWPC Host Build route** for new FPGA Images is the
trusted **Path 2 `operator-cli`** with an Owner-authorized SHA-pinned Work Order
and a reviewed, version-controlled Python build entrypoint. That script invokes
the new Project's Vivado Tcl and records toolchain, timing, DRC/methodology,
BIT/HWH/BIN (when applicable), full reports and SHA256. Path 3 owner-approved
engineering experiments remain separate and are not substitutes for a
qualified Path 2 product build.

`vivado-host-build` is F1-B-specific and **not a general new-Project route**.
Its retirement is `F1B_BUILD_ENGINE_RETIREMENT_PENDING`: do not expand its
project allowlist; do not delete its existing historical/recovery dependencies
until a new MPE operator-cli build is qualified, consumers migrated, safety
retained and a separate owner-approved Gate 2 retirement PR is accepted.
New MPE/new product projects shall have no F1-B build-engine or legacy
single-Site SWD source dependency; CI must test this fail-closed boundary.
Host Build != FPGA Manager Load, DUT power, PS MMIO, Flash or HIL authorization.
See `docs/adr/0004-project-isolated-fpga-build-path2-operator-cli.md`.

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

## 4A. Shared PS driver and Cocotb/HIL verification contract

For any PS-visible AXI-Lite register or command protocol, prefer **one
production PS control/transaction implementation** exercised by both
Cocotb and the real Linux PS, with a narrow injected MMIO interface
(`read32`/`write32`, and other widths only when explicitly specified).

- Cocotb must exercise the **same register sequencing, state handling,
  address/value calculation, and response validation** used by the PS
  application. Do not maintain an independent test-only copy of the
  control algorithm that can drift from production.
- Use an **AXI bus-functional-model backend** when simulating RTL and
  a **Linux MMIO backend** when running on the Z2; adapt execution models
  (e.g., synchronous versus asynchronous I/O) without duplicating business
  logic. A mock backend only proves the mock contract, not bus behavior.
- For applicable AXI-Lite interfaces test aligned full-word reads/writes,
  byte/partial writes and WSTRB semantics, valid and invalid offsets,
  AW/W independence, BRESP/RRESP, backpressure, and reset. For invalid
  transactions, check the expected error in simulation; **do not
  deliberately provoke bus faults in development HIL**.
- The real Linux backend must have **separate target-architecture
  verification**: inspect how its actual CPython/native implementation
  emits aligned memory accesses (including ARMv7 STR versus STRB),
  memory mapping attributes and any required barriers, and confirm
  behavior in bounded real-PS HIL. `struct.pack_into("<I", ...)`
  specifies byte representation but **does not guarantee a single
  32-bit device-register write**.
- **Never equate** Cocotb RTL PASS with ARM/Linux/PS7-to-PL MMIO PASS.
  Record software-driver regression, RTL transaction simulation,
  target-access-width validation, and real HIL as distinct results.
- Prefer small new regression cases and reuse of existing tests over
  introducing a whole-SoC co-simulation framework for a prototype.

See `docs/development/fpga-verification-guide.md` for the practical
verification matrix and accepted limitations. The 2026-10-15 PSPL-02
CONTROL-page SIGBUS remains **an unproven root-cause hypothesis** until
ARM instruction and/or transaction evidence confirms it; an abort address
at `base+1` is not proof that the AXI slave saw `AWADDR=base+1`.

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
    -> approved-scope Z2 hardware validation (when applicable)
    -> merge approval (for PR integration)
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
  power/voltage, or programming a real IC requires explicit coverage in the **approved Gate 1 scope**
  under the root `AGENTS.md`. Do not invent a separate deployment/hardware approval gate.
  Internal-loopback prototype HIL defaults to the root's `development` profile and canonical
  autonomous Codex execution command; operations outside that scope still need authorization.

Never turn a software/simulation pass into a claim of hardware validation.