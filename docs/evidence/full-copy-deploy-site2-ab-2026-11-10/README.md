# PLASMA Full-Copy deployment to Z2 and Site 2 Bundle A/B real Flash

**Date:** 2026-11-10 (UTC 13:19–13:28)
**Authorization:** owner direct-execution approval for the SWPC → PYNQ-Z2 Full-Copy Runtime deployment, extended to one Site 2 Erase / Program / Readback Verify per Bundle (A and B). No Z2 reboot, FPGA reload, Golden Restore or PR merge was authorized or performed.
**Deployed source:** merged main `6cf7057ce5460a8f40207840ebd4d85ef144cdb8` (PR #1386, PR-B Full-Copy).
**Release Kit:** trusted Z2 PS Release [push Run 42820831367](https://github.com/physicslu/plasma/actions/runs/42820831367), artifact `plasma-z2-ps-kit-0.2.1-6cf7057ce546`, kit tar.gz SHA256 `c8a1b264623444b0ffea1ab040a6d9864581d7685057e5ffeaab81cd63780955`.
**Release archive:** `plasma-ppu-0.2.1-6cf7057ce546-linux-armv7l.tar.gz`, SHA256 `6c03aa819021013a5d5379d1065a2251320684fe4c18e777d767ed47b4430ce3`.
**Enrolled target:** Z2 `192.168.2.99`, device `ppu-device-7ed4b30913a9bf6101da5a7a`, PPU `z2-hil`, Site 2 STM32F103C8T6.
**CLI source:** `scripts/plasma_program.py` from a worktree at the same main `6cf7057ce`, run locally on SWPC (not through the Path 2 dispatcher). Every write command ran once. No automatic retry, no failure, no fix PR.

## Sequence

| Step | Scope | Command | Result |
| --- | --- | --- | --- |
| P | Read-only | Z2 state snapshot, Gateway status, `plasma_program.py diagnose` | Journals terminal (`reconciled` / `runtime_active`), no Job, lease free, no Site seal, engine `plasma_swd` ABI 5, Active `4d2837d4…` generation 13; `diagnose` `PASS` |
| **G2** | Runtime + control-plane write | `plasma_program.py runtime-deploy` | `PASS`; API tx `db2b7948f36f40168cffa4159fcd3e38` `succeeded`; Coordinator tx `f3696b53-d1c4-44c1-8810-5d9c1deb44fa` `runtime_active`; `7e90f95bc…` → `6cf7057ce…` |
| G3 | Read-only | Installed tree against the release manifest | 39 / 39 control-plane files equal the manifest SHA256; `control-plane.json` written |
| **R** | Service restart | `systemctl restart plasma-bootstrap.service` (only this unit) | PID 26277 → 9956, active |
| A | Read-only | Before / after snapshot diff, running processes, `diagnose` | Identity and state files identical; `diagnose` `PASS` |
| **H1** | Asset + DUT write | `plasma_program.py run` (Bundle A) | `PASS`; B3 `ACTIVATED` |
| **H2** | Asset + DUT write | `plasma_program.py run` (Bundle B) | `PASS`; B3 `ACTIVATED` |

## Full-Copy release identity

`/opt/plasma/bootstrap/control-plane.json` after G2 (see `post-deploy-control-plane.txt`):

- `release_id` `0.2.1-6cf7057ce546`, `release_git_sha` `6cf7057ce5460a8f40207840ebd4d85ef144cdb8`
- `release_archive_sha256` `6c03aa81…0ce3`, `control_plane_manifest_sha256` `df935e71a435354cbe5bf7349aa8c305cb22505bb231df0a09fc9c90b8610807`
- `site_worker_protocol` `plasma.ppu.site-worker.v3`; Site Adapter `ppu_site_adapter_abi5.py`, `plasma_swd` ABI `[5]`

Running processes after G2 and R: Runtime Server and Gateway from `/opt/plasma/releases/0.2.1-6cf7057ce546`; Site Worker and Package Control restarted by the transaction at 13:23:37Z on the copied tree; Bootstrap service restarted at 13:25:11Z. No `CONTROL_PLANE_RELEASE_*` or `SITE_WORKER_PROTOCOL_MISMATCH` in the service journals.

The restart of `plasma-bootstrap.service` was decided from the service start time (09:26 CST, before the copy). The `bootstrap_service_restart_required` result field itself was not read back.

## Physical receipts

| Scope | H1 Blue Pill CDC v0.1 Bundle A | H2 Blue Pill CDC v0.2 Bundle B |
| --- | --- | --- |
| Action | One `run`: B1/B2/B3 `activate` (`fpga_load=false`), then one `flash_cycle` | Same |
| Canonical Bundle SHA256 | `71e9a044c7f45d0f6e608c2727961f6ada220b483225bd20b928bf06f289946a` | `387b9c8c08822a6d4edb8ac7904a71a6e3143b1714453a35778c372a7517764c` |
| Firmware package | `bluepill-cdc-fw-v01` | `bluepill-cdc-fw-v02` |
| Firmware SHA256 | `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d` | `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c` |
| Readback SHA256 | Equal to firmware SHA256 | Equal to firmware SHA256 |
| `bytes_verified` | 18,768 | 62,800 |
| Erase range | `0x08000000`, 19,456 B | `0x08000000`, 63,488 B |
| Write / verify / readback address | `0x08000000` | `0x08000000` |
| Runtime Job ID | `job-20261110-132653-11211d38` | `job-20261110-132728-d4f178e4` |
| B3 Transaction | `3d1f9cb641134eec9365b6a9e8d9d52b` | `bddf7fe6e8c44d5987481a723baafaac` |
| Job terminal state | `success`, `attempts` 1 | `success`, `attempts` 1 |
| Job submit count | 1 | 1 |
| SAFE_OFF | `true` | `true` |
| Automatic retry | `DISABLED` | `DISABLED` |

Both Jobs report adapter `z2-abi5-swd-openocd5088`, `opf_driver_abi` `plasma_swd:5`, 2000 kHz, `openocd_rc` 0, profile package `stm32f103c8t6-site2`, provider `openocd-platform-reference`.

## Identity that did not change

SHA256 of each file was taken before G2 and after R, and the two lists are identical:

- `/etc/machine-id`, `/etc/plasma/ppu.yaml`, `/etc/plasma/site-worker-engine.json`, Bundle authority, Package target and Package actions configuration.
- Bootstrap controller record, ledger and pending files (controller generation 2).
- Both privileged FPGA root trees (current and previous).
- `/run/plasma-z2-swd05/fpga-image-identity.json` (`f6688d8e…842f`), also unchanged after H2. FPGA manager state `operating` throughout. There was no FPGA reload.
- OpenOCD Engine: `plasma_swd` ABI 5, binary SHA256 `b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861`.

## State after this evidence

- Z2 Runtime, Bootstrap, Site Worker v3 and Adapter: `6cf7057ce`, bound by `control-plane.json`.
- Bootstrap deployment API record `succeeded`; Site 2 idle; no Site seal; no OpenOCD process.
- **Active Set: Bundle B** (`387b9c8c…`), generation 15. It was `4d2837d4…` generation 13 before H1.

## Not verified / out of scope

- **Readback was not dumped independently.** `PASS` rests on the Job's reported `readback_sha256` being equal to the firmware SHA256, with `bytes_verified` equal to the image size.
- **No standalone Probe report.** Probe is a step inside `flash_cycle`.
- **DUT electrical state was not inspected physically.** The run relied on the unchanged FPGA identity, the matching engine ABI, an idle Site and no seal.
- **The SWPC Control Station was not updated** (still `082f01894`). The Console / Manager path against this Runtime is NOT_RUN.
- **Job Binding address and Resource Reuse (OFE-1B) on hardware: NOT_RUN.** Both Jobs used the Bundle-reference path (`job_binding_sha256` null).
- One Site and one IC only. This is not an 8-Site concurrency result.

## Files

- `TIMELINE.md` — UTC timeline of the write steps.
- `runtime-deploy-receipt.txt`, `bundle-a-run-receipt.txt`, `bundle-b-run-receipt.txt` — `PLASMA_PROGRAM=` receipts.
- `post-deploy-control-plane.txt` — coordinator journal summary, API state, `control-plane.json`, manifest comparison.
- `ppu-job-job-20261110-132653-11211d38.json`, `ppu-job-job-20261110-132728-d4f178e4.json` — Gateway Job records.
