# `plasmactl program` — Z2 2-Site programming HIL, fourth repeat on CS d282adcbf (2026-11-19)

**Verdict: PASS.** A fourth `plasmactl program submit` on the same deployment
as [`plasmactl-program-2site-hil-2026-11-19`](../plasmactl-program-2site-hil-2026-11-19/README.md)
[`-run2`](../plasmactl-program-2site-hil-2026-11-19-run2/README.md) and
[`-run3`](../plasmactl-program-2site-hil-2026-11-19-run3/README.md): one
Manager start ID and exactly one Batch over Z2 Sites 1+2; both Sites ran
Erase/Program/Verify once, with matching readback and SAFE_OFF. Scope: one PPU
(`z2-hil`), two physical Sites, STM32F103C8T6 Blue Pills. The PASS is the
Manager-persisted Batch outcome plus the PPU Job receipts; no LA2016 capture
or USB CDC boot check was part of this run, and it is not an electrical or
production qualification. Run time 2026-11-19 03:52 UTC (11:52 CST).

## Deployed identity (unchanged since the previous run)

| Item | Value |
|---|---|
| SWPC Control Station (Manager + Console) | `d282adcbfcad` (main `d282adcbf`) |
| Z2 Runtime | `0.2.1-ebde888471c8` |
| Active Set / Root / FPGA journal | `957ac4e6…` gen 25 / `51e87bfe…` / `986446e7…` |
| `max_concurrent_jobs` | 2 |

The operator CLI ran from a checkout of main `18e83ec42`; since the previous
run main changed only by evidence documents (#1494), and nothing was
redeployed.

## Command

```bash
scripts/plasmactl program submit --target z2:1,2 --icpn STM32F103C8T6 \
  --image plasma-blue-pill-cdc-v0.2.bin --journal journal.json --wait-timeout 600
```

Image SHA-256 `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c`
(62,800 B, the previously approved v0.2 image). Operations default
`erase,program,verify`; `retry_limit` 0; stop policy `never`. Precondition:
deployment preflight before the Batch PASS — Manager healthy, PPU execution
`IDLE` ([`preflight-before-run.json`](preflight-before-run.json)).

## Results

| | Value |
|---|---|
| CLI exit | 0 |
| Start ID / Batch ID | `4cf8aac2ab80995c66ba9921fdfe52bf` / `a3116b5278ba5f5bec33e6220c38291b` |
| Start / Batch POSTs | 1 / 1 ([`journal.json`](journal.json)) |
| Batch | `finished`, outcome `PASS`, `journal_persisted: true`, 2 pass / 0 fail / 0 blocked / 0 unknown |
| Manager Batch elapsed | 12.43 s (created → finished, Manager clock); previous runs 13.87 s, 12.36 s, 12.42 s, 12.65 s |
| `plasmactl program receipt` | `manager_reported_pass: true` ([`receipt.json`](receipt.json)) |
| Deployment preflight after the Batch | PASS, PPU `IDLE`, 8 Batches / 16 Runs / 26 Starts ([`preflight-after-run.json`](preflight-after-run.json)); exactly one Batch more than after the previous run |

| Site | Job | Operations | Image | Readback | SAFE_OFF | Attempts |
|---|---|---|---|---|---|---|
| 1 | [`job-20261119-035227-b1e416a6`](job-20261119-035227-b1e416a6.json) | erase, program, verify | `e691ab23…` 62,800 B | `e691ab23…` | true | 1 |
| 2 | [`job-20261119-035227-307abbb2`](job-20261119-035227-307abbb2.json) | erase, program, verify | `e691ab23…` 62,800 B | `e691ab23…` | true | 1 |

Files: [`report.json`](report.json) (CLI output),
[`progress.txt`](progress.txt) (CLI stderr progress),
[`timing-summary.txt`](timing-summary.txt)
(`plasma_hil_timing.py summarize --report report.json`). Job JSON is the PPU
Gateway `GET /api/status?job=…` record; the Gateway has no
`GET /api/jobs/<id>` route (it returns 404).

## Not covered

Retention pruning on hardware (8 Batches, far below the 32-Batch limit), LA2016
SWD waveform, USB CDC firmware boot, CPU/RAM sampling, Sites beyond 1–2, other
PPUs, and any repeat or retry behaviour inside one Batch.
