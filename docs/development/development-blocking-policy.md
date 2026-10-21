# Development Mode — Three Shared BLOCKING Decisions

Paths 2 and 3 share the same trusted Dispatcher, Runner and Path 2 Bridge.

1. **B1 — Authorization and source**: only a bounded owner-approved Work Order and immutable reviewed executable/source may run.
2. **B2 — Current Z2 hardware safety and recovery**: lock, effective root, ownership of MMIO and drivers, same boot, pinned candidate/recovery image and durable restoration state must be valid before physical operations.
3. **B3 — Real result and fail-closed progression**: authentic root-sourced receipt, correct stage/return code, read-only native aligned MMIO, no unsafe retry, and stop on SIGBUS, timeout, unreaped child or uncertain restore.

These are three *policy decisions*, **not three total predicates**. Device integrity checks inside B1–B3 remain mandatory and cannot safely be removed.

## Actual runtime simplification

Codex's work-order evidence (GitHub Run 39573288065) counted 233 explicit rejection sites across seven live sources, versus 212 after its original patch, a reduction of 21. Removed: repeated workflow event/runner tests (14); Z2 service-availability and descriptive risk-label assertions (2); duplicate environment acknowledgement (1); duplicate orchestration auto-stage assertions (2); repeated full-HIL aggregate result assertion (1); host-only evidence completeness execution stop (1). Also removed SSH prompt-presence as an atomic predicate, retaining verified remote exit and strict root receipt.

**Safety adjustment before merge:** Guarded-hardware Path 3 keeps the evidence-completeness execution stop so an empty/incomplete Codex report does not satisfy the prerequisite to the trusted hardware job. Therefore the shipped reduction is **20**, not the original 21, counted by the same inventory method. Host-only evidence incompleteness is review metadata.

All current Z2 firmware/image, root-owned source, Manager status, UIO/MMIO ownership, stage allowlists, protected restore, durable UNKNOWN state and native read32/SIGBUS/reaping checks remain enforceable. No actual hardware qualification is implied by hosted tests.

Run: https://github.com/physicslu/plasma/actions/runs/39573288065
