# OPF S2/S3 + S5 — retire Gen7-only Site 2 deployment helpers (Gate 1)

**Accepted baseline:** `main@690c21149cbbe540907c672ec58655cfaba36eab` (merged PR #1354).
**Authority:** `AGENTS.md`, Common, Embedded/PPU, Manager contract, [core convergence roadmap](../architecture/plasma-core-convergence-and-deletion-first-roadmap.md), and [merged #1353](https://github.com/physicslu/plasma/pull/1353).
**Scope:** One source-only deletion/migration; no merge authorization, no deployment/Runtime restart, no SWPC/Z2/FPGA/DUT operation.

## S0 Work Order reachability observation

[Issue #981](https://github.com/physicslu/plasma/issues/981) contained 498 comments at initial Gate 1 audit. The last explicit old Gen7 `opf_site2_path2_bundle_deploy.py` operator-cli dispatch was at comment index 415, and the last `opf_site2_joint_acceptance.py` dispatch at index 417 (zero-based audit indexing). Later comments (through 497) move to real Site 2 preflight and generic `scripts/plasma_program.py` Jobs, including new-path A/B accepted receipts. No subsequently posted Issue #981 Work Order references the retired Gen7-only script names.

This verifies the **visible Issue #981 dispatch history**, not the contents of private queued SWPC processes or unsynchronized offline operator worktrees. No queued legacy dispatch was positively identified in the inspected GitHub Issue. Existing historical audit/evidence comments are preserved; no Work Order or device was cancelled, retried, or inspected remotely.

## S2/S3 ownership/reachability ledger

| Concern | Before | Proposed after | Decision |
| --- | --- | --- | --- |
| Site 2 Active read-only | `plasma_site2_active_readonly_path2.py` imports `opf_site2_joint_acceptance.observe_active` | Local `observe_active` and fixed installed `ppu_asset_set.read_active` observer in retained read-only CLI | MIGRATE unchanged guarded contract |
| Gen7 only Bootstrap B3 | `opf_site2_path2_bundle_deploy.py` hard-pins original Gen7 source SHA and reconstructs a bundle | Removed; `plasma_program.py` remains canonical owner-authorized B1/B2/B3/Job path | DELETE |
| Old Joint Doctor + B3 | `opf_site2_joint_acceptance.py` can perform a separate mutation path | Removed; `plasma_ppu.py` remains read-only and never deploys | DELETE |
| Doctor tracked source audit | `_REPO_FILES` requires two Gen7 CLIs | Remove only those two entries; keep current source contract | MIGRATE |
| Profile-only offline builder | `opf_platform_bundle_v3_build.py` | Unchanged | KEEP |
| PPU production programming | `plasma_program.py` and existing Gateway/Bootstrap/C-3 | Unchanged | KEEP |
| Historical host tests | Two Gen7 CLI suites, including obsolete writer tests | Remove writer-focused tests; add local read-only Active observer and Doctor source inventory guards | REPLACE |
| Active PPU resource/safety owners | `PPUExecutionLease`, `RuntimeQuiesceGate`, C-3 Session/Worker, Root/native FPGA Owner/Reload | Unchanged | KEEP |
| Unknown outcomes | Transaction receipts, readback SHA, SAFE_OFF, durable SEALED / operator Recovery | Unchanged | KEEP |

The existing read-only preflight retains pinned local source SHA, paired host credential resolution through the existing approved Helper, Engine/ABI digest checks, idle/Lease gates, and static Active Provider file-set observation. Its SSH observation executes `python3 -I -c` with a fixed script reading the installed, protected `ppu_asset_set.read_active`. No new credential entrypoint or privileged mutation is added.

**Old routes in this narrow Site 2 operator scope:** 2 Gen7-only write-capable helper entrypoints → 0; the canonical generic PPU writing CLI remains 1 before and after. This is not a claim about Engineering Route B or every diagnostic harness. Runtime Router/Executor/Provider contracts are unchanged.

## Negative acceptance required

1. Existing read-only Active receipt validates exact `ACTIVE`/SHA or `EMPTY` states, and rejects malformed, duplicated, or failed remote receipts.
2. Paired target mismatch denies SSH; wrong `--source-sha`, Engine digest/ABI mismatch, active lease/job, non-PASS static OPF or invalid SHA fails closed before readiness.
3. Doctor source inventory no longer produces false missing-script warnings when Gen7 helpers are absent; Doctor `deploy` remains denied.
4. Offline Bundle builder, `plasma_program.py`, Bundle v3 Admission, C-3 Site Worker and Runtime/Lease/SEALED/SAFE_OFF/Recovery host regressions stay collected by Python PS CI.
5. No removed script or test is imported by live retained code; no compatibility alias or shadow B1/B2/B3 writer.

Host-only PASS and exact-head CI are required before Gate 2 readiness. **Current status in this design record is Gate 1 implementation candidate; physical Z2/FPGA/DUT HIL NOT_RUN.** Read-only historical Site 2 A/B physical receipts remain valid only for their exact accepted earlier Runtime/Bundle/Site.

## Deferred, explicitly out of scope

No S2 lease/fence simplification without authority-equivalence proof; no C-2/non-OpenOCD physical Provider qualification, PC ST-LINK, 8-Site HIL, Engineering Route B consolidation, privileged Root/FPGA change, Runtime deployment or new PPU device operation. No new framework/registry/engine introduced. Gate 2 remains an independent owner decision after exact-head CI, Rulesets, Reviews, Threads and Mergeability review.
