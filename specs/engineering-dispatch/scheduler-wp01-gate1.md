# Path 3 Gate 1 — WP-01 Manager Concurrent Site Lanes (Host-only)

Source design: [PR #1439](https://github.com/physicslu/plasma/pull/1439) exact contract HEAD `193ed8f257916c011d488d74805c31d9cb2600ec`.
Engineering WBS: [Issue #1440](https://github.com/physicslu/plasma/issues/1440).
Base is deliberately stacked on the frozen documentation PR HEAD, while the PR itself targets main and remains Draft. Once #1439 is merged, remove any overlapping documentation delta from the WP-01 PR through normal source synchronization; never combine merge authorizations.

## Bounded implementation

Refactor existing `software/python/plasma_manager/programming_batch.py` **only as necessary to support bounded concurrent execution across distinct Site lanes**, while preserving the current canonical Manager Batch/Start/Run API, `repeat=1` policy, resource/route admission, Retry and Stop semantics, and single-Site real Flash path.

Host-only acceptance must prove actual overlap on independent Site lanes, no overlap on one Site, no unverified extra Job after OUTCOME_UNKNOWN, existing PPU-wide unknown latch, PPU vs Manager shared-failure isolation, clear Stop/failure thresholds, and restart-safe journal-before-submit. Use deterministic event/clock tests that cannot falsely PASS serial execution. 2 and 8 Site Mock cases required. Do not widen device concurrency config based only on eight defined Site IDs.

## Path 3 authority

Existing SWPC `SWPC-plasma-codex` Worker, owner-authenticated Issue #981 Work Order, `codex-workspace`, `--sandbox workspace-write`. Code/edit/host-only tests and CI under this WP are authorised by the 2026-11-15 owner direction. **No SWPC service mutation, Z2/FPGA/DUT operations, deployment, live programming, global privilege/ACL adjustments, PR merge or auto-merge.** No new deployment architecture/Runner.

Path 3 should deliver a bounded independent engineering PR and true test evidence at exact HEAD. Separate future PRs implement Manual Repeat, Automation Work Order and UI; do not expand this WP into them.
