# PLASMA Root Guard: Program Session vs FPGA Configuration Admission

Status: **Gate 1 Draft — Host-only implementation candidate, 2026-10-29**.
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
