# Dead Engineering start_job removal (#1555) — deploy and Z2 Site 2 HIL (2026-11-28)

Owner-authorized deploy of main `7d77b39d7` (PR #1555: removal of the Gateway Engineering session, Programming Asset cache and Job/cancel write path that U7 made unreachable), followed by read-only post checks and a Z2 Site 2 E/P/V HIL. Result: **PASS**.

## Deploy

| Target | Before → After | Method | Rollback |
|---|---|---|---|
| SWPC Control Station | `b0ac8403ff25` → `7d77b39d7825` | `plasmactl deploy local-control-station`; `verify` PASS | `b0ac8403ff25` |
| Z2 PPU Runtime | `0.2.1-b0ac8403ff25` → `0.2.1-7d77b39d7825` | `plasmactl deploy z2-ps`, kit from run 46128903577 (kit sha256 `0ac4c9f1…`), tx `64bc9559` PASS | `0.2.1-b0ac8403ff25` |
| Z2 Root / journal / Active Set / `max_concurrent_jobs` | unchanged: `e3830a03` / `986446e7` / gen 25 / 2 | no `pl/` change | — |

Files: [`deploy/`](deploy/).

## Post-deploy checks (read-only)

| Check | Result |
|---|---|
| Manager relay `POST /api/engineering/session` (removed) | 404 `managed_route_not_allowed` |
| Z2 unsigned `POST /api/engineering/session` | 403 `CONTROLLER_OPERATION_UNCLASSIFIED` |
| Z2 unsigned `POST` Engineering target `jobs` | 403 `CONTROLLER_OPERATION_UNCLASSIFIED` |
| Manager relay `GET /api/status?site=2` | OK; Active gen 25, Reservation NONE, PPU idle |
| Manager relay `GET /api/engineering/targets` | 503 "Engineering PPU provider is not enabled" — unchanged: the real Z2 runs no Engineering provider |
| Console | 307 (healthy redirect) |

File: [`deploy/post-checks.txt`](deploy/post-checks.txt).

## HIL (Z2 Site 2, STM32F103C8T6, same IC)

| Scenario | Result | Evidence |
|---|---|---|
| `plasmactl program` E/P/V, v0.1, Repeat 3, retry 0 | **PASS** 3/3, batch `9ed60fab`, retry 0, SAFE_OFF true; pre/post Active gen 25, Reservation NONE, PPU idle | [`hil-epv-repeat3/`](hil-epv-repeat3/) |

This confirms that the Manager-owned Batch Programming path works unchanged after the dead Gateway path was removed.

## Not exercised

Read, STOP, multi-Site, Replace-IC, FAIL path, electrical or production qualification.

## Not committed

The Manager submission journal, SSH helper scripts and the downloaded kit stay in the SWPC evidence root `<swpc-evidence-root>/deploy-7d77b39d7-20261128`.
