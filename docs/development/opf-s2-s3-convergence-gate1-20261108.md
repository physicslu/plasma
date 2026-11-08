# OPF S2/S3 deletion-first bounded convergence audit — 2026-11-08

**Baseline:** `main@e81c52656430d35cb090e7eca2d6748adf7f5599`. The owner's execution order is (1) real Bundle A new-path HIL, (3) S2/S3 convergence; PC/ST-LINK second Provider (2) and eight-Site (4) are deferred.

## Scope 1: replace a reachable but obsolete duplicate physical CLI

| Responsibility | Retained authority | Duplicate / action |
| --- | --- | --- |
| Generic Bundle v3 verification, Profile/Firmware selection | `scripts/plasma_program.py::read_bundle` + `ppu_unified_deployment.verify_host_only_bundle` | Keep, no new schema/ZIP parser |
| B1/B2/B3 activation | `plasma_program.py::activate` -> existing Bootstrap API and single DeploymentCoordinator | Keep; Bundle v3 only; no second Installer |
| One Job Flash/Readback/SAFE_OFF | `plasma_program.py::{post_once,poll_job,verify_job}` -> existing Gateway/C-3 | **Delete** fixed v0.1 `scripts/plasma_site2_single_flash_path2.py`, which independently implements REST submit/poll/verify and hard-pins a tracked firmware |
| Legacy CLI-only dedicated tests | `software/python/tests/test_plasma_program.py`, `test_c3_rest_flash_cycle.py`, `test_ppu_stage_c3_site_worker.py` | **Delete** `software/python/tests/test_plasma_site2_single_flash_path2.py`; keep regression suite for the retained route |

Before -> after physical operator Flash entrypoints in this bounded source scope: **2 -> 1** (`plasma_site2_single_flash_path2.py` retired; `plasma_program.py` retained). This does **not** claim every historical diagnostic or test harness was deleted. Expected Python production source deletion: **286 lines**; dedicated legacy tests deletion: **184 lines**; zero runtime production lines added. GitHub diff/CI is authoritative for final counts.

## S2 safety authority: do not confuse different locks with duplicate logic

| Trust boundary | Existing authoritative owner | Reason to KEEP |
| --- | --- | --- |
| PPU-wide active Job and owner exclusion | `site_manager.py::PPUExecutionLease` | Exclusive operator/Job owner; also blocks Runtime/Asset activation during queued or running Jobs |
| Runtime/Asset quiescence | `RuntimeQuiesceGate` under the same SiteManager `_execution_lock` | TTL vs connection-held leases have different lifetimes; no concurrent Job admission during activation |
| Process/Session/stale Runtime fence | `ppu_site_worker.py::SiteWorkerCore` | Runtime PID, UID/PGID, Job lease and one bounded per-Site operation; durable in-progress seal on crash |
| Native shared FPGA/PL/PS Owner | `plasma_swd`/Root native ABI and FPGA Manager | Hardware-wide reload guard, cross-process Site ownership and unknown-outcome recovery |
| PPU Active Bundle identity | `ppu_asset_set.py` and `ppu_provider_contract.py` | Verified actual installed bytes and Device hardware binding; cannot be moved into the portable OPF contract |

No independent proof of redundant, safely removable authority exists for these mechanisms. They are **not deleted**. In particular, `RuntimeQuiesceGate` and `PPUExecutionLease` are coordinated under one lock, not accidental duplicate Executors; `SiteWorkerClient` and `SiteWorkerControlClient` have different privilege/caller boundaries. Removing them to hit LOC targets would regress safety.

## S3 deployment boundary

- **Product Route A** stays one Bootstrap API + Coordinator lock/journal; canonical Bundle v3 is the PPU Asset Set policy, not a requirement of standalone OPF.
- **Engineering Route B** remains distinct and optional; migration into Product Route A is not implemented by this deletion PR. Do not add a third entrypoint or erase unqualified Engineering paths.
- **Standalone OPF** `software/python/plasma_opf/python_provider.py` operates Host-only without PPU, Bundle, C-3, FPGA or OpenOCD; fake subprocess success remains `programming_status=NOT_QUALIFIED`.
- The retired Bundle v1/v2 source code is not restored; historical source/docs/tests that intentionally assert rejection are not an operative legacy Compatibility API.
- B1/B2/B3 activation does not equal DUT Flash; [actual Bundle A and B Site 2 Jobs](../evidence/opf-site2-ab-newpath-2026-11-08.md) prove only the exact selected target/firmware.

## Remaining work and not overclaiming completion

This bounded PR resolves **one true duplicate hardware-write entry**, reconciles S1-C/S2/S3 architecture/evidence, and preserves all current guards. It does **not** complete S2 multi-Site safety/recovery negative HIL, the Route B migration, multi-Host extension, or full S5 dead-code cleanup. Second physical Provider and eight-Site test are intentionally deferred.

**Merge/deploy decision:** Draft Gate 1; exact-HEAD CI and independent Owner Gate 2 are required. Documentation and deletion do not require Z2 Runtime redeployment; the obsolete CLI lived only on SWPC.
