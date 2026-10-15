# PLASMA Linux MMIO Backend v1 — prototype engineering contract

**Scope:** production Python module, host-only acceptance and SWD-05 adapter
injection. The current PYNQ-Z2 SWD-03 image implements **one** transaction
aperture, not eight. **Real Z2 MMIO on this branch: NOT RUN.**

## Runtime and layering

- PLASMA PPU target ARMv7 runtime qualification baseline: **CPython 3.12.13**,
  independently installed under `/opt/plasma/python/3.12.13/`.
- Never replace PYNQ's system Python 3.10. The MMIO backend does not import
  `pynq` or `python-periphery`; it uses Linux `/dev/mem`, POSIX `mmap`,
  `fcntl.flock` and native `memoryview(...).cast("I")`.
- `plasma_interfaces.swd_transaction.SWDTransactionDriver` owns SWD
  command/response sequencing; `linux_mmio.LinuxMMIO` owns mapping, exact
  address/operation policy, per-access synchronization and cleanup. FPGA
  Manager / clocks / resets / firmware reload are **outside this module**.
- Cocotb injects its AXI BFM into the **same production SWD-05 driver**.
  Cocotb does not run the Linux /dev/mem backend. Host file-backed mmap
  regression does not qualify native ARMv7 MMIO.
- This is a cooperative user-space backend, **not a Linux kernel driver**.
  No kernel device ownership or AXI response observability is added.

## Explicit SWD-05 injection

This is a **design example, not permission to touch a live board**. Only run
under an approved, supervised Z2 HIL procedure after firmware identity,
clock/reset, current PL ownership, known-good recovery and UART checks.

```python
from plasma_interfaces.linux_mmio import LinuxMMIO, swd03_aperture
from plasma_interfaces.swd_transaction import SWDTransactionDriver

base = 0x40003000  # only the current verified SWD-03 source ABI aperture
with LinuxMMIO([swd03_aperture(base)]) as mmio:
    with mmio.claim_site(site_id=1, base=base) as port:
        swd = SWDTransactionDriver(port, base=base, site_id=1)
        # Command/DPIDR HIL must be executed only by an authorized runbook.
        # No implicit FPGA load, reset or target programming.
```

Caller must supply immutable exact readable/writable register-offset sets for
other IP blocks. Do not derive authorization from user-controlled HTTP
addresses. Register address and u32 value validation occurs before touching
the mapping. Current SWD-03 policy makes COMMAND write-only, ABI/STATUS/
META/RDATA read-only and permits config registers per the SWD-03 ABI.

Every `LinuxMMIO` instance owns one process-global advisory lock file at
`/run/lock/plasma-mmio.lock`. Deploy exactly one shared instance per PPU
process. `claim_site` issues one Site ID/aperture lease at a time; duplicate
claims fail. Each SWD Driver must have **one dedicated lease**, must not share
it with another driver, and must own its own SWD transaction lock. The
backend's short `RLock` serializes individual read32/write32 and mapping
lifecycle actions without holding the lock across whole SWD transactions.
Different Site threads can progress independently between accesses; they
still contend for the common AXI fabric and Python runtime.

**Limitations of ownership:** `flock` is *advisory*. Root processes accessing
`/dev/mem` by another path, a different lock file, a kernel/PL driver, DMA,
or stale process mappings can bypass it. Maintenance must independently
verify and quiesce actual kernel, PYNQ, UIO and user-space PL consumers.
A Site lease is a cooperative usage token, not an OS/hardware capability;
never pass the same lease to two independent SWD Driver instances.

## Lifecycle and failure semantics

- `with LinuxMMIO(...)` opens `/dev/mem` with `O_SYNC` and uses a
  nonblocking advisory owner lock. Configuration only opens device on explicit
  `open()` / context enter, never on construction.
- The first valid address in an approved aperture lazily maps its reviewed
  page. Real u32 loads/stores index a native 4-byte view; never use
  `struct.pack_into` to write registers.
- `close()` is final and idempotent, synchronizes with single accesses,
  invalidates all leases, releases each exported view before closing
  each mmap, and closes descriptors. Reopening requires a **new instance**.
- `quiesce_for_reload()` refuses with active Site leases. The FPGA owner must
  also stop all in-flight SWD sequences and external consumers before any
  FPGA Manager load; this method does not prove those conditions and never
  programs the PL. Reconfiguring while a surviving MMIO mapping exists is
  forbidden by deployment policy, not prevented by this Python module.
- If an mmap/access call raises a catchable error, the backend is poisoned
  and refuses subsequent reads/writes; no automatic START/WRITE retry.
  A write may have committed even if software observed an error.
- POSIX `mmap` + `memoryview` **cannot reliably translate AXI SLVERR/
  DECERR into Python exceptions**. An External Abort may deliver SIGBUS or
  stall ARM/Linux indefinitely; a Python timeout, lock, `try/except` or
  background thread cannot guarantee recovery. This remains an explicit
  gap versus the synchronous SWD-05 `WordMMIO` ideal AXI-error contract.
  Deliberate invalid AXI transactions belong in Cocotb **only**.
- Memory barriers and device cacheability/order depend on Linux mapping
  attributes and ARMv7. Confirm physical write width (`STR`, not `STRB`),
  read width (`LDR`), memory attributes, PYNQ PS7 GP0 and reset state on
  the exact Z2 image/CPython runtime. Host unit tests cannot prove this.

## Test strategy / sign-off

| Evidence level | Acceptance | This change |
|---|---|---|
| Python host | immutable allowlist, word width, RO, bad input fail-closed, resource lifetime, multiple Site leases, thread/close race, SWD-05 ABI-only injection | CI target, Python 3.12 |
| RTL Cocotb | the **existing SWD-06** tests exercise the real SWD-05 driver via AXI BFM, SWD-03 RTL & synthetic target | Retained regression; not raw mmap |
| ARMv7 native | exact PLASMA CPython 3.12.13 in target image emits single 32-bit register accesses with correct mapping attributes | NOT RUN |
| Z2 PS/PL | valid Build ID, approved CONTROL/STATUS, existing SWD-00 loopback; no invalid AXI transactions | NOT RUN for this backend |
| Z2 SWD-03 | supervised SWD-05 Internal DPIDR fixture, explicit line reset/read/ACK, recover original base | NOT RUN |
| Multiple physical Sites | separate SWD hardware apertures, failure isolation, concurrency stress | NOT RUN; current RTL only Site 1 |
| Target programming | external SWD pins, power, MCU erase/program/verify | NOT RUN |

Hardware test acceptance must identify source SHA, Z2 hardware identity,
candidate `.bin` hash, known-good recovery `.bin/.hwh`, real loaded Build ID,
runtime path and exact Python patch version, kernel/build logs, actual driver
operations, no new AXI errors, and observed base restoration. Do not probe
invalid addresses or intentionally trigger SLVERR in live hardware.

## Next step after host CI

Use the existing PSPL-02/SWD-00 hardware fixtures, **not a new eight-Site
bitstream**, for the first short supervised Z2 HIL. Build a dedicated
MMIO-LT-01 test fixture only if the existing CONTROL/STATUS path cannot
reveal a required failure mode. The physical SWD-03 HIL remains independently
qualified and is not inferred from previous PSPL-02 tests.
