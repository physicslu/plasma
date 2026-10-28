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
- Persist an UNCERTAIN record containing the operation ID and incremented
  generation using an exclusive temporary file; write -> fsync(file) ->
  rename -> fsync(parent directory) must complete before the callback.
  Incomplete replacement or journal persistence failure invokes no callback.
- Never auto-clear UNCERTAIN on callback success, timeout, SIGKILL, process
  restart, FIFO drain, or Image reload. The **only** current recovery behavior
  is fail closed, pending explicit verified external authority. The code has
  no public mark_ready or clear_uncertain operation.
- Site 1 and Site 2 have independent files/locks; the 1..8 parser represents
  future logical Site IDs, **not** admission of 8 physical SWD engines.

The JSON checksum detects accidental corruption, **not** hostile modification.
Neither the directory owner nor the injected Boot/Image values are attested
by this prototype. A cooperating process can manufacture a READY file. Thus
the primitive is a **testable safety design**, not a deployed security control.
Host-only tests synthesize READY as an explicit fixture, not as production
permission.

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
- Synthetic loss before atomic rename and leftover temp journal denial.
- Synthetic unknown completion, no auto retry, FIFO pending proxy and
  Boot/Image change denial.
- Site 1/2 separate journal state, cross-process journal lock contention.

Tests intentionally use only temporary regular files and fake callbacks.
They do **not** exercise the C FIFO, actual FPGA Reload, Root privileges or
real DUT. Those checks must be added at the integration gate.
