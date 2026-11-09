# PLASMA — Console-driven Bundle Programming, first physical runs on Z2 Site 2

**Date:** 2026-11-09 (UTC run times 04:24–04:41)
**Gate:** owner Gate 2 for [Console-driven Bundle Programming](../../development/console-bundle-programming-gate1-20261109.md), PR #1369.
**Control Station source:** merged main `2efb4543f46029cf475b9b41cbe795bc3d0db4cf`. Its post-merge CI was 12/12 success. It was deployed to the SWPC `local-control-station` profile with `plasmactl deploy local-control-station`; verify reported PASS.
**Target:** PPU alias `z2` → Z2 `192.168.2.99`, PPU `z2-hil`, device `ppu-device-7ed4b30913a9bf6101da5a7a`, Site 2 STM32F103C8T6.

Before these runs, `z2` was enrolled in the SWPC Manager, passed Validate & Enable, and was Bootstrap-paired. Pairing used the existing device token, which was not rotated.

The owner selected the Blue Pill CDC v0.1 image: SHA256 `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d`, 18,768 B. It is the committed file `docs/evidence/bluepill-z2-flash-2026-10-27/firmware/plasma-blue-pill-cdc.bin`.

Every run was submitted once. There was no automatic retry and no FPGA load.

## Owner verdict

- **Console-origin Site 2 flash: PASS.**
- This does **not** yet show the full human-UI path "Console builds the Bundle → B1/B2/B3 → Flash" on hardware. The owner's UI run (H2) took the *already-Active* path.
- The cache-miss path with B1/B2/B3 (H1) was driven through the same Console BFF requests, but **not** by a human in the UI.
- Nothing here implies multi-Site or eight-Site validation.

## Runs

| | H1 — activation required | H2 — already Active |
| --- | --- | --- |
| How submitted | The exact Console BFF requests (Prepare, then one Start), sent over HTTP on the SWPC loopback. **No human UI.** | **The owner used the real Console UI** in a browser: PPU → Platform → Bundle Programming |
| Manager run | `de00788710bab4ed522e4705955d80f1` | `92a6f9e068d0cc4b864e99e9053b3151` |
| Plan | Bundle `4d2837d483be46b960903c2ec3f2b2bb05fd309da96aa9e0ca2ae2758fad5467` (21,607 B). Active Set was Bundle B `387b9c8c…`, so activation was required. | The same Bundle `4d2837d4…`. The Active Set already matched; see `console-ui-h2-plan.txt`. |
| Steps | `PREFLIGHT` → `B1_UPLOAD` → `B2_ADMIT` → `B3_SUBMIT` → `B3_ACTIVATE` → `FLASH_CYCLE_SUBMIT` → `VERIFY_RECEIPT` | `PREFLIGHT` → `ACTIVE_SET: ALREADY_ACTIVE` → `FLASH_CYCLE_SUBMIT` → `VERIFY_RECEIPT` |
| B1 upload | `c103534f8bc1436e82caf16848510fbf` | not run |
| B2 admission | `285c0483c5b64f0d9c68a970cdcef8fe` | not run |
| B3 | `d929e9859df14acc91bff2b53043b51b`: `bundle.activate`, `fpga_load=false`, `succeeded` | not run |
| Job | `job-20261109-042428-113dd980` | `job-20261109-044035-b8cbd4da` |
| Manager `job_submission_count` | 1 | 1 |
| PPU `attempts` | **1**. `attempt_history` has 1 entry and `retry_exhausted=false`. | **1**. `attempt_history` has 1 entry and `retry_exhausted=false`. |
| Job state | `success` | `success` |
| `flash_cycle` result | `PASS` | `PASS` |
| Readback SHA256 | `8d3ffb02…` (equal to the image) | `8d3ffb02…` (equal to the image) |
| Verified bytes | 18,768 / 18,768 | 18,768 / 18,768 |
| SAFE_OFF | `true` | `true` (UI: `VERIFIED`) |
| OPF Active Set used by the Job | `4d2837d4…` | `4d2837d4…` |
| Adapter / config | `z2-abi5-swd-openocd5088`, `target/stm32f1x.cfg` | same |
| Manager outcome | `PASS` | `PASS` |

- **`attempts=1`** is now listed explicitly from the PPU Job receipts. It is also one of the checks behind `VERIFY_RECEIPT: PASS`, but the UI does not display it.
- **Three-way agreement for H2:** the owner's on-screen receipt, the PPU Gateway Job status and the Manager run journal agree.
- **After each run:** Site 2 returned to `idle` with no current or queued Job.

## Active Set reconciliation

The owner asked which transaction replaced Bundle B. Both Bootstrap captures below come from the PPU's own Bootstrap deployment record, read through the Manager.

| Generation | Active Set | Activated by | Source |
| --- | --- | --- | --- |
| 11 | Bundle A `71e9a044…` | earlier Path 2 operation | `asset_activation_previous` in `bootstrap-status-before.json` |
| 12 | Bundle B `387b9c8c…` | B3 `1944c45f55e641f8b155b8fcfc56be76` (G3, `plasma_program.py run`, Path 2) | `bootstrap-status-before.json`, captured before any Console programming run |
| 13 | Console Bundle `4d2837d4…` | B3 `d929e9859df14acc91bff2b53043b51b`; B2 `285c0483…`; upload `c103534f…` | `bootstrap-status-after.json` (`asset_activation_previous` = generation 12, `387b9c8c…`) |

- The B3 that replaced Bundle B is H1's B3, transaction `d929e985…`, Manager run `de007887…`.
  - Its owner authorization is `bundle.activate`, bound to subject `4d2837d4…`, B2 transaction `285c0483…` and the paired device.
  - These IDs match H1's Manager journal steps.
- Generations are contiguous (12 → 13), so no other activation happened in between.
- H2 did not activate anything: the Bootstrap's last deployment is still `d929e985…`.

## Resulting device state

| Field | Value |
| --- | --- |
| Active Set | `4d2837d4…`, generation 13. Returning to Bundle B needs a separate approved activation. |
| Runtime | `0.2.1-a1b1c6f3b142` (`a1b1c6f3b1424ce38d1de7e597ef22d0ef4460f2`, `runtime_active`), unchanged |
| FPGA | `pl_compatibility=not_managed`, `pl_qualification=not_qualified`. No FPGA load was requested (`fpga_load.requested=false`). Bootstrap capability `fpga_update=false`. |

## Files

| File | Content |
| --- | --- |
| `console-ui-h2-plan.txt`, `console-ui-h2-result.txt` | Owner's Console UI screens (H2), as pasted by the owner |
| `h1-plan.json` | H1 Prepare response: route, Bundle, Active Set and steps |
| `manager-run-journal.json` | Manager journal records for both runs |
| `ppu-job-job-20261109-042428-113dd980.json` | H1 PPU Job receipt |
| `ppu-job-job-20261109-044035-b8cbd4da.json` | H2 PPU Job receipt |
| `bootstrap-status-before.json` | Bootstrap status before the Console runs: Bundle B generation 12 |
| `bootstrap-status-after.json` | Bootstrap status after the Console runs: B3 `d929e985…`, generation 13 |

All captures contain identities, digests and receipts only; no credential or token values.

## Not verified / out of scope

- **Human-UI cache-miss path not shown on hardware.** H1 used the same BFF requests the Console sends, but no human operated the UI for it. A separate owner-run cache miss would close this gap; it needs separate authorization.
- **No independent check that the firmware runs.** Nothing outside the receipt confirmed the v0.1 firmware running on the Blue Pill, such as USB CDC enumeration. The receipt proves exact readback only.
- **Failure paths were not tested on hardware.** OUTCOME_UNKNOWN, SAFE_OFF failure, B3 failure, timeout and duplicate submission are covered by Host-only tests (PR #1369) only.
- **Packaged runtimes were not tested on hardware.** The macOS and Windows packaged Control Station runtimes were not exercised physically.
- **Console write authorization on this profile.** The SWPC `local-control-station` profile uses the default `mutable` registry policy, so the BFF maintenance capability is not enforced. Console write access relies on the loopback binding and on any upstream protection of a tunnel exposing it.
- **Scope of this evidence.** It covers only this exact Site, IC and image. It does not prove multi-Site or eight-Site concurrency, other ICs or Providers, or FPGA-bearing Bundles.

**No further physical Job is implied or authorized by this evidence document.**
