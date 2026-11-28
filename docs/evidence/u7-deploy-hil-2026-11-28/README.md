# U10 follow-up + U7 Mandatory Reservation — deploy and Z2 Site 2 HIL (2026-11-28)

Owner-authorized deploy of main `b0ac8403f` (PR #1553: U10 follow-up `cabacb88f` + U7 mandatory Resource Reservation `1d49beca8`), followed by Z2 Site 2 HIL. Result: **H1–H4 PASS**.

## Deploy

| Target | Before → After | Method | Rollback |
|---|---|---|---|
| SWPC Control Station | `6cda93f2b5b6` → `b0ac8403ff25` | `plasmactl deploy local-control-station`; `verify` PASS | `6cda93f2b5b6` |
| Z2 PPU Runtime | `0.2.1-6cda93f2b5b6` → `0.2.1-b0ac8403ff25` | `plasmactl deploy z2-ps`, kit from run 46123158605 (kit sha256 `b9e014c2…`), tx `5ffb699b` PASS | `0.2.1-6cda93f2b5b6` |
| Z2 Root / journal / Active Set | unchanged: `e3830a03` / `986446e7` / `957ac4e6` gen 25 | no `pl/` change since U12 | — |

The deployed `ppu.pyz` `plasma_server/site_manager.py` contains the U7 admission check (`PPU Resource Reservation required` ×1, `root_package_action` ×3), identical to the source (`h1-epv-repeat3/h1-z2-code-check.txt`).

Files: [`deploy/`](deploy/) (CS status/verify, Z2 deploy log, Z2 state before/after).

## HIL (Z2 Site 2, STM32F103C8T6, same IC)

| ID | Scenario | Result | Evidence |
|---|---|---|---|
| H1 | `plasmactl program` E/P/V, v0.1, Repeat 3, retry 0 | **PASS** 3/3, batch `a3d7f57f`. Jobs were admitted under U7, so the Manager supplied the Reservation token and execution owner. | [`h1-epv-repeat3/`](h1-epv-repeat3/) |
| H2 | Manager Batch Read `0x08000000`, 64 KiB | **PASS**, batch `19c4a006`. Readback SHA256 equals receipt (`c4a08f9b…`); the first 18768 B equal v0.1. Reservation NONE afterwards. | [`h2-read-64k/`](h2-read-64k/) |
| H3 | Refused ingress | **PASS**: Z2 `GET /api/batches/x` → 410 `PPU_BATCH_RETIRED`; unsigned `POST /api/jobs` with diagnostic/mock labels → 401 `CONTROLLER_UNAUTHENTICATED`; Manager relay `POST /api/jobs`, `/api/jobs/x/cancel` and engineering jobs (removed by U7) → 404 `managed_route_not_allowed`; Console BFF `POST /api/jobs` → 404. PPU idle, Reservation NONE throughout. | [`h3-refused-ingress/`](h3-refused-ingress/) |
| H4 | STOP_QUEUING through the production Console BFF (18190) ×3, Repeat 5, v0.2 | **PASS**: `5feef494`, `252ee8f3`, `09818ffa`. Stop HTTP 200 each, after 3 BFF GETs on the same Batch; the in-flight Cycle finished PASS, the remaining 3 were never submitted, outcome `PARTIAL` `STOP_REQUESTED_NOTHING_SUBMITTED`. | [`h4-bff-stop-x3/`](h4-bff-stop-x3/) |

Post state: Active gen 25, Reservation NONE, PPU idle, no OpenOCD process, no admission records.

## Not exercised on hardware

- PPU-side refusal of a **signed** Job without a Reservation. Only the Manager can sign G13 requests; testing this on hardware would require bypassing it. Covered by the host test `test_u7_every_programming_job_needs_the_active_reservation_token_and_owner`.
- Console reconciliation of a lost STOP response (U10 defect 1). It is client-side and covered by the Playwright lost-STOP tests; a real network loss was not injected.
- Multi-Site, Replace-IC, FAIL path, electrical or production qualification.

## Not committed

Manager submission journals, the 64 KiB Read binary (its SHA256 is recorded above and in `h2-batch.json`), SSH helper scripts and the downloaded kit stay in the SWPC evidence root `/storage/projects/plasma-evidence/u7-deploy-hil-20261128`.
