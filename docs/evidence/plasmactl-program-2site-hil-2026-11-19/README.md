# `plasmactl program` — Z2 2-Site programming HIL after the Start retention fix (2026-11-19)

**Verdict: PASS.** After deploying main `d282adcbf` (PR #1488: a consumed Start
is pruned together with its Batch or Run) to the SWPC Control Station, one
`plasmactl program submit` issued one Manager start ID and exactly one Batch
over Z2 Sites 1+2; both Sites ran Erase/Program/Verify once, with matching
readback and SAFE_OFF. The deployment preflight passed before the deploy,
after the Manager restart and after this Batch. Scope: one PPU (`z2-hil`), two
physical Sites, STM32F103C8T6 Blue Pills. The PASS is the Manager-persisted
Batch outcome plus the PPU Job receipts; no LA2016 capture or USB CDC boot
check was part of this run, and it is not an electrical or production
qualification. Run time 2026-11-18 16:52 UTC (2026-11-19 00:52 CST).

The previous run on `ebde88847` is in
[`plasmactl-program-2site-hil-2026-11-18`](../plasmactl-program-2site-hil-2026-11-18/README.md).

## Deployed identity

| Item | Value |
|---|---|
| SWPC Control Station (Manager + Console) | `d282adcbfcad` (main `d282adcbf`); previous `ebde888471c8` |
| Z2 Runtime | `0.2.1-ebde888471c8` (unchanged; #1488 is Manager-only) |
| Active Set / Root / FPGA journal | `957ac4e6…` gen 25 / `51e87bfe…` / `986446e7…` (unchanged since 2026-11-18) |
| `max_concurrent_jobs` | 2 |

See [`cs-deploy-summary.txt`](cs-deploy-summary.txt).

## Command

```bash
scripts/plasmactl program submit --target z2:1,2 --icpn STM32F103C8T6 \
  --image plasma-blue-pill-cdc-v0.2.bin --journal journal.json --wait-timeout 600
```

Image SHA-256 `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c`
(62,800 B, the previously approved v0.2 image). Operations default
`erase,program,verify`; `retry_limit` 0; stop policy `never`. Preconditions
observed with `plasmactl diagnose --target z2:1,2`: both Sites enabled and
idle, no Job, no OpenOCD on SWPC.

## Results

| | Value |
|---|---|
| CLI exit | 0 |
| Start ID / Batch ID | `57207f48b706857de89d2c6be50a330c` / `e3d6c9d222657252b598a3f29ab10385` |
| Batch POSTs | 1 ([`journal.json`](journal.json)) |
| Batch | `finished`, outcome `PASS`, `journal_persisted: true`, 2 pass / 0 fail / 0 blocked / 0 unknown |
| Manager Batch elapsed | 12.36 s (created → finished, Manager clock); 13.87 s on 2026-11-18 |
| `plasmactl program receipt` | `manager_reported_pass: true` ([`receipt.json`](receipt.json)) |
| Deployment preflight after the Batch | PASS, 5 Batches / 10 Runs / 17 Starts ([`preflight-after-run.json`](preflight-after-run.json)) |

| Site | Job | Operations | Image | Readback | SAFE_OFF | Attempts |
|---|---|---|---|---|---|---|
| 1 | [`job-20261118-165248-de94ab35`](job-20261118-165248-de94ab35.json) | erase, program, verify | `e691ab23…` 62,800 B | `e691ab23…` 62,800 B | true | 1 |
| 2 | [`job-20261118-165248-7c754c46`](job-20261118-165248-7c754c46.json) | erase, program, verify | `e691ab23…` 62,800 B | `e691ab23…` 62,800 B | true | 1 |

After the Batch both Sites were idle with no current Job and no OpenOCD on
SWPC. The Manager journal held one more Batch than this run accounts for
(3 at deploy, 5 after); that Batch was not submitted by this run and had
finished. Files: [`report.json`](report.json) (CLI output),
[`progress.txt`](progress.txt) (CLI stderr progress),
[`timing-summary.txt`](timing-summary.txt) (`plasma_hil_timing.py summarize`).
Job JSON is the PPU Gateway `GET /api/status?job=…` record.

## Not covered

Retention pruning itself on hardware (the journal holds 5 Batches, far below
the 32-Batch limit; pruning is covered by host-only tests in PR #1488), LA2016
SWD waveform, USB CDC firmware boot, CPU/RAM sampling, Sites beyond 1–2, other
PPUs, and any repeat or retry behaviour on hardware.
