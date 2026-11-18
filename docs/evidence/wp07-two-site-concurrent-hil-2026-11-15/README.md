# WP-07 — Z2 2-Site concurrent programming HIL (2026-11-15)

**Verdict: PASS for real 2-Site concurrent E/P/V on Z2 Site 1 + Site 2, and PASS for Site-local definite FAIL not blocking the healthy Site.** Scope is two physical Sites of one PPU (`z2-hil`), STM32F103C8T6 Blue Pills, 2 MHz SWD. It is not a 4/8-Site or production qualification. Shared-fault fail-closed was verified Host-only (WP-01 tests); no physical fault was injected.

## Final deployed identity

| Item | Value |
|---|---|
| SWPC Control Station (Manager, WP-01 lanes) | `109a97602a0c` |
| Z2 Runtime | `0.2.1-f1994ba5ca19` (main `f1994ba5c`) |
| Root guard / Root manifest | `caa87754…` / `5e2ccdd1…` (#1450 + #1455) |
| Engine admission / OpenOCD | `c6dd05e6…` (#1450, pinned by #1451) / `b8a7db67…` |
| FPGA image | `z2-independent-swd-v5-d0add58c`, journal unchanged, no reload |
| Active Asset Set | `957ac4e6…` gen 22, Resource reuse on every Job |
| `max_concurrent_jobs` | 2 (`/etc/plasma/ppu.yaml`) |

## Results

| Step | Batch | Result |
|---|---|---|
| 2a Site 1 alone, v0.2 | `b0ce9322…` | PASS, readback `e691ab23…` 62,800 B, safe_off |
| 2b Site 2 alone, v0.2 | `e4cb9385…` | PASS, same |
| 3 Sites 1+2, v0.1, max 1 (negative control) | `c49f3645…` | PASS both; PPU serial; LA both-clocking 1-ms windows = **0** |
| 5 Sites 1+2, v0.2, max 2 (before fixes) | `81d906d1…` | FAIL: Site 2 refused `ADMISSION_DENIED` (Root fence EX) → fixed by #1450 |
| 6 verify-only, max 2 (after #1450) | `4aabca9a…` | Site 1 refused `PROC_RESOURCE_OWNER_CONFLICT` (census snapshot race) → fixed by #1455 |
| **6b** verify-only v0.1, Sites 1+2 | `332df1a4…` | **Site 1 definite FAIL `VERIFY_MISMATCH`** (readback `0ecc03b3…`, worker safe_off true); **Site 2 PASS** (`8d3ffb02…`, safe_off) |
| **5b** E/P/V v0.2, Sites 1+2 | `025ccf49…` | **PASS both**, readback `e691ab23…` 62,800 B, safe_off, one attempt each |

All refused attempts were refused before OpenOCD started (no SWD edges for that Site); no Site was sealed and no attempt was resent.

## Overlap proof (step 5b)

LA2016, one sample clock, 20 MHz, 1.4 V; Site 1 SWCLK/SWDIO = CH3/CH4, Site 2 = CH0/CH1.

- Site 2 SWCLK 13.194–17.691 s, Site 1 SWCLK 14.297–18.781 s → **3.394 s interval overlap**, **2,565** 1-ms windows with both clocks toggling.
- PPU Job RUNNING (Z2 clock): Site 2 15:26:30.996–42.650, Site 1 15:26:32.590–43.610.
- Manager scheduling: one Batch, one POST, both lanes started together.

## Performance baseline (500 ms sampling)

| Metric | Value |
|---|---|
| Z2 CPU (both cores, 12.6 s job window) | avg 77.6 %, peak 100 % |
| Z2 RAM | total 503,464 kB, min available 367,364 kB, peak used 136,100 kB |
| OpenOCD per Site | CPU avg 72–74 % of one core (peak 97–100 %), RSS peak 15.8–16.6 MB, PSS peak 9.4–10.5 MB |
| E / P / V per Site (OpenOCD) | single ≈ 1.45 / 1.91 / 0.88 s; concurrent ≈ 1.46 / 1.93 / 0.96 s |
| 2 × 62,800 B E/P/V | serial 19.958 s → concurrent 12.613 s, **1.58×** (6,293 → 9,958 B/s) |

Root Site admission takes about 6 s and serializes on the supervisor lock; for a 0.5 s verify (step 6b) the SWD activity did not overlap.

## Known gaps

- Manager receipt reports `safe_off=None` / `SAFE_OFF_NOT_VERIFIED` for a definite FAIL whose Site Worker result has `safe_off: true`, making it non-retryable (conservative).
- ~~The Z2 installer still writes `max_concurrent_jobs: 1` on reinstall.~~ Corrected 2026-11-16: at WP-07 time only a fresh install (no `/etc/plasma/ppu.yaml`) wrote `1`; the proposed Site Count installer change makes fresh installs derive `max_concurrent_jobs` from their declared Site topology (1..8, default 8). An upgrade or reinstall, including Bootstrap Full-Copy, continues to keep the existing `ppu.yaml` byte for byte. During WP-07 the value returned to `1` only because the operator restored the backup after each failed step (`step4*-z2-config.log`). Regression tests: `test_ppu_z2_installer.py::test_upgrade_preserves_the_operator_concurrency_limit_byte_for_byte` and related tests.
- Two OpenOCD processes use about 1.5 of Z2's two cores; CPU will bound 4/8-Site scaling.
- Root admission latency (~6 s, serialized) dominates short operations.

## Files

- `result.json` — per-step Batch/Start/Job IDs, receipts, LA channel activity and `.sr` SHA-256s, final identity.
- `step5b-la-overlap.json` — overlap computation.
- `step5b-z2-resources.csv`, `step6b-z2-resources.csv` — raw 500 ms Z2 samples (CPU, RAM, per-Site OpenOCD PID/CPU/RSS/PSS; Site from `/proc/locks`).
- `perf-summary.txt` — derived performance numbers.
- `deploy-timeline.txt` — deployment, recovery (tx `4899bb12`), Root maintenance and engine switch timeline.

Raw LA captures (`.sr`, 40–50 s × 16 channels) remain in the SWPC evidence store `wp07-two-site-hil-20261115/`; only their SHA-256 values are recorded here.
