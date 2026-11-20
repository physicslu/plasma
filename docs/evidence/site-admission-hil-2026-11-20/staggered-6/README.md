# Site-level Admission Gate 3-B — 2-Site Staggered Continue (2026-11-20 04:11–04:12 UTC) — PASS

SWPC CS `ba1a4b713e4a` (#1510), Z2 Runtime acdfd7403, Root 9bd9ba30, FPGA journal 986446e7, Active 957ac4e6 gen 25 — all unchanged.
Tools: `plasmactl` (verify / diagnose / program submit / continue / status), Manager Batch + cycles API, PPU `/api/status`,
Bootstrap `/v1/status`, `jq`, `journalctl`. Z2-internal read-only state/log counts use the existing SSH helper and the same commands as
`../site-admission-gate3-20261120`. No script, tool, code change, deploy or PR.

**IC handling (owner decision 2026-11-20: 「不用換片」).** No IC was replaced or re-seated and the fixture was not touched. `--replace-ic yes`
was used only so that each Site pauses after a Cycle and the next Cycle starts on an explicit `plasmactl program continue`, which is how the
Sites were staggered. The 4 Continue records (`post/continue-records.jsonl`, actor `plasmactl-local:<operator>`, `actor_verified: false`) therefore
mean "same IC, owner-approved", **not** "replaced": these 6 Cycles are 3 repeated programmings of the same 2 ICs, not 6 distinct units.

Batch **35366e0eadda43417423ab544e87855a** — `--target z2:1,2 --operations erase,program,verify --repeat 3 --replace-ic yes --retry-limit 0`,
image e691ab23 (62 800 B). Outcome PASS, COMPLETED, cycles 6/6 PASS.

| Site | Cycle | Job | PPU created (accepted) | started | ended |
|---|---|---|---|---|---|
| 1 | 1 | job-20261120-041121-3229f489 | 04:11:21.253 | 04:11:21.574 | 04:11:31.500 |
| 2 | 1 | job-20261120-041121-f99c6c1f | 04:11:21.682 | 04:11:22.068 | 04:11:31.562 |
| 1 | 2 | job-20261120-041151-7350c561 | 04:11:51.280 | 04:11:51.596 | 04:12:00.338 |
| 2 | 2 | job-20261120-041158-6b698824 | 04:11:58.517 | 04:11:58.850 | 04:12:07.744 |
| 2 | 3 | job-20261120-041216-1f4df796 | 04:12:16.338 | 04:12:16.654 | 04:12:25.593 |
| 1 | 3 | job-20261120-041223-da79f898 | 04:12:23.801 | 04:12:24.123 | 04:12:33.160 |

All 6: state success, operations erase+program+verify, readback e691ab23, SAFE_OFF true (PPU result, Manager attempt and receipt); distinct
job/run/plan IDs (`cycles.json`); 1 Batch POST + 1 start POST (`journal.json`): no resend.

## Direction A — Cycle 2: Site 1 running, Site 2 starts its next Cycle (`cycle2-steps.log`, `cycle2-fleet.json`)
- 04:11:49.347 Continue Site 1 (ACCEPTED). PPU: Site 1 running job …7350c561 at 04:11:51.927, still running at 04:11:55.929.
- Fleet (Manager observation) observed_at **04:11:54.087**: Site 1 `running` / …7350c561, Site 2 idle. Read 04:11:56.162.
- 04:11:56.202 Continue Site 2.
- **PPU accepted Site 2 Cycle 2 at 04:11:58.517 and started it at 04:11:58.850; Site 1 Cycle 2 ended 04:12:00.338**, so the PPU accepted the
  Job 1.82 s and started it 1.49 s before the peer Job ended. Both Jobs ran at once for 1.49 s. PPU poll at 04:11:59.190 shows both running.

## Direction B — Cycle 3: Site 2 running, Site 1 starts its next Cycle (`cycle3-steps.log`, `cycle3-fleet.json`)
- 04:12:14.613 Continue Site 2. PPU: Site 2 running …1f4df796 at 04:12:16.974, still running at 04:12:20.976.
- Fleet observed_at **04:12:20.181**: Site 2 `running` / …1f4df796, Site 1 idle. Read 04:12:21.210.
- 04:12:21.249 Continue Site 1.
- **PPU accepted Site 1 Cycle 3 at 04:12:23.801 and started it at 04:12:24.123; Site 2 Cycle 3 ended 04:12:25.593**: 1.79 s / 1.47 s before.
  PPU poll at 04:12:24.605 shows both running.

In both directions the next Cycle's admission ran while the Manager's own fleet observation showed the peer Site active. Under the #1503 gate
that observation produced PPU_BUSY and a wait; under #1510 the Site was admitted at once.

## Safety / negative
NEXT_CYCLE_EXECUTION_PPU_BUSY 0; PPU_BUSY / NEXT_CYCLE / OUTCOME_UNKNOWN / Traceback in the Manager journal 0; blocked_dispatch records 0;
Z2 job logs (6): ADMISSION_DENIED 0, PROC_SCAN_INCOMPLETE 0, job_error 0, stage_failed 0. Different-owner and maintenance contracts:
not exercised on hardware (no injected conflicts); unchanged code, covered by #1510 Host-only T5/T6 and the existing PPU lease/quiesce tests.

## Before / after (`precheck/`, `post/`)
Before: CS verify PASS, preflight PASS, z2 OBSERVED/execution_ready, Sites 1/2 idle (last Jobs success, SAFE_OFF), lease free, no activation,
Bootstrap ready / runtime_active / deployment succeeded, no open or UNKNOWN Batch.
After: preflight PASS (20 Batches / 64 Runs / 86 Starts, PPU IDLE), CS verify PASS, lease free, Sites 1/2 idle with queue 0, no open or UNKNOWN
Batch or Run; Z2 state identical (Runtime, Root manifest/guard, FPGA journal, fpga_manager operating, no OpenOCD, 0 admission records, Active Set).
