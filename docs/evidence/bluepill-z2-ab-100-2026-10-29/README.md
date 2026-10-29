# Blue Pill 100-pair A/B physical burn-in — 2026-10-29

**Observed result: PASS — 100/100 paired cycles, 200/200 Flash attempts, 0 failures.**

This directory preserves the three complete A/B Runner files supplied by the owner. The large `events.jsonl` is stored as a lossless, deterministic gzip file; its original SHA-256 is recorded below. These are **real SWPC/Z2/FPGA/STM32F103C8T6 execution receipts**, not hosted-CI simulations. This result belongs to the tested PR #1206 software and the unchanged Native C/FPGA hardware path; it does **not** claim that the different PR #1207 Python/Receipt implementation completed the same physical run.

## Immutable source and execution identity

| Identity | Verified value |
| --- | --- |
| Tested source commit (PR #1206) | `1b7cae67d40ebc2baadc608e29ab5684e6b03f53` |
| Tested Z2 engine, `scripts/plasma_wordport_program.py`, SHA-256 | `006ec0956b7d29c47dc3b660c1870aca5f99a3c1bcfa7d72cf0c41b8650adbc2` |
| Engine source-to-receipt equality | **MATCH**: the SHA-256 independently computed from that exact PR commit equals the digest recorded in all 200 Program and 200 Reset receipts |
| Stage Monitor source, `software/python/plasma_interfaces/wordport_stage_monitor.py`, SHA-256 | `84f0b557b09cb728c612971c598baea7457c28bfe0f2873bef205238ba9f226e` |
| Stage Monitor source-to-receipt equality | **MATCH**: the independent PR-commit source digest equals the digest recorded in all 200 Program receipts |
| Native C ARMv7 bridge, recorded SHA-256 | `66261cef851c9777469b393b7539c5b0f8c2b039a032f1a5b4cbf9e93460e447` |
| OpenOCD binary, recorded SHA-256 | `20690fc154bf7c76ad2ce46a33bee2e3038623a2f951c698425be13133f3b640` |
| `target/stm32f1x.cfg`, recorded SHA-256 | `bd086fbcb18aaed8839f844be4a8abfa6c284b776e05c8e7e8f1883d6686d7fe` |
| Z2 Boot ID, consistent across 200 receipts | `4cefdc0c-f586-4d19-b126-1d8e1108c8f1` |
| FPGA Image SHA-256 required by the unchanged PR #1206 / `main` Manifest | `bfbd3d872caeff05a8f9daa0829b6292e5b5036c6c6b927d6c779e13fe9ec1a1` |
| New `main` after #1207 merge | `e338083564c30dc6bdc24009f7b62a3984fb7023` |
| New `main` engine SHA-256 (different) | `2e5ca21b99e0018c881bac73bd53fcf0bcdaf6417bf6ea69fc7d97b865839e16` |

The Z2 preflight in the tested, SHA-pinned engine requires actual Native C and companion-file SHA matches, protected Root source checks, a current-boot FPGA Manager `operating`/held-image/Manifest/Golden consistency check, and free ownership/MMIO resources before hardware operations. The supplied three A/B Runner files contain successful operation receipts, not standalone contemporaneous Root/FPGA Manager snapshots.

## Physical acceptance

| Measurement | Observed value |
| --- | --- |
| UTC start | `2026-10-29T05:51:13.901474+00:00` |
| UTC completion | `2026-10-29T08:35:06.164993+00:00` |
| Runner elapsed time | `9832.3` seconds (2 h 43 min 52.3 s) |
| Target | exact `STM32F103C8T6`, Site 1 |
| Order | `v0.1` then `v0.2`, repeated 100 times |
| Attempts / passing attempts / failures | `200 / 200 / 0` |
| Program-stage operations | 200 `program-verify`, each Erase / Program / OpenOCD `verify_image` PASS |
| Explicit `reset-run` | 200 PASS |
| Post-reset CDC | 200 PASS; 3 consecutive valid Heartbeat frames per attempt (600 frames total) |
| v0.1 image | 18,768 bytes; SHA-256 `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d`; 100 PASS |
| v0.2 image | 62,800 bytes; SHA-256 `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c`; 100 PASS |
| CDC port / expected periods | `/dev/ttyACM0`; v0.1 500 ms, v0.2 1000 ms |
| Independent Readback | explicitly OFF; `readback_requested=false`, `readback_sha256=null` |
| Auto-retry | disabled, `no_auto_retry=true` in all Program/Reset receipts |
| Event integrity | 1,204 JSONL rows; exact per-attempt order and alternating version sequence; timestamp and progress counters monotonic |
| Runner terminal result | `COMPLETE`, `current=200`, `passed=200`, `failed=0` |

All 200 Program receipts report engine/OpenOCD/Bridge exits `0`, released sockets, PASS stage counter reconciliation and passing Erase/Program/Verify stages. All 200 Reset receipts report no Flash write. All 200 CDC receipts report zero wrong-version samples and three valid frames.

## Preserved raw evidence and integrity

| Repository file | Original bytes | SHA-256 |
| --- | ---: | --- |
| `status.json` | 409 | `df2f727104f3083676463a51eec348093a3251ce15940be3f3d10dfabfaf5fb1` |
| `progress.log` | 127,948 | `f790b88d05d72d07a81ffaea28ba8b14b8ce86ab12b354a69e8221145b130940` |
| `events.jsonl.gz` (gzip, lossless) | 178,353 compressed | `aab514e8ae84f3d6617dd8273ddce1752aff5dea9d7b3099acf2c8f445ec7334` |
| `events.jsonl` (uncompressed, reconstructed with `gzip -dc`) | 2,066,256 | `4dc66b57551bbae0403dbec78806f2d51d2987464d05ca4a1b7060d1f0d67d17` |

To independently verify the reconstructed raw event stream: `gzip -dc events.jsonl.gz | sha256sum`. The gzip stream was created with `gzip -n` and passes `gzip -t`.

The owner's original Runner evidence directory was `/storage/projects/plasma-ab-runs/20261029T055113Z-4136626`. This repository snapshot preserves all **three owner-supplied Runner evidence files**; the separate per-attempt Z2 `openocd.log` and original FPGA Manager/Root raw snapshots were not supplied and are not represented as archived here.

## Qualification boundaries and PR disposition

- This is a **bounded physical integration PASS** for one Site, one Blue Pill and two exact firmware images, with OpenOCD Verify and brief CDC observation after each reset. It is not general IC-programmer qualification.
- No independent Readback, logic-analyzer capture or analog voltage measurement was performed in this run. `electrical=NOT_MEASURED_DEV_MODE_NON_BLOCKING`; SWD WAIT/FAULT/retry counters are `NOT_OBSERVED`, not measured zero.
- No physical Flash failure occurred, so the failure-register diagnostic path was not exercised by this run. Its Host-only tests are separate.
- The PR #1207 merge introduces a different `program` + opt-in `--readback` contract and uses `readback_enabled` and a `SKIPPED` stage rather than the tested #1206 `program-verify` / `readback_requested` contract. Both retain the same Native C bridge and FPGA image source pins, but #1207 cannot automatically claim this exact end-to-end 100-pair physical result.
- This evidence-only commit preserves the tested PR #1206 source commit as the immutable reference. It does not modify code, deploy software, control hardware, request a merge, or elevate any L2 / SUPPORTED qualification.
