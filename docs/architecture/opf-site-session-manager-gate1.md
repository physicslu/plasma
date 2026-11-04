# OPF-3A — Per-Site Session ownership within the existing Site Worker

**Status: Gate 1 / Host-only candidate.** OPF-3A is the smallest isolated
step toward OPF Site Session Manager; it does **not** install a second Session
Manager, rewrite the PPU execution lease, change Provider execution, or enable
hardware operations.

## Reused, not rewritten

- `software/python/plasma_server/site_manager.py` already owns the PPU-wide
  execution lease and supports multiple Site Jobs from the **same** logical owner.
  It continues to determine Job admission and Runtime quiescence.
- `scripts/ppu_site_worker.py` already validates the trusted Runtime MainPID,
  authenticated Package process group/UID, Job lease on open **and** operation,
  one monotonic deadline per Session, per-Site locks and persistent seals.
  OPF-3A retains all of these in the same Worker/AF_UNIX protocol.
- `scripts/ppu_site_adapter_abi5.py` retains the PS-local OpenOCD and ABI-v5
  safety behaviour, including actual SAFE_OFF proof. It is not modified.
- `scripts/ppu_site_recovery.py` remains the only authorised operator seal
  recovery procedure. No auto-unseal or auto-Flash retry.
- ADR-0007 PPU shared FPGA Reload Fence and per-Site OS-level locks remain
  the hardware authority. The Python per-Site lock is only an additional
  in-process guard and **does not replace** the existing OS protection.

## Verified source gap (before this PR)

The Runtime permits concurrent Site Jobs by the same PPU owner, but Stage C-3
`SiteWorkerCore` had one `self._session` for the entire PPU and rejected the
second Job with `SESSION_ALREADY_ACTIVE`, even if its Site was different.
Therefore two simultaneously active C-3 REST Sessions were impossible.

## OPF-3A minimal contract

1. One existing Worker holds a map of Session ID → Session and a map of
   Site → Session ID. Multi-Site Package Sessions reserve all requested Sites
   atomically; two Sessions that overlap **any** Site are refused. Multiple
   disjoint Sessions may coexist.
2. A Package peer is accepted only for its unique authorized process group,
   UID and Job lease; REST Jobs continue to use trusted Runtime control socket
   and exact Session IDs. No arbitrary Provider, Tcl, shell or MMIO commands
   are accepted.
3. Each Session retains **one** bounded monotonic deadline, cancellation token,
   set of Sites, immutable starting hardware identity, and own sealed outcome.
   Per-Site cancellation and close wait only for that Session's Sites.
4. A stale or restarted Runtime invalidates Sessions, but a Site reservation
   persists while that Site's adapter is running; no early release can create
   a new hardware execution owner.
5. Worker status can list disjoint Sessions. Existing single-session `session`
   status remains readable for a single active Session; multi-session state
   uses the `sessions` array. Replace-by-Default migration will evaluate
   the exact status consumer before eliminating the old single-key view.
6. A deadline, unexpected adapter exception or unknown SAFE_OFF result uses
   the *existing* seal and fail-closed path. A sealed Site is not reassigned
   or automatically recovered.
7. For concurrent Flash Jobs, the existing Worker now rejects a second
   bound image unless the firmware SHA256 **and the complete trusted Flash
   Profile** match the first Session. A PPU Execution Lease by itself only
   proves a logical owner, not that the selected MCU and firmware match.
8. This PR deliberately does **not** change root guards, OpenOCD/Driver,
   Active Bundle v3 selection, the requirement for one target/firmware per PPU,
   or claim 8-Site physical parallelism.

## Host-only acceptance

- Different disjoint Sites can both hold Sessions and execute concurrently.
- Duplicate Site admission is denied, and a Package Session reserving multiple
  Sites denies any partial overlap.
- Cancel/unknown Site 1 seals Site 1 without ending or sealing Site 2.
- Concurrent Flash bindings require identical Profile and firmware SHA256;
  different target or firmware is rejected before the adapter executes.
- Existing lease, identity, expiry, peer authentication, close, restart, seal,
  ABI-v5 adapter, install and production wiring tests continue to pass.
- CI is a Host-only simulation; no real SWPC Path 2, Z2, MMIO, FPGA, DUT,
  8-Site hardware load, or true independent 8-Channel timing is claimed.

## Verified hardware-adapter concurrency blocker (not changed here)

The existing `Abi5OpenocdAdapter._session` refuses entry when
`_openocd_running()` detects **any** OpenOCD process, including one that may
already be legitimately owned by another Site. Therefore **passing C-3
Session-level concurrency does not establish concurrent real OpenOCD sessions**.
Future integration must distinguish authorised per-Site native OpenOCD owners
from unrelated external processes through the existing audited admission
records, Root Guard and PPU Reload Fence. Do **not** merely remove the global
process check or bypass those hardware safety gates. The current FPGA image
supports two physical SWD Sites; eight real Sites are a separate qualification
target.

## Follow-up OPF-3B

Only after this initial Host-only change is reviewed: feed OPF-1's effective
`timeout_ms` into the existing C-3 Session deadline, bind OPF-2's trusted
Provider Route to the Site, migrate the static Flash Profile admission, and
validate cross-layer cancellation/restart and fail-closed HIL. OPF-3A does not
pretend this integration is already complete.
