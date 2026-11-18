# `plasmactl program` — Z2 2-Site programming HIL (2026-11-18)

**Verdict: PASS.** First physical run of the Unified CLI programming command
(PR #1485): one `plasmactl program submit` issued one Manager start ID and
exactly one Batch over Z2 Sites 1+2; both Sites ran Erase/Program/Verify once,
with matching readback and SAFE_OFF. Scope: one PPU (`z2-hil`), two physical
Sites, STM32F103C8T6 Blue Pills. The PASS is the Manager-persisted Batch
outcome plus the PPU Job receipts; no LA2016 capture or USB CDC boot check was
part of this run, and it is not an electrical or production qualification.

## Deployed identity

| Item | Value |
|---|---|
| SWPC Control Station (Manager + Console) | `ebde888471c8` (main `ebde88847`), deployed via `plasmactl deploy local-control-station`; previous `7565ff0b11b8` |
| Z2 Runtime | `0.2.1-ebde888471c8`, `plasma_program.py runtime-deploy` tx `b8eb700e…`; previous `a34f0ef03271` |
| Z2 Runtime Kit | z2-ps-release run 44337052640, kit SHA-256 `74ae0c04…` (ships `utilities/plasmactl`) |
| Active Set / Root / FPGA journal | `957ac4e6…` gen 25 / `51e87bfe…` / `986446e7…` (unchanged) |
| `max_concurrent_jobs` | 2 |

See [`deploy-summary.txt`](deploy-summary.txt).

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
| Start ID / Batch ID | `35f059639b378f0d91719fc7eb712541` / `842900c4ceced9700d6affcc78077ebb` |
| Batch POSTs | 1 ([`journal.json`](journal.json)) |
| Batch | `finished`, outcome `PASS`, `journal_persisted: true`, 2 pass / 0 fail / 0 blocked / 0 unknown |
| Manager Batch elapsed | 13.87 s (created → finished, Manager clock) |
| `plasmactl program receipt` | `manager_reported_pass: true` ([`receipt.json`](receipt.json)) |

| Site | Job | Operations | Image | Readback | SAFE_OFF | Attempts |
|---|---|---|---|---|---|---|
| 1 | [`job-20261118-154328-a21dcb5e`](job-20261118-154328-a21dcb5e.json) | erase, program, verify | `e691ab23…` 62,800 B | `e691ab23…` 62,800 B | true | 1 |
| 2 | [`job-20261118-154328-d86649a2`](job-20261118-154328-d86649a2.json) | erase, program, verify | `e691ab23…` 62,800 B | `e691ab23…` 62,800 B | true | 1 |

After the Batch both Sites were idle with no current Job and no OpenOCD on
SWPC. Files: [`report.json`](report.json) (CLI output),
[`progress.txt`](progress.txt) (CLI stderr progress),
[`timing-summary.txt`](timing-summary.txt) (`plasma_hil_timing.py summarize`).
Job JSON is the PPU Gateway `GET /api/status?job=…` record.

## Not covered

LA2016 SWD waveform, USB CDC firmware boot, CPU/RAM sampling, Sites beyond
1–2, other PPUs, and any repeat or retry behaviour on hardware.
