# PSPL-02 / SWD-00 internal PL Loopback Baseline

Host-only integrated candidate; Z2 loading is not qualified. HIL-PSPL-01,
its Identity-only design, evidence and artifacts remain unchanged.

PS7 GP0, FCLK0 100 MHz and synchronized active-low reset serve three disjoint
4 KiB segments: Identity `0x40000000` (unchanged ABI v1, flags 0), Control
`0x40001000`, and SWD command `0x40002000`. Only DDR/FIXED_IO are external.
There are no SWD pins, IOBUF, EMIO GPIO or PMODB connections.

Control offset 0 is WSTRB-aware RW CONTROL (reset 0); offset 4 is RO
STATUS = CONTROL XOR `0xA5A55A5A`. Its existing behavior is preserved.

## SWD command ABI v1

Offsets below are relative to `0x40002000`; all accesses are aligned 32-bit.

| Offset | Ownership | Reset | Meaning |
|---|---|---|---|
| 00 | RO | 1 | ABI version |
| 04 | WO/read-zero | 0 | START=1, CLEAR=2, RESET=4 |
| 08 | RW idle | 0 | TX data, LSB first |
| 0C | RW idle | 0 | Bit count; legal writes 1..32 |
| 10 | RW idle | 2 | Half-period in FCLK cycles; 2..65535 |
| 14 | RW idle | 0 | SWDIO drive enable; 0/1 |
| 18 | RO | 0 | Last completed RX data |
| 1C | RO | 0 | BUSY[0], DONE[1], ERROR[2], SWCLK[3], output[4], OE[5] |
| 20 | RO | 0 | First semantic error: command=1, busy=2, config=3, engine=4 |
| 24 | RW idle | 0 | Responder mode: echo/pull-high=0, RX pattern=1 |
| 28 | RW idle | 0 | Independent responder RX pattern |

No queue: accepted START reserves BUSY immediately and snapshots engine and
responder inputs. Config writes, START and CLEAR during BUSY return SLVERR,
preserve the active transfer and set sticky first ERROR. DONE is sticky on
completion; ERROR is sticky on semantic rejection or engine error. Idle CLEAR
or a valid accepted START clears DONE/ERROR/error code. CLEAR preserves RX and
configuration. RX changes only on completion or reset. STATUS is an AXI read
snapshot, so it can remain stale while RREADY is low.

RESET is accepted during BUSY and aborts the engine, restoring configuration,
RX and flags to defaults. It does not discard pending AXI responses. External
reset clears both AXI state and the engine. After either reset, configure a
legal count before START. Invalid commands/configuration preserve configuration.
Invalid addresses and RO writes return SLVERR without setting semantic ERROR.

RW writes merge bytes according to WSTRB before validating the entire value.
Zero WSTRB is a no-op at valid writable offsets, including during BUSY.
Nonzero COMMAND writes require WSTRB=0xF and exactly one defined command value.
AW and W may arrive independently; one response per accepted write is retained
under backpressure. Undefined, unaligned and out-of-aperture slave addresses
return SLVERR; the interconnect's unmapped-address response is its own contract.

The reusable waveform engine is unchanged: 1..32 LSB-first pulses, idle-low
SWCLK, sampling at the end of each high phase. Mode 0 echoes driven output or
returns logical 1 while OE=0. Mode 1 supplies the latched independent pattern,
advancing its index after each falling edge. This is a digital fixture, not
physical Hi-Z, SWD turnaround, ACK/parity or target qualification.

## Mandatory regression and isolated build

Before adding SWD transaction features, this baseline must continue to pass:

```bash
python3 -m pytest -v pl/verification/test_pspl02_swd00_rtl.py
python3 -m pytest -q pl/tests/test_z2_control_waveform_build.py
```

Cocotb uses deterministic vectors/seeds, all WSTRB masks, independently ordered
AW/W, R/B backpressure, invalid commands, busy protection, reset recovery,
back-to-back transfers, independent RX patterns, every waveform half-period,
and 32-bit / 65535-cycle boundaries. Verification-only immediate assertions
check held AXI responses and engine invariants in Icarus; temporal SVA support
is not claimed. Failure waveforms/XML remain under `pl/build/pspl02-swd00/sim/`.

Commit clean sources before running:

```bash
PLASMA_BOARD_REPO=/path/to/pinned/board-repository \
PLASMA_TEST_PYTHON=/path/to/cocotb/python \
bash pl/projects/z2-control-waveform/build-on-swpc.sh
```

The board repository must be clean at
`e02d6a3866b5465218f777168cdc51344ac94e07`. Vivado 2026.1 uses the PYNQ-Z2
preset/xc7z020clg400-1, 50 MHz crystal and 100 MHz FCLK0. Host regressions run
before each build. Unique build directories preserve previous runs. Timing
must pass setup/hold; blocking DRC and critical warnings fail closed. HWH checks
all three decoder/segment bases, GP0 clock, synchronized reset and absence of
external PL pins. Bitstream/HWH SHA256 and log/report hashes enter the manifest.
Preserve each known-good entire run directory for future comparison; large
bitstreams are not committed. Building never executes ps7_init or loads FPGA.

## Evidence levels

- LB-HOST: only PASS after RTL regression and implemented Vivado artifact checks.
- LB-Z2: NOT RUN; requires real PS -> AXI -> PL -> AXI -> PS verification.
- Real SWD target: NOT RUN; no physical SWD or IC programming qualification.

Current-source CI validates simulation/lint/artifact contracts on hosted runners.
It does not run an unreviewed PR on the persistent SWPC runner or prove Vivado/HIL.
