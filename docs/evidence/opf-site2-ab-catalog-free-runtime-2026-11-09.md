# PLASMA post-S5 — Catalog-free Runtime update and Site 2 Bundle A/B re-run

**Date:** 2026-11-09 (UTC run times 00:15–00:28)
**Gate:** owner Gate 1 for the post-S5 Z2 Site 2 A/B plan (G0–G3), following the read-only audit of main `a1b1c6f3b`.
**Dispatcher / CLI source:** merged main `c9a397b9b2c66699d92973d7f23c339ba21ef4ef` (every work order passed `--source-sha` with this value; `pr_number` 0).
**Installed Runtime source after G1:** `a1b1c6f3b1424ce38d1de7e597ef22d0ef4460f2` from trusted Z2 PS Release [push Run 42529614284](https://github.com/physicslu/plasma/actions/runs/42529614284), artifact `plasma-z2-ps-kit-0.2.1-a1b1c6f3b142`, kit tar.gz SHA256 `d40649202f58b54af4a046513eff4d607ba0299ee52740046b3601abdb57664c`.
**Enrolled target:** Z2 `192.168.2.99`, device `ppu-device-7ed4b30913a9bf6101da5a7a`, PPU `z2-hil`, Site 2 STM32F103C8T6.

All work orders were posted on [Issue #981](https://github.com/physicslu/plasma/issues/981) and executed through the existing `plasma-engineering-runtime-dispatch.yml` Path 2 `operator-cli` route on `SWPC-plasma-codex`. Every command ran once. No automatic retry.

## Sequence

| Step | Scope | Path 2 Run | Script / command | Result |
| --- | --- | --- | --- | --- |
| — | Admission denied, before execution | [42539221270](https://github.com/physicslu/plasma/actions/runs/42539221270) | G0a order with a `monitor_phase` field | `WORK_ORDER_OPERATOR_CLI_FIELDS_DENIED` in `development-authorize`; no SWPC/Z2 execution. Not a device result. |
| G0a | Read-only | [42539309965](https://github.com/physicslu/plasma/actions/runs/42539309965) | `plasma_program.py diagnose` (Bundle A) | `PASS`, `mutations=NOT_RUN`; Active `71e9a044…`; Site 2 idle |
| G0b | Read-only | [42539420991](https://github.com/physicslu/plasma/actions/runs/42539420991) | `plasma_site2_path2_preflight.py` | `NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS`; release `0.2.1-37a7823d8997`; no Site 2 seal/admission; `openocd_pids=[]`; Worker PID 925 |
| G0c | Read-only | [42539561065](https://github.com/physicslu/plasma/actions/runs/42539561065) | `plasma_site2_active_readonly_path2.py` | `readiness=PASS`, `opf_static=PASS`, Active `71e9a044…` |
| **G1** | Runtime write | [42539690632](https://github.com/physicslu/plasma/actions/runs/42539690632) | `plasma_program.py runtime-deploy` | `PASS`; Coordinator tx `4757517bb7b7439cbfbc19bae7e79c29`; `37a7823d8…` → `a1b1c6f3b…`; Active Set unchanged (A) |
| G1 post | Read-only | [42539988496](https://github.com/physicslu/plasma/actions/runs/42539988496) | `plasma_site2_path2_preflight.py` | No blockers; release `0.2.1-a1b1c6f3b142`; services restarted (Worker PID 18151); no seal; Site 2 idle |
| **G2** | DUT write | [42540091562](https://github.com/physicslu/plasma/actions/runs/42540091562) | `plasma_program.py flash` (Bundle A, already Active) | `PASS` |
| **G3** | Asset + DUT write | [42540204521](https://github.com/physicslu/plasma/actions/runs/42540204521) | `plasma_program.py run` (Bundle B) | `PASS`; B3 `ACTIVATED` |

## Physical receipts

| Scope | G2 Blue Pill CDC v0.1 Bundle A | G3 Blue Pill CDC v0.2 Bundle B |
| --- | --- | --- |
| Action | One `flash` (A already Active) | One `run`: B1/B2/B3 `activate`, then one `flash_cycle` |
| Canonical Bundle SHA256 | `71e9a044c7f45d0f6e608c2727961f6ada220b483225bd20b928bf06f289946a` | `387b9c8c08822a6d4edb8ac7904a71a6e3143b1714453a35778c372a7517764c` |
| Firmware package | `bluepill-cdc-fw-v01` | `bluepill-cdc-fw-v02` |
| Firmware SHA256 | `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d` | `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c` |
| Readback SHA256 | Equal to firmware SHA256 | Equal to firmware SHA256 |
| `bytes_verified` | 18,768 | 62,800 |
| Runtime Job ID | `job-20261109-002548-b072658b` | `job-20261109-002711-3e934f14` |
| B3 Transaction | N/A (already Active) | `1944c45f55e641f8b155b8fcfc56be76` |
| Job terminal state | `success` | `success` |
| Job submit count | 1 | 1 |
| SAFE_OFF | `true` | `true` |
| Automatic retry | `DISABLED` | `DISABLED` |

`plasma_program.py` grades `PASS` only when the Job result has `attempts == 1` and the Site is idle again after the Job.

## Identity that did not change across G1–G3

- FPGA image `z2-independent-swd-v5-d0add58c`, boot ID prefix `da39c09bd196`, `boot_match=true`, manager state `operating`. There was no FPGA reload.
- OpenOCD Engine: `plasma_swd` ABI 5, binary SHA256 `b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861`, admission SHA256 `3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b`, `VERIFIED`.
- Bootstrap service PID 6821. The Runtime services restarted in G1.

## State after this evidence

- Z2 Runtime: `a1b1c6f3b` (Catalog-free `ppu.pyz`; the PPU Gateway no longer serves `/api/devices/search`).
- **Active Set: Bundle B** (`387b9c8c…`). Returning to A needs a separate approved activation.

## Not verified / out of scope

- **C-3 Worker file SHA256 was not attested on the device.** The script that did this (`plasma_s2_postinstall_site2_path2.py`) is retired. The G1 kit's Worker source is byte-identical to `37a7823d8`, whose installed SHA256 `703d5756…` was attested in Run 42463456939. G2/G3 ran on the restarted Worker. This is an inference, not a measurement.
- A GET of PPU `/api/devices/search` expecting 404 was **NOT_RUN**.
- **The SWPC Control Station was not updated.** The Console B3 `mode` fix (#1365) was not live. Deploying C1 + C2 + #1365 was a separate owner decision.
  - *Correction (2026-11-09):* An earlier version of this line said the old Console/Manager was `37a7823d8` and relayed the IC Selector to this Z2. That was wrong. The SWPC `local-control-station` install evidence showed release `daf31bd94ed9` (#792). Its Manager registry held only `swpc-ppu` (the co-resident SWPC Gateway). No SWPC Manager had this Z2 enrolled. The old Console therefore relayed the Selector to the SWPC Gateway, not to this Z2. These runs did not use the Console.
  - *Follow-up (2026-11-09):* PR-L1 #1367 made the `local-control-station` Manager serve the Selector and the Bootstrap routes. It was deployed to SWPC at `22a88c989`. This Z2 was then enrolled as `z2`, passed Validate & Enable, and was paired using its existing Bootstrap token, which was not rotated. Read-only checks through the Console BFF passed. After those checks, Runtime was still `a1b1c6f3b`, the Active Set was still Bundle B, and Site 2 was idle. No B3, Job or Flash was sent.
- Dispatcher wrapper `physical_hil=NOT_VERIFIED` only means the wrapper does not grade device results. The `PLASMA_PROGRAM` receipts above are the evidence, and only for this exact Site, IC and firmware.
- These runs do not prove eight-Site concurrency, physical C-2 Package Provider, ST-LINK/PC, fault injection, cancellation, or sealed recovery.

**No new physical Job is implied or authorized by this evidence document.**
