# SWD-01 / SWD-02 transaction transport and virtual target

This host-only stage adds `swd_transaction_master` above the unchanged
SWD-00 waveform engine. The PR #892 AXI register ABI, internal loopback,
Vivado project, artifacts and HIL acceptance records are unchanged.
No external pins or software-visible registers are added.

## Command and PHY boundary

One instance belongs to one independently controlled Site. All command signals
are sampled on `cmd_valid && cmd_ready` in the single `clk` domain. There is one
outstanding command; no queue or shared Site scheduler. Responses remain stable
until `resp_valid && resp_ready`. Holding a new command during BUSY cannot replace
the accepted command. Reset is active-low, synchronous to `clk`; output clock
and drive enable are also gated low when reset is asserted.

| Input | Contract |
| --- | --- |
| `cmd_op` | 0 raw DP/AP transfer; 1 line recovery/reset |
| `cmd_ap`, `cmd_read` | AP versus DP; read versus write |
| `cmd_addr` | Aligned byte register address: 0, 4, 8, 12 |
| `cmd_wdata` | 32-bit write payload |
| `cmd_half_period` | 2..65535 FCLK cycles per SWCLK half-period |
| `cmd_turnaround` | 1..4 SWCLK cycles, must match target |
| `cmd_idle_cycles` | 8..255 host-driven LOW clocks after each transfer attempt |
| `cmd_max_retries` | 0..255 additional WAIT attempts |
| `cmd_error_data_phase` | Must match target ORUNDETECT data-phase setting |
| `cmd_timeout_cycles` | Nonzero total active FCLK deadline, including retries |
| `cmd_abort` | Abort active command locally; does not discard a pending response |

All configuration fields are validated even for line reset. Invalid configuration
returns BAD_CONFIG without wire activity. No other command fields are read after
acceptance. Timeout excludes response backpressure. Software must budget segment
launch overhead as well as wire clocks; a deadline shorter than a transfer safely
terminates it but does not undo target effects.

| Response status | Value | Meaning |
| --- | --- | --- |
| OK | 0 | Transport completed |
| BAD_CONFIG | 1 | Invalid command configuration |
| NEED_RESET | 2 | Link initialization sequence required |
| WAIT_LIMIT | 3 | Bounded WAIT retries exhausted |
| FAULT | 4 | Target FAULT; no automatic replay or sticky-error clearing |
| BAD_ACK | 5 | Invalid ACK, including floating/no-target response |
| PARITY | 6 | Read data parity mismatch |
| TIMEOUT | 7 | Active command deadline reached |
| ABORTED | 8 | Local abort |
| PHY_ERROR | 9 | Waveform primitive rejected a segment |

`resp_ack` preserves the last three-bit ACK; `resp_attempts` is nine bits
(0 for reset/rejected commands, 1..256 for transfers). `resp_data_valid` is true
only for an OK read. Otherwise `resp_rdata` is zero. ACK OK on a write precedes
the data phase and does **not** prove target write completion: target WDATAERR
must be checked by the caller where required. Aborting or timing out a write
can leave target effects; automatic write replay is forbidden except a received
WAIT whose protocol semantics say the access was not accepted.

`link_state` is 0 (reset required), 1 (DPIDR required), or 2 (connected).
After local reset, perform line reset, then DP DPIDR read before other accesses.
Bad ACK, read parity error, abort, timeout or PHY error requires recovery.
WAIT/FAULT remain explicit responses rather than silent recovery operations.

## Wire behavior and ARM reference

The primary reference is [ARM IHI 0031D, ADIv5 architecture specification](https://documentation-service.arm.com/static/5f900abff86e16515cdc063b),
sections B4.1, B4.2 and B4.3; AP posted access also uses B2 register semantics.
The supported subset is point-to-point SWDv1. SWDv2 multidrop, dormant transitions,
JTAG-to-SWD selection and a real MEM-AP are not qualified here.

Requests are eight bits, LSB first, with even request parity and defined
start/stop/park bits. ACK is three bits (OK=1, WAIT=2, FAULT=4). Data is 32 bits
LSB first plus even parity. Ownership is released for each configured turnaround.
Read responses have target data/parity followed by turnaround; writes have
turnaround before host data/parity. With ORUNDETECT, WAIT/FAULT still includes
the configured data phase: read data floats and is ignored; write dummy data is
zero and has no modeled target register effect.

B4.3.1 specifies that the target samples host data and updates its own output on
rising SWCLK edges. The virtual target therefore updates after the rising edge;
the unchanged waveform engine captures later in HIGH, before generating the
falling edge. Host bits are prepared during LOW. Segment boundaries may extend
LOW; HIGH duration remains exactly the configured half-period. These digital
checks do not establish external pad timing, CDC, cable or electrical margins.

The master stops SWCLK between commands, so every normal attempt emits at least
eight LOW idle clocks (B4.1.1). Line recovery emits 64 released clocks to finish
possible interrupted request/response phases, then 64 host-driven HIGH clocks
and eight LOW clocks. The latter exceeds the B4.3.3 minimum of 50 HIGH and two
LOW. Target turnaround returns to one after line reset; the caller must update
its next command accordingly. Invalid ACK drains a possible 33-bit read response
and four turnaround clocks without driving, then requires explicit line reset.
The released recovery preamble cannot roll back a partially delivered write.

## Independent reference and target

`verification/models/swd_reference.py` is a transaction-level oracle, independent
of the RTL and line target. `virtual_swd_target.py` parses only SWCLK edges and
resolved SWDIO ownership/data. It cannot inspect command fields or RTL state.
The fixture implements DPIDR `0x2BA01477`, ABORT sticky-error clearing,
CTRL/STAT, SELECT, RESEND and RDBUFF. Power acknowledgments are immediate virtual
responses. Unsupported banked DP/AP accesses fail closed with FAULT.

AP transport and posted reads are separate test stages: the synthetic AP has one
scratch register and IDR `0x00000001`, not a MEM-AP. AP reads return the previous
posted value; RDBUFF obtains the pending result. DP reads preserve pending data;
a subsequent AP or DP write invalidates it. The deterministic `0xDEADBEEF`
invalid-value fixture is not an architectural promise. RESEND returns the last
AP-read/RDBUFF wire result. Line reset preserves DP sticky/register state and
resets link/turnaround; global line-reset recognition is a fixture choice.

Injected WAIT/FAULT on normally exempt DP accesses, malformed ACK, silence and
bad parity deliberately model faults, not conforming responses for every DP
register. Write parity failure sets WDATAERR without retroactively changing ACK.

## Regression gate and evidence levels

Run with Icarus, Verilator, pytest, cocotb 1.9.2 and cocotb-test 0.2.6 installed:

```sh
python3 -m pytest -q pl/tests pl/verification/test_pspl02_swd00_rtl.py pl/verification/test_swd_transaction_rtl.py
verilator --lint-only --sv -Wall --top-module swd_transaction_master pl/rtl/site/swd_transaction_master.sv pl/rtl/site/swd_waveform_engine.sv
```

CI runs the PR #892 loopback regression before new transaction regression, on
GitHub-hosted runners. No persistent integration runner or Vivado build is used.
The new master has no Verilator warning suppression. The original lint failure
was SYMRSVDWORD for port `abort`; the interface now uses `cmd_abort`.

| Stage | Required checks |
| --- | --- |
| Existing baseline | Control register loopback, waveform primitive, AXI command/responder and artifact contracts |
| DP transaction | DPIDR framing, data/parity, DP writes/reads and backpressure |
| Error/recovery | WAIT retries through 256 attempts, FAULT, invalid ACK, silent target, read/write parity, abort, deadline and reset |
| PHY boundary | Turnaround 1..4, LSB first, drive/release ownership, half-period 2/3/9, idle 8/33, 32-bit data |
| AP transport | Synthetic AP scratch/IDR raw access |
| Posted reads | AP pipeline, RDBUFF, RESEND, DP-read preservation and write invalidation |
| Site isolation | Two concurrent instances; reset one while the other completes |
| Checker activation | Deliberate stalled-response mutation must fail assertion |

The maximum divider configuration is accepted and bounded by the watchdog;
this suite does not complete a full transaction at divider 65535. Deterministic
randomized data uses seed `0x53574412`. Waveforms, result XML and per-test JSON
wire/command evidence remain under ignored `pl/build/swd01-02/sim/`; CI uploads
failure evidence. Immediate clocked assertions check ownership of command and
response state, deadline and stable stalled responses. Icarus reports `$fatal`
as non-synthesizable in these verification-only checkers; they are intentionally
excluded from production RTL and build source lists.

Host simulation and strict RTL lint qualify only this digital stage. Verilator
simulation, new Vivado synthesis/implementation/timing/bitstream, LB-Z2 and real
SWD target qualification remain **NOT RUN**. Prior LB-HOST and HIL-PSPL-01 records
remain their own acceptance evidence, not evidence for this new master.

## Future integration boundary

An AXI adapter must latch the entire command atomically, retain responses until
software consumption, expose target effects as uncertain after interrupted writes,
and provide independent per-Site reset/abort/status. It must have an explicitly
reviewed register ABI; no accepted PSPL-02/SWD-00 register is repurposed here.
AP selection, posted-read sequencing, sticky-error recovery and real programming
algorithms belong above this transport. Each later Site may instantiate its own
master/PHY; no global lock or zero-based public Site identity is introduced.
