# SWD-03: PS AXI-Lite to Internal Synthetic DPIDR Target

**Status:** source/CI verification candidate. Vivado synthesis/implementation/
timing/handoff/bitstream **NOT RUN** until an actual SWPC build is reviewed.
Physical Z2 SWD, pin-level timing, IOBUF, voltage, HIL and IC programming
**NOT QUALIFIED**.

This is a *new, isolated project*. It does **not** replace or mutate the
retained `pl/projects/z2-control-waveform/` 3-aperture build or its evidence.
PYNQ-Z2 PS7 runs FCLK0 at 100 MHz, with synchronized active-low reset and
GP0 control. Only DDR/FIXED_IO are external. **No SWD PMOD pins**.

## Address and fixture topology

| GP0 base | Vivado instance | Contract |
|---|---|---|
| `0x40000000` | `identity_0` | Identity ABI v1; CAPABILITY_FLAGS=0 |
| `0x40001000` | `control_0` | Existing control/status behavior |
| `0x40002000` | `swd_0` | Existing waveform digital loopback |
| `0x40003000` | `transaction_0` | New SWD transaction AXI ABI v1 |

Each address segment is exactly **4 KiB**, non-overlapping. The new transaction
module emits `swclk`, `swdio_out` and `swdio_oe` **internally** to
`fixture_0: swd03_dpidr_responder`; `swdio_in` returns on an internal net.
The fixture responds to SWD line reset, then to **DP DPIDR read only**
(value `0x2BA01477`) and rejects other requests with FAULT. It neither
models a real IC nor supports production SWD writes/Flash programming.

The simulator also tests the independent Python VirtualSWDTarget against
the AXI adapter. The synthesizable fixture test is separate.

## SWD-03 register map (32-bit word accesses)

| Offset | Access | Meaning |
|---|---|---|
| `0x00` | RO | ABI version = 1 |
| `0x04` | WO/read zero | START=1, ABORT=2, ACK_RESPONSE=4 |
| `0x08` | RW idle | CONFIG: OP[0], AP[1], READ[2], ADDR[6:3], ERROR_DATA_PHASE[7] |
| `0x0C` | RW idle | SWD write data |
| `0x10` | RW idle | Half-period 16-bit cycles; reset 2 |
| `0x14` | RW idle | Turnaround 3-bit cycles; reset 1 |
| `0x18` | RW idle | Idle cycles 8-bit; reset 8 |
| `0x1C` | RW idle | Max retries 8-bit; reset 0 |
| `0x20` | RW idle | Timeout cycles 32-bit; reset 1,000,000 |
| `0x24` | RO | STATUS: BUSY[0], CMD_READY[1], RESP_VALID[2], LINK_STATE[4:3] |
| `0x28` | RO | META: STATUS[3:0], ACK[6:4], DATA_VALID[7], ATTEMPTS[16:8] |
| `0x2C` | RO | SWD read result, 32 bits |

All registers are fixed-width AXI4-Lite, not arbitrary-width IP parameters.
Writes use WSTRB byte merging, reject reserved bits or inappropriate write
contexts, and produce a response. START is accepted only with command ready.
Response is retained until explicit ACK_RESPONSE; the write result is not proof
of successful target flash commit. No software-ready production driver yet.

## Offline qualification

Before Vivado, the build script runs legacy loopback, SWD Master, new SWD-03
AXI/fixture simulation and HWH fault-injection source tests. Hosted CI checks
Icarus, Verilator lint and regressions, but cannot run Vivado 2026.1 on a
GitHub-hosted runner.

## Isolated SWPC build (AFTER review and correct branch checkout)

Preconditions: checked-in clean SWD-03 feature branch at the reviewed commit,
existing read-only pinned PYNQ-Z2 board cache at commit
`e02d6a3866b5465218f777168cdc51344ac94e07`, Vivado 2026.1 and
the dedicated host Cocotb Python venv.

```bash
cd /storage/projects/plasma/.work/swd03-axi-transaction
git status -sb
# Set this to the *already existing* local clone of the pinned board repository.
export PLASMA_BOARD_REPO=/path/to/existing/pinned/board-repo
export PLASMA_TEST_PYTHON="$HOME/.venvs/plasma-swd03/bin/python"
export PLASMA_VIVADO_JOBS=4
export PLASMA_BITSTREAM_VERSION=0.1.0
bash pl/projects/z2-swd03-axi/build-on-swpc.sh
```

The script does not operate on Z2, use `ps7_init`, rewrite an old run, or
restart services. Each build goes to a new
`pl/build/z2-swd03-axi/run.XXXXXXXX/` directory, guarded by a lock.
The first line prints `SWD03_BUILD_DIR=...`. Preserve every run, even failed
runs. Relevant output includes source and toolchain provenance, HWH decoded
4-aperture map, internal signal/clock/reset checks, setup/hold slack, DRC and
methodology reports, `*.bit`/`*.hwh`, SHA256 checks and manifest.

`SWD03_HOST_ARTIFACT_PASS_NO_Z2_OR_TARGET_CLAIM` is permitted only when
all mandatory gates pass. This establishes **implemented host-only evidence**,
not physical Z2 hardware or real target SWD qualification.

The Vivado build can still discover block-design routing/synthesis or timing
issues: **offline CI PASS is not a guarantee of Vivado PASS**.
