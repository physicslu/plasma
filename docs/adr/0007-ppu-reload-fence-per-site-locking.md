# ADR-0007 — PPU Image/Reload Fence and independent per-Site SWD ownership

> Status: **Accepted architecture / Draft implementation** — Owner revised PR #1189 Gate 1 on 2026-10-28.
> Execution: GitHub-hosted Host-only only; **NOT deployed**, no SWPC, Z2, MMIO device or DUT operations.
> Depends on ADR-0006 NORMAL-only SWD and existing protected Root Image/Manifest Guard.

## Why one global exclusive lock is insufficient

PLASMA must program independent Sites concurrently. The previous
`/run/lock/plasma-mmio.lock` held `LOCK_EX` by every
`LinuxMMIO` and C OpenOCD process: safe for a single owner but forces
all eight product Sites into serial execution. Conversely, removing
that lock could allow FPGA Manager Image A→B replacement while SWD
commands still execute in the previous PL Image. Neither is acceptable.

Crucially, the **existing privileged FPGA Root Guard** uses another
exclusive `/run/plasma-z2-swd05/supervisor.lock`. It is retained;
it never by itself excluded a separate process merely holding
`plasma-mmio.lock`. Both domains must participate in the PPU fence.

## Lock protocol (acquire in this exact order)

1. **Programming Site N:** acquire PPU Reload Fence SH on existing
   `/run/lock/plasma-mmio.lock`, then acquire exclusive
   `/run/lock/plasma-mmio.lock.site-N`. Only the exact assigned Site N
   may then use its own ABI-v5 AXI aperture, its own FIFO/IRQ and
   its own target authorization. Site N=1/2 in current Z2 candidate;
   the eight-Site product requires separate future hardware admission.
2. **PPU Image Download/Restore/Root operation:** first acquire the
   *existing* protected `supervisor.lock` EX, then acquire the same
   PPU Reload Fence EX before reading/manipulating the Image/Manifest
   or FPGA Manager. This is additive to, **not replacing**, Root Guard,
   loaded-image attestation, Boot identity, physical voltage, exclusive
   FPGA ownership and the protected Golden recovery behavior.
3. **Legacy single-owner MMIO:** unchanged `LinuxMMIO` default
   acquires PPU Fence EX. It excludes all shared Site sessions and
   remains backward-compatible. A Site-concurrent opt-in is restricted
   to one exact SWD ABI-v5 Site aperture per LinuxMMIO instance.
4. **Release:** close Site MMIO and its lease first; release the Site
   EX lock before the PPU SH fence. Root releases PPU EX fence before
   the old supervisor EX. All locks are nonblocking; conflict is an
   explicit NO_GO, no silent waiting or fallback.
5. **Uncertainty:** I/O error or Barrier uncertainty invalidates the
   applicable shared Owner domain. Site lock release is never
   permission to retry a possibly executed DUT write. Failed FPGA
   load/UNKNOWN state remains a Root/FPGA Manager recovery decision.

## Threat model and limits

`flock` is cooperative Linux advisory locking, **not** a credential
system, secure provenance check, or protection against kernel access,
uncooperative privileged processes, SIGBUS, or untrusted AXI bus timing.
Process identity, registered exact ABI v5, Site physical voltage,
Image/Manifest/Boot SHA/Root source-pin, current reload state and
DUT readiness must still be verified by a trusted owner **on each
real transaction**. The portable C owner callback does not yet perform
real device-backed MMIO; the Python Host-only sparse-file mapping is
not ARMv7 electrical evidence.

Site and PPU lock files require deliberate owner-controlled inode,
ownership, DAC/ACL and group provisioning. A Root-created 0600 PPU
fence may block the non-root OpenOCD service; **do not weaken filesystem
permissions or start devices until deployment permissions are
qualified**. Pathnames must resolve to the same inode for every
participant. The protected Root and its source pins must be qualified
as one exact-SHA deployment; a Draft PR modification is not a
currently installed Z2 Root Guard.

## Host-only acceptance

- Real distinct Linux processes can simultaneously hold Site 1 and
  Site 2; a second owner of the same Site is denied.
- An EX PPU Reload attempt is denied while either Site is active.
  When EX is held no Site can start; after release, new Site sessions
  can acquire. Python/C code shares the exact lock protocol and
  alternate lock paths fail closed.
- C Site lease binds to its matching site lock and generation, and
  a stale/released owner cannot re-admit the same Site.
- An unmodified legacy PPU EX session excludes all Site SH sessions.
- The protected Root obtains its own historic supervisor EX **and**
  the PPU Reload EX, without changing Root's Image, Manifest, download,
  state or recovery decision logic.
- Source-locked OpenOCD native C build and existing Python/RTL
  regression still pass on the exact Draft PR HEAD.

**Not yet qualified:** actual ARMv7/RAM/device-width barrier, FPGA
HWH/BIT/Timing, two simultaneous real DUTs, Root lock file DAC on Z2,
full PS Owner/Provider connection, or eight-Site physical throughput.
Do not infer Gate 2 readiness or merge/deploy authority from tests.
