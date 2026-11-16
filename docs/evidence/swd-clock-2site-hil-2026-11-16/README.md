# Bundle Profile SWD clock — Z2 2-Site concurrent HIL at 2 MHz and 5 MHz (2026-11-16)

**Verdict: PASS.** Z2 Site 1 and Site 2 programmed concurrently in one Manager Batch at a Bundle-Profile SWD clock of 2 MHz and, separately, 5 MHz (PR #1458). The PPU receipts report the requested clock, and an LA2016 capture measures exactly that SWCLK frequency on both Sites. Scope: two physical Sites of one PPU (`z2-hil`), STM32F103C8T6 Blue Pills, E/P/V. This is not a DUT electrical, signal-integrity or production qualification at these clocks.

## Deployed identity

| Item | Value |
|---|---|
| SWPC Control Station (Manager + Console) | `c633e1c5b0eb` (main `c633e1c5b`) |
| Z2 Runtime | `0.2.1-c633e1c5b0eb` (Route A tx `1707deaa…`) |
| Engine selection / OpenOCD | `665d0d95…` / `b8a7db67…` (unchanged) |
| Driver ABI | `plasma_swd:5`, FPGA not reloaded |
| `max_concurrent_jobs` | 2 |

## Method

The Manager has no API or UI field for the SWD clock: the clock comes only from the Programming Route's `flash_profile.transport_settings`. For each run:

1. A copy of the release Route root with the operations Route changed to add `transport_settings: {"protocol": "swd", "clock_hz": N}` and the profile version `1.0.0-swd<N>k` ([`routes-2000k`](routes-2000k/z2-site2-stm32f103c8t6-operations.json), [`routes-5000k`](routes-5000k/z2-site2-stm32f103c8t6-operations.json)).
2. The Manager was pointed at that root through a temporary systemd user drop-in (`PLASMA_PROGRAMMING_ROUTES_ROOT`) and restarted.
3. The matching Resource Set was activated on its own through Bootstrap B1–B3 with `fpga_load: false` ([`tools/activate_route.py`](tools/activate_route.py)). No DUT operation was involved. Without this step the Site that activates runs exclusively, and the two Sites would not overlap.
4. One canonical Batch (`POST /api/programming/batches`, targets `z2` Sites 1+2, E/P/V, retry 0) ran with a passive LA2016 capture armed before the single POST ([`tools/run_batch.py`](tools/run_batch.py)). The read-only plans confirmed Resource reuse and no FPGA load.

LA2016: 100 MHz, 1.4 V threshold, 30 s. Site 1 SWCLK/SWDIO = CH3/CH4; Site 2 = CH0/CH1. Analysis: [`tools/la_analyze.py`](tools/la_analyze.py) streams the capture and records rising-edge periods inside bursts (< 2 µs), the active span and the 1-ms windows in which both SWCLKs toggle.

## Results

| | 2 MHz | 5 MHz |
|---|---|---|
| Active Set (generation) | `108a90cc…` (23), Resource Set `4c7833d8…` | `8338ef40…` (24), Resource Set `6f1df96a…` |
| Batch / start | `d283829f…` / `2e5a05fd…` | `a4feeeff…` / `abc22c23…` |
| Image | v0.1 `8d3ffb02…`, 18,768 B | v0.2 `e691ab23…`, 62,800 B |
| Site 1 Job | `job-20261116-141708-bf829495` PASS, 8.26 s | `job-20261116-142035-061810e8` PASS, 11.68 s |
| Site 2 Job | `job-20261116-141708-bebf0f22` PASS, 8.80 s | `job-20261116-142035-beb9edfe` PASS, 11.06 s |
| Receipt `adapter_khz` / `swclk_half_period` / `swclk_nominal_hz` | 2000 / 25 / 2,000,000 | 5000 / 10 / 5,000,000 |
| LA SWCLK median (both Sites) | **2.000 MHz** (50 samples; p5–p95 2.000 MHz) | **5.000 MHz** (20 samples; p5–p95 5.000 MHz) |
| SWD active span, Site 1 / Site 2 | 10.683–12.162 s / 9.537–11.051 s | 9.419–13.976 s / 10.461–15.007 s |
| Concurrent SWD | 0.368 s, 165 1-ms windows | 3.516 s, 2,462 1-ms windows |

On every Job the readback matched the image SHA256 and `safe_off` was true, with one attempt each. The two images differ in size, so the durations are not a speed comparison between clocks. The 2 MHz overlap is short because each Site's SWD activity (~1.5 s) is shorter than the ~1 s offset caused by the serialized Root admission. In the 5 MHz Site 1 capture, 2 of 2.7 M periods were 2 samples (20 ns) long; these are isolated glitches and were not decoded further.

## Restore

The drop-in was removed and the Manager restarted on the release Routes. The original Active Set `957ac4e6…` was reactivated through B3 only (generation 25, tx `bbbb6f26…`, [`restore-active-957ac4e6.json`](restore-active-957ac4e6.json)), with no DUT operation. `plasmactl-local-control-station verify` passed and z2 was READY. Final DUT content: v0.2 on both Sites.

## Files

- `run-2000k/`, `run-5000k/`: `report.json`, plans, `batch-final.json`, `start-reconcile.json`, Manager runs, PPU Job receipts, `la-analysis.json`.
- `activate-2000k.json`, `activate-5000k.json`: activation-only B3 receipts.
- `summary.txt`: operator summary.
- `raw-capture-sha256.txt`: SHA256 of the raw `.sr` captures (7.1 MB / 9.3 MB, kept off-repo in the operator evidence store) and of both images.
