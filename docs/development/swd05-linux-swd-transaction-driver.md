> **HISTORICAL / SYNTHETIC-ONLY SWD-05 DRIVER, NOT AN EXTERNAL BLUE PILL ROUTE.** Real Blue Pill programming uses Z2 PS-local ARMv7 OpenOCD → UNIX WordPort/RemoteBitbang → reviewed PL SWD Image → PMOD. Follow [retirement inventory](swd-legacy-path-retirement.md); old internal loops and synthetic ACK/DPIDR cannot establish physical MCU success.

# SWD-05 — Linux PS SWD-03 AXI Transaction Driver (host-only)

**State:** software integration candidate. Requires SWD-05 Gate 2 before merge.
PYNQ-Z2 is offline/not available; **no physical HIL, FPGA loading or IC
programming** is performed in this stage. This is a transport abstraction,
not the registered production `FPGAInterface`, a Flash driver or OpenOCD
adapter. The source of truth for physical SWD protocol remains
`pl/rtl/site/swd_transaction_master.sv` and its SWD-03 AXI adapter; this
change does **not** modify the FPGA ABI or hardware timing.

## Separation of responsibilities

```text
One PPU Site-owned Python SWDTransactionDriver
    -> injected WordMMIO(read32, write32), NO built-in physical backend
    -> SWD-03 AXI adapter 0x40003000 (4KiB)
    -> FPGA SWD Transaction Master / digital SWD waveform
    -> internal test fixture only until Z2/physical HIL
```

The SWD-05 driver never directly opens `/dev/mem`, UIO or PYNQ Overlay.
The separate, explicit `LinuxMMIO` candidate in
[Linux MMIO Backend v1](linux-mmio-backend-v1.md) can now be injected
via an aperture-scoped Site lease. **This is NOT an assertion of physical
Z2 qualification.** Raw Linux /dev/mem cannot reliably surface AXI
SLVERR/DECERR as catchable Python exceptions; that remains a deliberate
qualification and hardware-fault policy gap. The existing Cocotb AXI BFM
does report AXI responses and exercises the production SWD driver. Creating a driver object
reads only the ABI register (must be 1); it does not write any register,
configure clocks, reset the chip, or load an FPGA.

One object belongs to exactly one logical Site (`site_id=1..8`,
one-based). A hardware-provided aperture is explicit and 4KiB aligned;
the SWD-03 reference build supports only one hardware instance at
`0x40003000`. Software type validation of `site_id>1` **does not**
establish additional physical Site support. The MMIO backend must turn
AXI SLVERR/DECERR into Python exceptions and serialize access; no
background owner may share the same register aperture.

## API

```python
from plasma_interfaces.swd_transaction import (
    SWDTransactionDriver, SWDTiming, SWDDriverError,
)

# 'mmio' must be a separately validated and explicitly injected
# synchronous 32-bit register backend. There is NO default live backend.
swd = SWDTransactionDriver(mmio, site_id=1)

swd.line_reset()           # SWD recovery clocks; no target reset pin
dpidr = swd.read_dp(0x00) # expects target DPIDR 0x2BA01477 for fixture

# Only after real target qualification (not for current synthetic fixture):
# swd.write_dp(0x04, value)
# raw = swd.read_ap_raw(0x0C)
# result = swd.read_ap_posted(0x0C)  # explicit AP read then DP RDBUFF
```

Reads/writes are raw four-register DP/AP transactions with addresses
`0x00, 0x04, 0x08, 0x0C`; there is **no MEM-AP bank/SELECT policy** or
automatic DP sticky clearing. `read_ap_raw()` returns the posted SWD wire
value, not necessarily the requested AP result;
`read_ap_posted()` first issues AP READ then DP RDBUFF (0x0C).
The caller remains responsible for AP select/address/banking, eventual
MEM-AP semantics and target protocol compatibility.

`SWDTiming` validates the FPGA accepted range:
half-period 2..65535 cycles, turnaround 1..4, idle 8..255,
extra WAIT retries 0..255, total active FCLK timeout 1..0xFFFFFFFF,
and explicit ORUNDETECT error-data-phase policy. Defaults match SWD-03
reset configuration; each transaction snapshots all timing/config words
while idle and executes one START. The driver does not contain a command
queue, run parallel transactions, or retry an operation on its own.

## Safety and error semantics

- Explicit Line Reset is required after link reset; hardware next requires
  DP DPIDR read before other raw DP/AP operations. No implicit reset.
- Polling is bounded by both time and iteration budget.
  **A Python timeout cannot interrupt an AXI bus stall or hang Linux**.
  On uncertain bus errors or unconsumed response, the driver is poisoned
  and refuses further operations until *external* safe recovery.
- Stable response META/RDATA is captured twice. The driver explicitly
  writes `ACK_RESPONSE` **once** after capture. It does not acknowledge
  a response before reading it, and never repeats START after an uncertain
  write. Hardware SWD WAIT retries are bounded by configured retry count
  and represented in `attempts`.
- SWD response statuses are preserved: OK, BAD_CONFIG, NEED_RESET,
  WAIT_LIMIT, FAULT, BAD_ACK, PARITY, TIMEOUT, ABORTED, PHY_ERROR.
  Failure raises `SWDDriverError` carrying `response` (when available)
  and `uncertain_target_effects`. A bad ACK/parity/timeout/abort/PHY
  failure of a write can leave physical target effects; no automatic replay.
- A successful SWD write transport response **does not prove target Flash
  committed**. The caller/Programming Engine must check DP sticky
  `WDATAERR` and device programming semantics where appropriate.
- `request_abort()` is safe to signal from a second Python Thread: it
  only sets a cancellation Event; the owner of the polling operation issues
  the single ABORT MMIO write if STATUS still confirms BUSY, then handles
  the ABORTED response. The signal is not a guarantee of physical rollback.
  If the target has already completed, no ABORT write is necessary.
- `abort()` is a separate explicit synchronous cancellation only if
  hardware STATUS confirms BUSY **and no other caller is concurrently
  operating the same driver**. It cannot safely rescue a poisoned
  driver or interrupted Linux bus.
- The driver serializes single-Site transactions with a re-entrant lock;
  `read_ap_posted()` protects AP READ + DP RDBUFF as one logical sequence.
  Separate processes or distinct driver instances sharing the same aperture
  remain forbidden until exclusive ownership/arbitration is implemented.
- No real IC erase/program/verify or power/voltage functions exist.
  `plasma_interfaces.fpga.FPGAInterface` remains fail-closed.

## Evidence

Host-only CI uses `software/python/tests/test_swd_transaction_driver.py`
with an injected fake-AXI register/transaction target (not cocotb and not
real HDL co-simulation). It covers exact ABI encoding, line-reset/DPIDR,
DP read/write, posted AP semantics, explicit response ACK, WAIT/FAULT/
PARITY/TIMEOUT/ABORT errors, invalid timing/address/value rejection,
uncertain AXI START writes, MMIO exceptions, stuck BUSY, separate Site
ownership and absence of implicit retries.

The previously merged SWD-03 cocotb/Icarus/Verilator regression remains
the HDL evidence. SWD-04 provides an *independent*, not-yet-executed Z2
HIL plan and supervision boundary. SWD-05 does not change either.

### Qualification matrix

| Gate | State |
|---|---|
| SWD-03 Vivado HOST | PASS (retained historical evidence) |
| SWD-05 Python/fake-AXI | Subject to CI |
| SWD-05 RTL↔Python differential | NOT_RUN |
| SWD-05 Z2 PS/PL HIL | NOT_RUN |
| SWD-05 production FPGAInterface wiring | NOT_RUN |
| Physical SWD/target programming | NOT_RUN |

Future HIL must not silently reclassify an injected fake backend as a
qualified Z2 MMIO backend. No valid fake test can prove electrical
turnaround, PS AXI interconnect hang recovery or real IC programming.
