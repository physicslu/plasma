# PLASMA SWD Site Crash Recovery — Gate 1R Host-only candidate

Status: **Draft / Host-only / no production enforcement / no Z2 Root authority**.
Owner Gate 1 approved 2026-10-28. Depends conceptually on the unmerged
independent Native C SWD work in PR #1189; this separate PR branches from
main, does not change #1189, and must not be merged/deployed without Gate 2.
Applicable contracts: root AGENTS.md, ADR-0002, draft ADR-0007.

## Safety question

A Linux Site owner can be killed after a FIFO PUSH has caused a DUT side
effect and before it receives a completion. Linux releases its ownership
lock; a new owner acquires the lock but cannot infer that a retry is safe.
FPGA reload may erase a pending/completion FIFO without undoing the prior
DUT side effect. Per-process lease epochs and blocked flags cannot provide
crash persistence.

**Invariant:** a fresh process MUST NOT treat a released ownership lock, an
empty FIFO, a new Boot, a replaced FPGA Image, or a successful readback as
standalone permission to replay a possibly accepted DUT write.

## Candidate primitive (implemented, Host-only)

software/python/plasma_interfaces/swd_site_recovery.py is a deliberately
unwired PS-local Python **reference primitive**, with no device or Root access.

- Pre-provisioned private directory (same UID, no group/other access) and
  per-Site 0600 site-N.lock and site-N.json inodes. File/symlink/hardlink,
  owner and DAC errors fail closed. Advisory Site journal lock is distinct
  from the PPU Reload Fence and does **not** prove hardware ownership.
- Before an injected potentially harmful write callback, read an existing
  externally qualified READY record matching exact Boot ID, Image SHA-256,
  Manifest SHA-256 and one-based Site ID; READY is **not** initialized
  automatically. Missing, malformed, stale, pending-temp or UNCERTAIN
  records block.
- Before a callback, persist a **distinct, monotonic site-N.intent fence**
  with write -> fsync(intent inode) -> fsync(parent directory), then persist
  the UNCERTAIN journal via write -> fsync(temp inode) -> rename ->
  fsync(parent directory). The intent is never renamed, deleted, or
  automatically cleared by this module. It closes the crash-consistency
  hole where an un-fsynced journal rename could roll back to the prior
  READY file after sudden power loss. The intent's mere presence blocks
  all new write admission, regardless of its JSON content.
- Any fsync/rename/ownership failure invokes **no callback**. A leftover
  intent or temporary file keeps the Site blocked. The filesystem must
  provide truthful Linux fsync and durable storage semantics; a lying drive
  cache, torn sectors or lower-level media faults remain unqualified.
- Never auto-clear UNCERTAIN or intent on callback success, timeout, SIGKILL,
  process restart, FIFO drain, or Image reload. The **only** current recovery
  behavior is fail closed, pending explicit verified external authority. The
  code has no public mark_ready or clear_uncertain operation.
- Site 1 and Site 2 have independent files/locks; the 1..8 parser represents
  future logical Site IDs, **not** admission of 8 physical SWD engines.

The JSON checksum detects accidental corruption, **not** hostile modification.
Neither the directory owner nor the injected Boot/Image values are attested
by this prototype. A cooperating process can manufacture a READY file. Thus
the primitive is a **testable safety design**, not a deployed security control.
Host-only tests synthesize READY as an explicit fixture, not as production
permission.

## Transaction granularity and throughput invariant

The Python primitive currently admits **at most one injected callback per
trusted READY record**; it intentionally lacks an automatic READY issuer.
This is a crash-safety reference, **not a viable multi-command Flash
programming session**. A literal durable fsync + manual reset for every
SWD register Write would severely impair normal programming throughput.

A production Native C path needs a *trusted Site execution session*:

1. Under PPU SH + Site EX and a trusted Boot/Image/Manifest/lease
   attestation, the authority establishes and durably fsyncs a Site
   UNCERTAIN intent **before the first potentially side-effecting PUSH**.
2. The **same live Owner** may issue multiple FIFO PUSH/POP commands while
   retaining its exact Site lease, non-reused session generation and the
   authority-issued session capability. A newly started process cannot
   inherit that capability merely by reacquiring flock or seeing an empty
   FIFO. Per-command Owner and session checks remain mandatory.
3. At clean end, the trusted authority may durably publish READY *only
   after* matched Completion accounting, FIFO quiescence and an
   operation-specific target state verification that actually establishes
   safe continuation. A generic ACK, successful OpenOCD exit or Readback
   alone is not sufficient for all OTP/security/erase operations.
4. The authority must durably fsync the new qualified READY **before**
   removing the independent intent; fsync the parent directory again after
   removing it. On a crash at any point, READY plus a surviving intent
   remains blocked. Only trusted code may remove intent.
5. SIGKILL, process crash, lost Owner, missing/corrupt journal, unobserved
   Completion, FPGA Reload, changing Boot/Manifest or unexpected FIFO state
   makes subsequent admission fail closed, with no automatic new-Owner
   replay. State may stay UNCERTAIN until human intervention.

This entire production session/close protocol is **DESIGN ONLY / NOT
IMPLEMENTED** in this PR. It requires the Native C PR #1189 control-point
integration and a trusted PS-local issuer. The current Python prototype
should not be called or deployed as an OpenOCD callback wrapper.

## Root recovery boundary: proposed, not authorized for privileged change

- Use a **PS-local durable state directory** under an appropriate persistent
  filesystem, never /run or the FPGA volatile state. The exact deployment
  pathname, mount durability, SELinux/AppArmor if applicable, UID/GID and
  ACL policy remain unapproved. The 0700/0600 same-UID candidate is only
  a Host-only fixture; no new sudoers, service, or privileged file writer
  may be introduced from this PR.
- Proposed lock order: Root supervisor EX -> PPU Reload Fence EX ->
  per-Site journal lock. Normal Owner order remains PPU SH -> Site EX ->
  per-Site journal lock. Root must not hold these in reverse order or
  reset a Site while a Site Owner is executing.
- The Root authority must anchor observations to trusted **current**
  boot identity, Image/Manifest hash, Site lease generation, session/Job
  identity and exact registered command history; a source hash in a JSON
  record cannot attest hardware provenance by itself.
- FPGA Reload/Restore retains the independent Site journal and intent
  after changing Image/PL FIFOs. Reload must not silently remove DUT
  uncertainty. For each Site, entry to a new safe programming session
  requires independent qualification and explicit recovery evidence.
- Owner-controlled recovery has two distinct decisions: **inspect** (no
  write/replay/clear) and **authorize new session** (requires positive
  evidence of quiescence and safe target state; otherwise DENY and flag
  operator review). A lost or corrupt journal is not proof of a clean Site.

## Source integration and remaining blockers (NOT IMPLEMENTED)

1. **Trusted PS-local authority:** decide Root-owned state directory identity,
   privilege/DAC, Boot/Manifest/source pin, owner lock and Root Reload Fence
   integration. A Root permission/security contract change requires design
   review; this PR does not modify Root or provisioning.
2. **Unbypassable Native C admission:** wire the trusted authority to **every**
   harmful C FIFO PUSH/OpenOCD execution path and to all independent Sites.
   A Python wrapper alone cannot prevent direct native MMIO writers. It must
   also handle multiple queued commands, ACK_WAIT, side-effecting SWJ,
   synchronous barrier errors, and a command accepted before a kill.
3. **Recovery transition:** only after positive, trustworthy evidence of
   Site quiescence and applicable target state may the authority issue a new
   qualified READY identity/generation. Unknown Write results, OTP, erase,
   security configuration, journal corruption and ambiguous physical
   observations must remain blocked or require explicit operator handling.
   Readback alone may not prove a non-idempotent operation safe to repeat.
4. **PPU/Root reload:** supervisor EX plus PPU Reload EX must coordinate
   current Boot/Image/Manifest and all affected Sites before/after FPGA
   Manager operations. Reload must NOT erase durable uncertainty.
5. **Hardware:** PS ARMv7 MMIO/barrier, Root source lock/DAC, FPGA FIFO and
   actual DUT effects remain **NOT_RUN**.

This is deliberately a **non-authoritative precursor** to the complete
Crash Recovery Gate 1R. It must not be described as crash-safe programming
on Z2 or as a Gate 2-ready SWD write path.

## Host-only tests

software/python/tests/test_swd_site_recovery_host.py covers:

- Missing/corrupt/untrusted/unsafe journal and ambiguous stale identity denial.
- UNCERTAIN durable publication before fake write callback.
- SIGKILL and a *different* Python process attempting the same write.
- Fault injection before durable intent publication, after journal rename but
  before final directory fsync, independent intent surviving simulated READY
  rollback, and leftover intent/temp denial.
- Synthetic unknown completion, no auto retry, FIFO pending proxy and
  Boot/Image change denial.
- Site 1/2 separate journal state, cross-process journal lock contention.

Tests intentionally use only temporary regular files and fake callbacks.
They do **not** exercise the C FIFO, actual FPGA Reload, Root privileges or
real DUT. Those checks must be added at the integration gate.
