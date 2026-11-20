# Site-level Programming Admission — Gate 3: SWPC deploy + Z2 HIL (2026-11-20)

**Result: 400/400 Job PASS. Deploy PASS. Safety contract held. Scenario A/B (Site-level independence while the peer is
running) is NOT_VERIFIED: in natural Same-IC Debug execution the two Sites stay phase-locked, so the run cannot tell
"no barrier" from "barrier". Throughput improvement over the #1503 baseline: measured (+7.9 %).**

Tools: `plasmactl` (status / verify / restart / deploy / diagnose / program submit), Manager Batch + cycles API, PPU
`/api/status`, Bootstrap `/v1/status`, Manager run journal (`bundle-programming-runs.json`, copied read-only every 60 s
because it keeps ~64 Runs), `jq`, `journalctl`. Z2-internal read-only state and job-log counts: the existing SSH helper
`../z2-root-wo1-deploy-20261119/z2.py`, the same commands as the WO-1 evidence. No product code, script, harness or
instrumentation was added. Analysis = two inline jq filters saved as text (`analysis-jq-filter.txt`,
`compare-jq-filter.txt`).

## A. Deployment (SWPC Control Station only)
- Before: CS `9b61d633a922` (has #1503 logic, not #1510). Target: main `ba1a4b713e4a` (= #1510 merge; main was not ahead).
  Delta vs the live release = #1510 only (Manager programming admission), so this deploy was not a no-op.
- `plasmactl deploy local-control-station` from a detached worktree at ba1a4b713: exit 0; built-in preflight PASS (`deploy/cs-deploy.log`).
- Verify PASS, `plasmactl restart`, then verify PASS again; Manager and Console services active; z2 ONLINE + managed-control READY; Sites 1/2 idle (`deploy/`).
- Installed code check: release venv has `programming=True` and `RELEASE_PENDING_REASONS = {"SITE_NOT_READY_OR_BUSY"}` (`deploy/installed-code-check.txt`).
- Backup: `backup/state-local-control-station.tgz` (Manager journals, registry, **bootstrap credentials — mode 600**), `backup/config.tgz`, `backup/previous-release.txt` (`releases/9b61d633a922`). Rollback = redeploy 9b61d633a / repoint `current` + restart.
- Not touched: Z2 Runtime (stays `acdfd7403`), Root protected tree, privileged-source-install, FPGA, Active Set, Registry/Endpoint, Programming Profile.

## Pre-check (`precheck/`)
Preflight PASS (16 Batches / 64 Runs / 82 Starts, PPU IDLE); no open or UNKNOWN Batch or Run; z2 → `http://192.168.2.99:18080`, commissioned;
PPU lease free, no runtime activation, Sites 1/2 idle (openocd); Bootstrap `bootstrap_ready`, Runtime `runtime_active` acdfd7403,
last deployment `succeeded` (tx c12a6c30); Active Set 957ac4e6 gen 25 VERIFIED (stm32f103c8t6-site2-operations); Root manifest 9bd9ba30,
guard f4dfb55e, FPGA journal 986446e7, fpga_manager operating, no OpenOCD, 0 admission records, max_concurrent_jobs 2.
**Physical DUT presence cannot be observed remotely.** It was shown by Run 0 (`run0-dut-check/`, batch 04754e23…, 2 Jobs E/P/V PASS + SAFE_OFF)
after the deploy and before Run 1. Power and wiring were not inspected physically (NOT_VERIFIED; setup unchanged since the WO-1 PASS of 2026-11-19).

## B/C. HIL — Same-IC Debug, Sites 1+2, one Batch owner, image e691ab23 (62 800 B), E/P/V, retry 0
`plasmactl program submit --target z2:1,2 --icpn STM32F103C8T6 --operations erase,program,verify --image … --retry-limit 0 --repeat 100 --replace-ic no`

| Run | Batch | Window (UTC) | Result |
|---|---|---|---|
| 1 | 975fefabcc66992338b9119a80cc0a0f | 03:09:40–03:30:24 | PASS 200/200 |
| 2 | ef273ba5c1d3f5b666392d055800ecb6 | 03:30:36–03:51:22 | PASS 200/200 |

Each run: 200 distinct job/run/plan IDs; every Job `success`, operations erase+program+verify, readback e691ab23, SAFE_OFF true in both the
attempt and the receipt; 0 retry; 0 blocked_dispatch records; 0 AWAITING_CONTINUE / NEXT_CYCLE / PPU_BUSY in progress; 1 Batch POST and
1 start POST per journal (no resend); 0 OUTCOME_UNKNOWN. Z2 job logs (`post/z2-joblog-counts.txt`, 402 = 400 + Run 0): ADMISSION_DENIED 0,
PROC_SCAN_INCOMPLETE 0, job_error 0, stage_failed 0. Manager journal: no PPU_BUSY / NEXT_CYCLE / OUTCOME_UNKNOWN / Traceback.

## D/E. Timeline and next-Cycle latency (`roundN/analysis.json`, rows per Job + per next Cycle)
Timestamps used: PPU Job created_at (submit accepted), started_at, updated_at (terminal); Manager attempt started_at (attempt reserved after
admission + plan), finished_at, cycle settled_at; Manager run steps PREFLIGHT (live Site readiness PASS) and PROGRAMMING_SUBMIT
(run-step coverage 200/200 and 198/200).

| next Cycle (198 per run) | Run 1 mean / p95 / max s | Run 2 mean / p95 / max s |
|---|---|---|
| Job terminal → Manager observed | 0.183 / 0.321 / 0.480 | 0.196 / 0.334 / 0.430 |
| Job terminal → Cycle settled | 0.231 / 0.368 / 0.513 | 0.243 / 0.375 / 0.494 |
| Job terminal → next attempt reserved (≥ admission + plan) | 1.323 / 1.597 / 1.766 | 1.344 / 1.575 / 1.802 |
| next attempt → PREFLIGHT readiness PASS | 0.331 / 0.375 / 0.391 | 0.335 / 0.384 / 0.395 |
| next attempt → PPU accepted Job | 1.074 / 1.237 / 1.589 | 1.085 / 1.261 / 1.583 |
| **Dispatch latency: terminal → next Job submitted** | **2.397 / 2.802 / 3.348** (p50 2.354) | **2.428 / 2.851 / 3.008** (p50 2.414) |
| terminal → next Job started | 2.755 / 3.198 / 3.745 | 2.789 / 3.239 / 3.393 |

NOT_VERIFIED (no such record): the Site release / SAFE_OFF instant (SAFE_OFF is a boolean in the terminal receipt; terminal is the upper bound), and
the exact admission instant (only "attempt reserved", which follows admission + plan, is recorded).
Overlap: Cycles 2–100 overlapping 99/99 in both runs; same-index overlap mean 9.75 / 9.70 s; total Site 1×Site 2 overlap 975 / 970 s.

## F. Site-level independence (Scenario A/B) — NOT_VERIFIED
Discriminating test: when Site X is released while the peer's Job J is still running, does X's next Job start before J ends?
- Old #1503 (WO-1): 0/99 per run. New #1510: 0/99 in both runs.
- Why the new run cannot show it: when a Site is released the peer's Job has at most **0.33 s (Run 1) / 0.42 s (Run 2)** left
  (mean 0.13 / 0.15 s), while a Site's own next Job starts no earlier than **2.31 s** after its own terminal. Both Sites start together and run
  ~9.6 s Jobs, so they stay phase-locked and the peer always finishes first. The cruder "started while the peer was running" counts
  (41+58, 53+46) are the same in the old run (52+47), because the two first-starts differ by a few hundred ms: they are not evidence.
- The HIL therefore does not prove or disprove A/B. Host-only coverage (PR #1510 T1/T3/T4) remains the evidence for the logic.
- Proposed separate acceptance (needs authorization, existing CLI only): one Batch, `--replace-ic yes --repeat 3`, Sites 1+2. After Cycle 1 both
  pause; `plasmactl program continue` Site 1 only; while its Job runs (≈5 s in), continue Site 2. Pass = Site 2 Job created_at < Site 1 Job
  updated_at (Scenario A), and the mirror for B. With #1503 the Site 2 admission would have waited for Site 1 + a fleet refresh.

## G. Old (#1503) vs new (#1510) — same Z2 (Runtime acdfd7403, Root 9bd9ba30, Active 957ac4e6, 2 Blue Pills, same image/route)
Old baseline = WO-1 HIL 2026-11-19 (`../wo1-hil-2site-2x100-20261119`, CS 750fbb4cd). The Manager delta 750fbb4cd→9b61d633a is Catalog-only
(#1502, outside the programming path), so the difference is attributable to #1510. Start-basis numbers (`compare-old-vs-new.txt`):

| | Old R1 | Old R2 | New R1 | New R2 | Change |
|---|---|---|---|---|---|
| Throughput Jobs/min | 8.96 | 8.93 | 9.67 | 9.66 | **+7.9 %** |
| s per Cycle per Site | 13.39 | 13.43 | 12.40 | 12.42 | −0.99 s (−7.4 %) |
| Terminal → next start, mean | 3.79 | 3.84 | 2.76 | 2.79 | **−1.04 s (−27 %)** |
| same, p95 / max | 4.67 / 5.03 | 4.72 / 5.13 | 3.20 / 3.75 | 3.24 / 3.39 | |
| Job duration mean | 9.65 | — | 9.64–9.71 | 9.64–9.67 | unchanged |
| Span 200 Jobs (s) | 1339 | 1344 | 1241 | 1242 | −98 s |

The ~1 s gap reduction is consistent with removing the wait for the Manager's 2 s fleet observation (#1503 re-checked every 0.5 s until the
snapshot showed both Sites idle). Old per-next-Cycle dispatch latency (terminal → submitted) is not available: the WO-1 records lack PPU
created_at. The old-vs-new comparison therefore uses terminal → started.

## H. Safety contract
400/400 SAFE_OFF; no unauthorized resend (1 Batch POST and 1 start POST per run); 0 UNKNOWN; 0 Root Guard denials; no PPU_BUSY anywhere;
one owner per run. The different-owner PPU_BUSY contract and the "unsafe Site never starts its next Cycle" rule were **not exercised on hardware**
(per instruction: no injected conflicts). Host-only evidence: #1510 T5/T6/T8 plus the unchanged PPU lease tests.

## I. Final state (`post/`)
Preflight PASS (19 Batches / 64 Runs / 85 Starts, PPU IDLE); CS verify PASS (ba1a4b713); PPU lease free, no activation, Sites 1/2 idle, queue 0;
no open or UNKNOWN Batch or Run. Z2 identical to pre-check: Runtime 0.2.1-acdfd7403058, Root 9bd9ba30, guard f4dfb55e, FPGA journal 986446e7
(no reload), fpga_manager operating, no OpenOCD, 0 admission records, Active 957ac4e6 gen 25.
