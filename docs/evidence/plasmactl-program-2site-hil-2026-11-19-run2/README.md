# `plasmactl program` — Z2 2-Site programming HIL, repeat run on CS d282adcbf (2026-11-19)

**Verdict: PASS.** A second `plasmactl program submit` on the same deployment
as [`plasmactl-program-2site-hil-2026-11-19`](../plasmactl-program-2site-hil-2026-11-19/README.md):
one Manager start ID and exactly one Batch over Z2 Sites 1+2; both Sites ran
Erase/Program/Verify once, with matching readback and SAFE_OFF. Scope: one PPU
(`z2-hil`), two physical Sites, STM32F103C8T6 Blue Pills. The PASS is the
Manager-persisted Batch outcome plus the PPU Job receipts; no LA2016 capture
or USB CDC boot check was part of this run, and it is not an electrical or
production qualification. Run time 2026-11-18 17:07 UTC (2026-11-19 01:07 CST).

## Deployed identity (unchanged since the previous run)

| Item | Value |
|---|---|
| SWPC Control Station (Manager + Console) | `d282adcbfcad` (main `d282adcbf`) |
| Z2 Runtime | `0.2.1-ebde888471c8` |
| Active Set / Root / FPGA journal | `957ac4e6…` gen 25 / `51e87bfe…` / `986446e7…` |
| `max_concurrent_jobs` | 2 |

## Command

```bash
scripts/plasmactl program submit --target z2:1,2 --icpn STM32F103C8T6 \
  --image plasma-blue-pill-cdc-v0.2.bin --journal journal.json --wait-timeout 600
```

Image SHA-256 `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c`
(62,800 B, the previously approved v0.2 image). Operations default
`erase,program,verify`; `retry_limit` 0; stop policy `never`. Preconditions
observed with `plasmactl diagnose --target z2:1,2` and `plasmactl deploy
status --ppu z2`: Runtime active, both Sites enabled and idle, no Job, no
OpenOCD on SWPC.

## Results

| | Value |
|---|---|
| CLI exit | 0 |
| Start ID / Batch ID | `4a7ce50cb41ab3369465a9e4e461e902` / `535afce6bec9d3327f701a39aa50770e` |
| Batch POSTs | 1 ([`journal.json`](journal.json)) |
| Batch | `finished`, outcome `PASS`, `journal_persisted: true`, 2 pass / 0 fail / 0 blocked / 0 unknown |
| Manager Batch elapsed | 12.42 s (created → finished, Manager clock); 12.36 s in the previous run |
| `plasmactl program receipt` | `manager_reported_pass: true` ([`receipt.json`](receipt.json)) |
| Deployment preflight after the Batch | PASS, 6 Batches / 12 Runs / 20 Starts ([`preflight-after-run.json`](preflight-after-run.json)); exactly one Batch more than after the previous run |

| Site | Job | Operations | Image | Readback | SAFE_OFF | Attempts |
|---|---|---|---|---|---|---|
| 1 | [`job-20261118-170741-521506fd`](job-20261118-170741-521506fd.json) | erase, program, verify | `e691ab23…` 62,800 B | `e691ab23…` 62,800 B | true | 1 |
| 2 | [`job-20261118-170741-d24b5fc1`](job-20261118-170741-d24b5fc1.json) | erase, program, verify | `e691ab23…` 62,800 B | `e691ab23…` 62,800 B | true | 1 |

After the Batch both Sites were idle with no current Job and no OpenOCD on
SWPC. Files: [`report.json`](report.json) (CLI output),
[`progress.txt`](progress.txt) (CLI stderr progress),
[`timing-summary.txt`](timing-summary.txt) (`plasma_hil_timing.py summarize`).
Job JSON is the PPU Gateway `GET /api/status?job=…` record.

## Not covered

Retention pruning on hardware (6 Batches, far below the 32-Batch limit), LA2016
SWD waveform, USB CDC firmware boot, CPU/RAM sampling, Sites beyond 1–2, other
PPUs, and any repeat or retry behaviour inside one Batch.
