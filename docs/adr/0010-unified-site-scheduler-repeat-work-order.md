# ADR-0010 — Unified 8-Site Scheduler: Manual Repeat / Automation Work Order

- **Status:** Accepted architecture decision; implementation pending
- **Decision date:** 2026-11-15
- **Owner scope:** Contract freeze only. No executable change, deployment, Gate 2 merge or physical HIL authorisation.
- **Normative design details:** [Unified 8-Site Scheduler, Manual Repeat and Work Order Quantity v1](../architecture/unified-8site-scheduler-repeat-work-order-v1.md)

## Context

PLASMA presently has one canonical Manager-owned Batch interface across EMode/PMode, but its `_run_units` walks Sites sequentially and the active policy accepts only `repeat=1`. A separate historical Gateway/Mock Batch supports `repeat_count`, but must not become a second production scheduling authority. Current Site execution and physical safety protections have different qualification levels.

A manufacturing **physical unit**, a programming **Cycle**, and a Retry **Attempt** are different things. Treating them as the same quantity fabricates yield and permits duplicate work after uncertain outcomes.

## Decision

1. Freeze **one** Manager-owned Scheduler/Repeat Engine, Site Lane, Job Lifecycle, Journal and Fault Isolation for both EMode and PMode; UI scope differs, execution logic does not.
2. **Manual:** `repeat_count` 1..10000 per selected Site, `replace_ic_before_next_cycle=true` by default. Yes requires explicit new placement confirmation each Cycle. No reuses the same IC for Debug, and its Cycle PASS count is not physical good-unit output.
3. **Automation:** MES Work Order `target_quantity` is the total number of qualified **PASS physical units across all Sites**, not per Site and not Manual Repeat. Work Order revision/product and fixture events are authoritative business inputs; Scheduler alone allocates and accounts jobs.
4. Require one unique Cycle identity and one unique Job ID/Receipt per initial execution; each Retry is a separately identified attempt/Job within its original Cycle. New Cycle is not a Retry.
5. Only distinct final physical unit dispositions yield `processed_units = pass_units + fail_units`; infrastructure errors, unknowns and Retry attempts are separate. Work Order completion requires target PASS with all reservations/in-flight/unknown and safety obligations settled.
6. Before dispatch, reserve one global good-unit quota slot so outstanding work can never create overproduction at the target boundary. Terminal FAIL may be compensated by a **new physical presentation** within an explicitly approved finite make-up budget; default no automatic make-up. Shortage does not become a false completion.
7. Each Site Lane runs Cycles sequentially; different Sites run concurrently under **proven** resource, lease, SWD, FPGA, electrical and PPU concurrency limits. A Site-local failure does not unconditionally stop healthy Sites, but shared-control or PPU-wide unknown ownership remains fail-closed.
8. `OUTCOME_UNKNOWN`, unverified SAFE_OFF and Sealed Site prevent automatic continuation; do not bypass the existing PPU-wide latch without separate ownership/isolation proof.
9. PLC/MES handshakes are deduplicated, ordered and correlated with exact Site/Work Order/presentation/cycle. Readiness signals do not replace actual hardware safety evidence. The Browser never owns this machine state.
10. Freeze the architecture now; implement only in later bounded PRs with Host-only and eventually real 2-Site then 8-Site acceptance.

## Consequences and migration gaps

- Current Manager `repeat=1`, sequential Target walk, current PPU installer default concurrency 1, and legacy Gateway Mock Repeat remain **unchanged**. The contract is a **Plan**, not proof of a deployed feature.
- Future implementation must replace/retire duplicated scheduling paths per the existing PR-F inventory; it must not add a mode-specific PMode worker or modify the proven single-Site hardware route by default.
- Version any changed schema/API, migrate all clients, update tests and operator instructions, and preserve existing Start/Run/Receipt identities and recovery.
- Future testing must separately prove concurrency, resource ownership, fixture I/O, physical electrical safety, and correct good-unit yield. Mock/CI evidence cannot be promoted to HIL PASS.
- This ADR grants no new approval Gate. Gate 2 remains merge approval; real hardware operation requires the applicable owner-authorised task scope and executable safety protections.

## Rejected alternatives

- Two Repeat Engines for EMode and PMode: duplicate correctness/safety logic and diverging accounting.
- `target_quantity × site_count`: manufactures too many units and defeats central Work Order authority.
- Counting Retry, repeated same-IC Debug PASS or infrastructure failures as good physical units: incorrect yield.
- Unlimited automatic make-up until target PASS: can produce unbounded scrap and mask faults.
- One cross-Site barrier per manual round or a forced `max_concurrent_jobs=8`: serialises independent lanes or claims unqualified capacity.
- Blind resubmission on lost Job/PLC response: can duplicate programming under uncertain hardware state.
