# PLASMA FPGA SystemVerilog Coding Standard (v1)

Applies to **new or substantively revised** RTL under `pl/`. This supplements
`pl/AGENTS.md` and the existing FPGA development/verification guides.
The public reference is the [lowRISC SystemVerilog style guide](https://github.com/lowRISC/style-guides/blob/master/VerilogCodingStyle.md);
OpenTitan is an example of applying it to production IP. This is a
Zynq/Vivado project, not an ASIC tapeout: **verified toolchain support and
existing ABI contracts take precedence over stylistic uniformity**.

## Architecture boundaries

- Each independently controlled **Programming Site** owns its command,
  cancellation, response retention, PHY timing and fault state.
- Keep AXI-Lite bus reception, register/ABI decoding, transaction control,
  SWD protocol framing and waveform generation clearly separated. Do not
  implement protocol clocks by Linux GPIO/MMIO bit-banging.
- Use a dedicated synthesizable **test-only** responder when a bitstream
  requires host internal-loopback evidence. Python cocotb models are never
  synthesizable. Never advertise fixture coverage as a physical SWD target.
- Keep established PSPL-02/SWD-00 ABI, evidence and board projects unchanged
  unless a separate, explicitly accepted migration has been specified.

## SystemVerilog RTL

- Use `logic`, `always_ff` and `always_comb`. Nonblocking `<=` is
  mandatory in clocked processes; blocking `=` is used for combinational
  logic. One clocked owner per register, no inferred latches.
- Name every FSM type: `typedef enum logic [N-1:0] { ... } state_e;`.
  Choose an explicit 4-state base type, and use a named `default` branch
  with a safe recovery policy. Do not fabricate an FSM where handshake flags
  are simpler and demonstrably safe.
- `typedef struct packed` is appropriate for atomic in-domain command/
  response records whose fields always travel together. It is not mandatory
  for externally inferred Vivado AXI ports or memory-mapped ABI registers.
- Prefer typed `localparam` for widths, bit positions, register addresses,
  status encodings, defaults and masks. Expose `parameter` only for supported
  IP customization. Use `package` for definitions shared between modules;
  packages must be dependency-acyclic and explicitly compiled before users.
- Use exact-sized literals, explicit casts/ranges where required, and
  compare one-bit predicates against their intended width. Compute masks
  from named widths. Check numerical limits at the software/RTL boundary;
  never silently truncate an invalid configuration.
- For portable Icarus/Vivado builds, prefer tested syntax such as
  `localparam integer` for nonnegative width/index constants if the
  supported Icarus release rejects `localparam int unsigned`. This is a
  **tool compatibility choice**, not a reason to eliminate symbolic types.
- Avoid `casex`, `full_case`, synthesis-only `X` don't-cares and global
  lint-waiver flags. A waiver must be local, documented and justified.
- Clock and reset semantics must be stated per module. PS FCLK synchronous
  peripheral reset must not be silently changed to an asynchronous reset.
  Reset/abort must return SWCLK and the SWDIO drive-enable to safe levels.
- Do not rename accepted ports or change accepted ABI encoding merely to
  achieve cosmetic suffix/style alignment. New module-local names should be
  descriptive and use `lower_snake_case`; registered/next-state signals
  may use `_q`/`_d`.

## Protocol properties that matter more than style

- AXI4-Lite AW and W channels are independently handshaken; handle any
  arrival order, partial WSTRB updates, held B/R backpressure and invalid
  addresses. Do not acknowledge commands that cannot safely execute.
- START must snapshot the *entire* SWD command, not just a GO bit. Active
  registers must not change until that transaction finishes.
- Hold response metadata and data until explicit host consumption, including
  under stalled reads. Abort and timeout of a write do not prove that the
  target was unmodified; never silently replay such a write.
- Multi-Site operation must not share unstated locks, reset coupling or
  implicit zero-based public Site numbering.

## Mandatory evidence tiers

1. **RTL**: strict Verilator lint and Icarus elaboration without silencing
   design warnings; explicit tool/compiler versions.
2. **Host simulation**: cocotb/pytest, assertion activation, reference/target
   independence; deterministic seeds and failure artifacts.
3. **Integration**: AXI-to-SWD control/response coverage, preserved baseline
   regressions, and software/ABI compatibility checks.
4. **Vivado**: separately recorded synthesis, implementation, timing, DRC,
   HWH address/pin/clock/reset checks, bitstream and manifest SHA256.
5. **HIL**: real board, voltage, pad/IOBUF and target SWD checks only when
   explicitly scheduled and authorized; never inferred from earlier tiers.

A CI result is labelled with exactly the tiers it actually exercised.
Do not mark Vivado, Z2 or real DUT acceptance PASS on a simulator result.
