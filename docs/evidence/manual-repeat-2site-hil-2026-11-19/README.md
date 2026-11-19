# Manual Repeat v1 — Z2 2-Site Repeat HIL (2026-11-19)

**Verdict: run 1 FAIL (defect found, hardware safe) → fixed by #1503 → run 2 PASS.**
First hardware execution of Manual Repeat (WP-02, [#1501](https://github.com/physicslu/plasma/pull/1501))
on one PPU (`z2-hil`), Sites 1+2, STM32F103C8T6 Blue Pills, through the canonical Manager Batch API.
The PASS is the Manager-persisted Batch/Cycle outcome plus the PPU Job receipts (SAFE_OFF verified per Job).
Scope limits are listed at the end; this is not an electrical, production or physical-IC-replacement
qualification.

## Deployed identity

| Item | Run 1 (10:55–10:57 UTC) | Run 2 (12:16–12:18 UTC) |
|---|---|---|
| SWPC Control Station (Manager + Console) | `e3fa6b3f5887` (main `e3fa6b3f5`, #1501) | `750fbb4cdc44` (main `750fbb4cd`, #1503) |
| Z2 Runtime | `0.2.1-ebde888471c8` (per deployment record; not redeployed since 2026-11-18, not re-read here) | same |
| Image | `plasma-blue-pill-cdc-v0.2.bin`, SHA-256 `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c`, 62,800 B | same |

Operations `erase → program → verify`, `retry_limit` 0, stop policy `never`. Preconditions: deployment
preflight PASS with PPU execution `IDLE` and Sites 1/2 idle ([`preflight-before.json`](preflight-before.json),
[`ppu-status-before.txt`](ppu-status-before.txt), [`cs-deploy-750fbb4cd-preflight.txt`](cs-deploy-750fbb4cd-preflight.txt)).

## Method

[`tools/repeat_hil.py`](tools/repeat_hil.py) — evidence helper, not a product path. It calls only canonical
Manager endpoints: issue start → **exactly one** `POST /api/programming/batches` → poll →
(H2) `POST …/continue` per Site. Stop rule: any pause other than `REPLACE_IC` → Stop Queuing, no Continue,
no resend; a lost Batch answer is reconciled read-only. Planned budget: at most 10 programming Jobs per run.

- **H1** — same-IC Debug (`replace_ic_before_next_cycle=false`), `repeat` 3, Sites 1+2.
- **H2** — replace-IC mode, `repeat` 2. When both Sites pause after Cycle 1, Continue **Site 1 only**, hold
  30 s and check Site 2 got no Job, then Continue Site 2.

The Blue Pills were **not physically replaced**: H2's Continue is a test attestation only.

## Results

### Run 1 — CS `e3fa6b3f5` — FAIL (stopped by rule; hardware safe)

| Step | Batch | Outcome |
|---|---|---|
| H1 | `b9cf4e9140c4668810c4bf74a1f553c1` | Cycle 1 PASS on both Sites (Jobs `job-20261119-105600-22afb2dd` S1 / `-1ffb8e2b` S2, overlapping, SAFE_OFF); both Cycle 2s paused `NEXT_CYCLE_EXECUTION_PPU_BUSY` → Stop → `PARTIAL`/`STOPPED`, 2/6 settled |
| H2 | `41ec30d0bb5ecda69073921f9a3773fe` | Cycle 1 PASS on both Sites (`…105708-61d389ee`, `…105708-6ff74434`); Site-1-only Continue → Site 1 Cycle 2 paused `PPU_BUSY` (nothing submitted), Site 2 stayed `REPLACE_IC` with no Job → Stop, 2/4 settled |

4 Jobs, all PASS, no FAIL / OUTCOME_UNKNOWN / resend; PPU idle afterwards.

Defects found:

1. **`PPU_BUSY` on every next Cycle.** Next-Cycle admission re-runs the Platform maintenance gate, which
   reads the Manager's fleet observation (`poll_interval_s: 2.0`). Right after a Job (or while a peer Site
   runs) that observation still shows an active Site → `ppu_busy`. #1501's bounded release re-check only
   covered `SITE_NOT_READY_OR_BUSY`; the Host fake PPU released instantly, so Host tests never showed it.
2. **Deploy preflight rejected the per-Site `PARTIAL` outcome** introduced by #1501
   ([`preflight-after.json`](preflight-after.json): BLOCKED), which would block every later CS deploy while
   these Batches are retained.

Fix: [#1503](https://github.com/physicslu/plasma/pull/1503) (owner chose a bounded re-check, no gate
semantics change): `PPU_BUSY` joins the re-check, bounded at 60 s; preflight accepts `PARTIAL` only with a
consistent ended Cycle record. Merged as `750fbb4cd`, deployed to the SWPC CS (preflight/verify PASS).

### Run 2 — CS `750fbb4cd` — PASS

| Step | Batch | Outcome |
|---|---|---|
| H1 | `838d27038800459675cde30620f2b8c2` | **PASS** `COMPLETED`: 6/6 Cycles PASS, no pause; 6 Jobs, job/run/plan IDs 6/6/6 distinct, all `success`, SAFE_OFF |
| H2 | `713d778aae4f4a3235ce957e49806485` | **PASS** `COMPLETED`: 4/4 Cycles PASS. After the Site-1-only Continue, Site 1 ran Cycle 2 (12:17:53–12:18:03 UTC) while Site 2 stayed `REPLACE_IC` with `settled` 1 and **no Job** for 30 s; Continue Site 2 → done. 4 Jobs, distinct 4/4/4, SAFE_OFF |

Timing ([`overlap-analysis.txt`](overlap-analysis.txt), PPU Job `started_at`/`updated_at`):

| H1 Cycle | Site 1 Job | Site 2 Job | Overlap |
|---|---|---|---|
| 1 | `…121650-31b01f0d` 9.9 s | `…121651-795cd5bb` 9.4 s | 9.4 s |
| 2 | `…121704-a9c5971e` 9.7 s | `…121705-cc99bb32` 9.3 s | 9.0 s |
| 3 | `…121717-66d21d3a` 9.6 s | `…121718-291827b7` 9.1 s | 8.9 s |

6 Jobs in 36.5 s wall; ~3.5 s between Cycles is the fleet observation refresh plus planning. Because both
Sites finish together they re-enter together, so later Cycles still overlap; Sites that drift apart (e.g. one
Retries) would mostly take turns under the PPU-wide gate.

After run 2: preflight PASS (12 Batches / 30 Runs / 44 Starts), PPU `IDLE`, Sites 1/2 idle
([`preflight-after-rerun.json`](preflight-after-rerun.json)). 14 programming Jobs in total today, all PASS.

## Files

`run1-H1-debug-repeat3/`, `run1-H2-replace-ic-repeat2/`, `run2-H1-debug-repeat3/`, `run2-H2-replace-ic-repeat2/`
each hold `report.json` (driver summary), `progress.txt`, `batch-final.json` (Manager Batch view),
`cycles.json` (Manager cycle segment page) and one `job-*.json` per PPU Job (`GET /api/status?job=`).
(The driver's run labels were `H1`/`H2` and `H1b`/`H2b`; `overlap-analysis.txt` uses the latter.)

## Not covered

Physical IC replacement between Cycles; a hardware FAIL-path pause (no FAIL occurred); `repeat` > 3 on
hardware (10,000-Cycle accounting is Host-only, opt-in `PLASMA_REPEAT_STRESS`); Console UI "IC replaced"
marks on hardware (driven through the Manager API here; covered by Playwright); LA2016 / SWD waveforms;
more than one PPU or more than two Sites.
