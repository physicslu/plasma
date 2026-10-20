# PLASMA Path 2 Persistent FPGA Lease / Restore — Gate 1

**Classification:** HOST-ONLY contract, **not** authority to load FPGA or restore firmware. Based exclusively on main \`7ffb531949610d2ae198d3e8766ac3a9574eddcd\` (PR #1077 merged). Changes do not modify the existing Orchestrator, F1-B Profile/Driver, trusted Dispatcher or any hardware workflow.

## Scope and first principles

Path 2 has three independent stages: **Build**, **Download**, and **Testing**. \`auto_download_after_build_success\` and \`auto_test_after_download_success\` remain two separately selected per-run booleans, both **default false**. A Download that returns to \`base.bin\` is **not** a persistent Download, and an isolated Testing stage cannot trust a stale prior Load Receipt as proof of still-loaded firmware.

\`scripts/plasma_path2_persistent_lease.py\` introduces a **single-target, host-only persistent ledger**. It does not import or call Vivado, SSH, sudo, FPGA Manager or MMIO and has no CLI or default backend. It reuses the already merged F1-B Adapter evidence fields (\`source_sha\`, \`profile_id\`, \`target_id\`, \`artifact_sha256\`, \`lease_id\`, \`load_evidence_sha256\`). Before Testing, the caller must supply separately authenticated *fresh target facts*, including same boot ID, loaded image hash, manager \`operating\`, exclusive owner evidence and a separately reviewed AXI admission. **A JSON receipt is a claim, not cryptographic hardware attestation.** Mock tests do not establish real AXI isolation.

## Durable state machine

| Status | Allowed operation | Next state |
|---|---|---|
| No ledger for target | Persist immutable firmware & recovery SHA, boot, original services/UIO snapshots, Lease ID, owner, RESTORE_REQUIRED intent and bounded expiry | \`RESTORE_REQUIRED\` |
| \`RESTORE_REQUIRED\` | Record exactly one attempt **before** any hardware write, after original-image and ownership proof | \`LOAD_IN_FLIGHT\` |
| \`LOAD_IN_FLIGHT\` | Fresh manager and candidate-image evidence, matching durable recovery intent, same boot, within deadline | \`LOADED_AND_HELD\` |
| \`LOADED_AND_HELD\` | Same lease/image/boot, current ownership proof, fresh observation, deadline valid | \`TEST_IN_FLIGHT\` |
| \`TEST_IN_FLIGHT\` | Exactly 3 native u32 Identity readbacks / 0 writes, all equal F1-B Profile; same load evidence | \`LOADED_AND_HELD\`, ready for explicitly triggered Testing again |
| \`LOADED_AND_HELD\` | Reviewed recovery authority, confirm current candidate and recovery bytes, record one restore attempt | \`RESTORE_IN_FLIGHT\` |
| \`RESTORE_IN_FLIGHT\` | Confirm original recovery image, same boot/manager plus original services/UIO hash, signed/approved evidence outside this module | \`RESTORED_VERIFIED\` |
| Loading/testing/restoring interrupted or uncertain | Record explicit incident, **never automatically retry or restore** | \`UNKNOWN_MANUAL_RECOVERY\` |
| HELD lease expired | Explicit expiration mark, no more Testing/Load/Restore actions | \`EXPIRED_REVIEW_REQUIRED\` |

No unconditional finally-restore or daemon-based timeout recovery is implemented. A stale \`*_IN_FLIGHT\` record after a process crash cannot be reused to start a second load or Test. Observed SIGBUS / AXI hang / unreaped child must be reconciled by a separately authorized recovery procedure, not guessed from a host receipt.

The ledger uses a private owner-writable directory, a **single canonical ledger path per target**, non-symlink files, \`flock\`, revision CAS checks, temp-file write + \`fsync\` + atomic replacement + directory \`fsync\`, and refuses duplicate initialization. **A separate global FPGA/hardware lease and trusted isolated host filesystem are still required**; this module cannot prevent writes from a second process that bypasses its ledger.

## Timeouts, trust boundary, and integration

Host-only tests inject a trusted integer clock \`now\`; max lease TTL 900 seconds and each in-flight step max 120 seconds. A caller must independently establish clock credibility and fresh device observations; time rollback, expired session, stale boot, mismatched candidate/recovery SHA or owner, and missing receipt evidence fail closed.

Actual Download/Restore providers are **not implemented or registered** in Gate 1. A future independently approved target runtime should (a) lock the real hardware, (b) verify the genuine device state and previous image, (c) record the durable restore intent and write-attempt counter **before** any real FPGA Manager operation, (d) verify loaded state and activate the lease only after independent evidence, (e) revalidate before every isolated Testing, and (f) explicitly authorize guarded recovery with manual handling if unknown. The existing \`one_shot.run_live\` restores the original image automatically, and must **never** be misrepresented as a held Download stage.

The merged \`scripts/plasma_path2_f1b_adapters.py\` can use \`require_testing(...)\` as the pre-Test guard, as shown by the offline integration test; it remains an injected backend responsibility and no production transport is wired. See [historical Codex Path 3 operation ledger](../development/plasma-f1b-path3-39395142726-codex-steps.md).

## Host-only verification

\`pl/tests/test_path2_persistent_fpga_lease.py\` tests cross-process ledger restart, single-load/restore attempts, exact independent Testing re-entry, bad image/target/boot/lease/fresh-owner evidence, expiration, timeout, unknown recovery, immutable recovery intent, symlink/path protection, stale revision, concurrent-writer CAS, and F1-B Adapter compatibility with a mock Identity provider. No new Workflow, real FPGA action, SWPC Runner action or Vivado execution. This is **Development contract evidence**, not hardware qualification.
