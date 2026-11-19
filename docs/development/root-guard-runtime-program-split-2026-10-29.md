# PLASMA Root Guard: Program Session vs FPGA Configuration Admission

Status: **Host-only implementation, merged in main (PR #1202), 2026-10-29**.
Source: [PR #1202](https://github.com/physicslu/plasma/pull/1202).
No SWPC/Z2 deployment, no FPGA/MMIO/DUT operation, no hardware HIL
acceptance, and no merge authorization from this documentation.

## Observed trigger

The operator's 2026-10-28 Blue Pill A/B burn-in completed 12 alternating
v0.1/v0.2 full Flash/Readback/Reset/CDC attempts. The 13th attempt failed
before the Bridge UNIX socket existed, with Z2 Root Guard
`INCOMPLETE_ROOT_OR_PROCESS_FACTS`; OpenOCD was not launched and
Erase/Program was not entered. A later read-only snapshot returned
`proc_complete=true`, `proc_conflicts=[]`, FPGA Manager `operating`.
A short-lived PID race is plausible but **not proven**: the original
failure did not record which aggregate predicate was false.

## Owner-approved separation

- **Normal programming session (current one-Site Z2 prototype):**
  the source-pinned Bridge, while holding the existing exclusive FPGA
  configuration lock and after the current image checkpoint check,
  uses `live_program_session_report()`. It keeps the exact held image,
  Golden digest, boot identity, FPGA Manager load provenance, UIO map,
  platform binding, and IRQ topology guards. It does **not** enumerate
  all Linux PIDs via `scan_proc_consumers()`; its internal live-facts
  snapshot explicitly records `proc_complete=null`, `proc_conflicts=null` and
  `proc_scan_diagnostic.status=NOT_RUN_PROGRAM_SESSION`, never a
  fabricated empty conflict set.
- **Device-scoped MMIO owner admission:** the existing Z2 engine still
  invokes `fuser -s` for `/dev/mem` and `/dev/uio1`, rejecting busy
  and unknown results. The Bridge repeats the same device-scoped check
  **inside** its global FPGA lock, before opening `LinuxMMIO`.
  `fuser` is only an observation, not an atomic hardware ownership
  primitive. Real OS device permissions, the exclusive configuration
  lock, exact script/source SHA and Site lease remain mandatory.
- **FPGA Manager download / image test / restore:** the existing
  `live_report()` continues to require a **complete whole-system**
  process visibility check, zero conflicting owners and the existing
  kernel/FPGA invariants. Neither a caller-supplied flag nor the
  runtime-only report is used by these maintenance paths. Unknown
  or conflicting process evidence still fails closed.

This is a **short-term development-mode admission split**, not proof
that arbitrary Root processes cannot access `/dev/mem`, that `fuser`
is race-free, or that the current one-Site bridge is a safe eight-Site
parallel Broker. A process-global `flock` only serializes participants
which honor that lock.

## Intended eight-Site end state

One authorized Hardware Broker holds the single UIO mapping and
arbitrates short MMIO register accesses. Eight independently admitted
Site leases/engines operate concurrently. FPGA reconfiguration is a
separate maintenance operation requiring all Sites quiesced and no
unreconciled in-flight work. Do **not** reuse the one-Site global
configuration lock to serialize entire multi-Site Flash jobs.
See `docs/architecture/fixed-fpga-hardware-broker-eight-site-gate1.md`
and `docs/architecture/fixed-fpga-hardware-abi-v1-gate1.md`.
Those remain Host-only proposals, not deployed eight-Site hardware.

## Acceptance and deployment limits

Host-only tests must prove both branches: runtime never enumerates the
global PID census, while FPGA Manager load/test/restore still rejects
incomplete visibility or real conflicts. Verify image, Manager,
UIO, boot and source invariants have not been bypassed. A source change
to `pl/hil/fpga_image_guard.py`, `fpga_image_admission.py` and
`fpga_image_root.py` changes **protected Root executable bytes**:
the installed device Root source SHA and integrity manifest must remain
unchanged until an independently authorized protected deployment
re-pins and verifies the reviewed code. The Bridge and generic programming
engine must also use mutually compatible reviewed SHA-pinned source.

**NOT_RUN**: Z2 HIL, protected Root install, DUT re-flash, 200-attempt
burn-in continuation, and Gate 2 merge.

## 2026-11-19 — ABI-v5 Site admission: confirmed-exited PIDs (WO-1)

**Trigger.** Concurrent 2-Site Manual Repeat on Z2 (evidence
`plasma-evidence/repeat100-2site-repro-20261119`): after 93 and 79 PASS
Cycles, Site 1 and Site 2 were each refused **before OpenOCD** with
`PROC_SCAN_INCOMPLETE:VANISHED_PID_RESCAN_EXHAUSTED:<pid>:FD:FileNotFoundError`.
The ABI-v5 Site admission (`live_site_admission_report`, #1326 / ADR-0007)
still runs the whole census per Job, with the peer-Site exemption, because it
holds only supervisor/fence **SH** and must tell the peer's `/dev/mem` owner
from an uncooperative one. The strict "restart the whole census on a vanished
PID, at most three times" rule cannot finish while the peer Site's
short-lived processes keep exiting.

**Change.** `scan_proc_consumers(vanished_pids=...)`:

- `"rescan"` (default) — unchanged strict behaviour. `RootZ2TargetPort` with
  `site=None` (FPGA Manager download/test/restore, `live_report`) always uses it.
- `"skip"` — used only by Site admission (`current_facts()` with a Site). A PID
  whose exit is **confirmed** (`/proc/<pid>` itself is gone) holds no fd and no
  mapping any more: it is counted (`vanished_skipped`) and skipped, no rescan.
- Both policies: a PID whose kernel start time (`/proc/<pid>/stat` field 22)
  changes while its fds/VMAs are read was reused by another process; it is
  re-read once and refused (`PID_REUSED_DURING_SCAN`) if it changes again.

Unchanged and still fail-closed: `/proc` enumeration failure, a live but
unreadable PID, malformed fd/VMA data, every `/dev/uio*`, `/dev/xdevcfg`,
`/dev/fpga0` holder, every `/dev/mem` holder that is not the proven peer
Site owner mapping only its own page, the Site lock / PPU reload fence,
the Root journal and boot identity, the admission record, SAFE_OFF and
OUTCOME_UNKNOWN sealing. This is not a retry increase and not a census
removal.

**Limit (unchanged by this change).** The census is a point-in-time detection
of pre-existing uncooperative owners, not prevention: a process created after
the `/proc` listing — including a child that inherited `/dev/mem` from a parent
that then exits — is not seen by either policy; a child listed with its parent
still is. Prevention needs the long-term Hardware Broker / device DAC design.

Host-only proof: `scripts/tests/test_fpga_image_root.py`
(`SiteAdmissionVanishedPidPolicyTests`, `SiteAdmissionPolicyWiringTests`).
This changes **protected Root executable bytes**: a separately authorized
protected Root deployment and 2-Site HIL are required before any hardware
claim. **NOT_RUN** here: protected Root install, Z2 HIL.
