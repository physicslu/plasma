# PLASMA Linux MMIO Backend v1 — prototype engineering contract

**Scope:** production Python module, host-only acceptance and SWD-05 adapter
injection. The current PYNQ-Z2 SWD-03 image implements **one** transaction
aperture, not eight. **Real Z2 MMIO qualification: NOT RUN pending live evidence.**

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

## MMIO-13/14/15 — Native PYNQ-Z2 HIL adapter (new integration)

### Explicit development profile

`native_qualify --profile development` is for the dedicated single-developer
Z2 and pinned internal-only four-aperture SWD-03 image. The default remains
`qualification`. The existing comprehensive P0, operator, UART, independent
power recovery and stage-session checks remain unchanged for qualification.

Development uses automated checks rather than operator Boolean assertions:

- Exact ARMv7 little-endian PLASMA CPython 3.12.13 runtime.
- FPGA Manager operating, enabled 100MHz FCLK0, and a protected loader
  receipt matching the current boot and **last** FPGA Manager load.
- Pinned BIN digest and internal-fixture Build ID/ABI/address-map provenance
  before MMIO; actual Identity/ABI readback before any writes.
- Kernel resources overlapping the four apertures, relevant UIO bindings,
  PL device fds and retained mappings. Only fd symlinks and relevant mapping
  ranges are inspected; no process-command inventory or unrelated services.
  Unknown retained UIO mappings are conservatively treated as conflicts.
- Production `LinuxMMIO` allowlists/native aligned u32 accesses and the
  production SWD-05 driver with bounded polling.

There is no development Qualification P0, fresh UART login, operator-presence,
maintenance-window, single-developer or repeated no-DUT attestation. Firmware
provenance pins an image with **no external PL I/O**. No arbitrary addresses,
external DUT operations, deliberate AXI faults or HIL03 are supported.
Polling limits cannot interrupt a stalled physical AXI access.

Prefer a compatible already-loaded image with its accepted protected receipt.
Do not reload simply to reset registers: development Identity checks accept
non-reset operational register values while still enforcing exact Build ID and
all three ABIs. Reconfiguration invalidates previous HIL01 evidence.

If the image is incompatible or provenance unavailable, verify the candidate
BIT/HWH/manifest/BIN and usable original firmware/recovery method **before**
a supervised load. Preserve metadata, driver bindings and any service state
that must change. Stop if recovery cannot be established. After testing,
always attempt restoration (also after failure), and verify the original
image, bindings, metadata and service state. The native test runner never
loads or restores firmware itself. Do not reload with a surviving MMIO user.

Immediately after a successful supervised load, the loader can record the
actual firmware named in the last FPGA Manager log (use root-owned firmware
and a private root-owned receipt directory):

```bash
sudo /opt/plasma/python/3.12.13/bin/python3 -m pl.hil.swd04.development \
  --candidate-bin /lib/firmware/approved-internal-swd03.bin \
  --output /private/loaded-image.json
sudo /opt/plasma/python/3.12.13/bin/python3 -m pl.hil.swd04.native_qualify \
  --profile development --stage HIL01 \
  --session /private/loaded-image.json \
  --candidate-bin /lib/firmware/approved-internal-swd03.bin \
  --output /private/hil01 \
  --execute-live --ack-unrecoverable-axi-stall-risk
```

For HIL02 use the same receipt and candidate, a new output directory and
`--previous /private/hil01/result.json`. No `--p0-report` is needed.
The receipt is trusted loading evidence, not cryptographic readback of FPGA
configuration memory. Capture it at load time; do not manufacture historical
receipts from filenames. Loss of the current-boot load log is a fail-closed
provenance blocker. A receipt is never physical HIL PASS.

STARTED is written before MMIO; PASS/FAIL records describe observed stages.
Missing results after a started SIGBUS/stall are incomplete, never PASS.
Actual development measurements and restoration are recorded in
[2026-10-16 evidence](../evidence/mmio-development/2026-10-16.md).

The next hardware candidate uses the **four-aperture SWD-03 design**, NOT the
three-aperture PSPL-02/SWD-00 image. Its source / verified artifact hashes
are specified by `pl/hil/swd04/contract.py`. Keep the physical SWD pins
and external DUT disconnected. Do not use the old SWD-00 firmware for SWD-05.

The safe execution entrypoint is
`python -m pl.hil.swd04.native_qualify`, using the **actual**
`/opt/plasma/python/3.12.13/bin/python3` runtime. The separate
`software/python` package must be installed into that runtime and the
`pl` source modules must be available on the Python import path. The
entrypoint is inert by default. It does **not** change FPGA Manager firmware,
stop/start services, or perform original-image recovery.

Use the existing [SWD-04 offline kit and candidate/recovery runbook](
swd04-offline-execution-checklist.md) to verify the source SHA and hashes,
create current hardware inventory, isolate PL consumers, prove UART/independent
power recovery, and produce a real P0 report, supervised candidate load log
and **actual** stage session evidence. A historical previous HIL result does
not validate the currently loaded candidate.

After the four-aperture candidate is **actually** loaded and identified,
the two native stages are:

1. `HIL01`: `LinuxMMIO(..., readonly=True)`, exact SWD-04
   Identity/Build ID/ABI/Control STATUS register readback. The native backend
   is used through the prior SWD-04 read-only checks, not the old HIL
   `DevMemBackend`. No writes.
2. `HIL02`: independently recheck Build ID and initial state; use
   `LinuxMMIO` at approved CONTROL offsets to write/read six full-word
   non-destructive echo patterns, ending at zero; claim the SWD-03 Site 1
   aperture and invoke the **production** `SWDTransactionDriver.line_reset()`
   and `read_dp(0)` against the synthetic DPIDR fixture. This does not
   connect any external IC or program flash.

Both stages require `--execute-live` **and**
`--ack-unrecoverable-axi-stall-risk`, current root/ARMv7/FPGA Manager
eligibility and the reviewed SWD-04 candidate, recovery, session and
prior-stage evidence. HIL02 additionally requires `HIL01` PASS from the
**native** tool with the same P0 digest. An unsupported Python version,
runtime path or architecture fails **before opening /dev/mem**.

Example command skeleton (paths must be resolved from actual retained private
files; do not execute with placeholders):

```sh
/opt/plasma/python/3.12.13/bin/python3 -m pl.hil.swd04.native_qualify \
  --stage HIL01 --p0-report "$P0" --session "$HIL01_SESSION" \
  --candidate-bin "$CANDIDATE_BIN" --output "$EVIDENCE/hil01" \
  --execute-live --ack-unrecoverable-axi-stall-risk

/opt/plasma/python/3.12.13/bin/python3 -m pl.hil.swd04.native_qualify \
  --stage HIL02 --p0-report "$P0" --session "$HIL02_SESSION" \
  --candidate-bin "$CANDIDATE_BIN" \
  --previous "$EVIDENCE/hil01/result.json" --output "$EVIDENCE/hil02" \
  --execute-live --ack-unrecoverable-axi-stall-risk
```

**These commands must only run inside the previously verified, supervised
hardware maintenance procedure.** Use an approved root execution channel;
do not alter system Python or sudoers and do not write credentials to logs.
STOP on preflight failures; never bypass checks by inventing attestation
flags. A `started.json` is written before the first physical register
access; no `result.json` after an AXI abort/stall means **NO PASS**, not a
timeout. If a register operation fails, do not automatically retry or
touch the hardware again.

After either stage, the external supervisor must restore the **original**
FPGA image and verify its identity, clock, kernel state, services, and
UIO/PL ownership. The native CLI records
`recovery_restoration: NOT_RUN` regardless of its functional outcome.
A stage's functional PASS is **not** a hardware qualification PASS until
original-image restoration is independently observed.

Validation command for the PR and future host CI (NO device I/O):

```sh
python3 -m pytest -q software/python/tests/test_linux_mmio.py \
    software/python/tests/test_swd_transaction_driver.py \
    software/python/tests/test_mmio_z2_qualification.py
```

The test file uses a **sparse regular file** at the reviewed AXI offset
layout for read-only native mappings, and controlled Python test doubles
for CONTROL and SWD command semantics. It cannot prove Linux device memory
attributes, ARMv7 instruction width or hardware electrical behavior.
