# PLASMA OPF P0 — SWPC Control Station update and OFE-1B Resource Reuse on Site 2

**Date:** 2026-11-10 (UTC 14:10–14:15)
**Authorization:** owner direct-execution approval for P0-A (SWPC Control Station update) and P0-B (OFE-1B Resource Reuse / Job Binding on the Site 2 test DUT). No Z2 deployment, Z2 service restart, Z2 reboot, FPGA reload, Golden Restore or PR merge was authorized or performed.
**Source:** merged main `728e55e529b58ea22d736553c50bee237a9962f4`. Its code is identical to `6cf7057ce5460a8f40207840ebd4d85ef144cdb8` (the Runtime already on Z2); the commits in between change `docs/` only.
**Enrolled target:** Z2 `192.168.2.99`, device `ppu-device-7ed4b30913a9bf6101da5a7a`, PPU `z2-hil`, Site 2 STM32F103C8T6, Manager alias `z2`.
**Path:** Console BFF (`127.0.0.1:18190`) → Manager (`127.0.0.1:18280`) → Z2 Gateway → Runtime → Site Worker v3 (C-3) → OpenOCD. Requests were sent to the BFF over HTTP by a script, not through the browser UI. Every write ran once. No automatic retry, no failure, no fix PR.

## Sequence

| Step | Scope | Action | Result |
| --- | --- | --- | --- |
| P | Read-only | Z2 snapshot, Gateway `/api/status?site=2`, Manager run journal | Site 2 idle, lease free, no Job, Active `387b9c8c…` generation 15, controller generation 2 `NORMAL`; three earlier Manager runs all `PASS` |
| **A1** | SWPC write | `scripts/plasmactl deploy local-control-station` from a worktree at `728e55e52` | rc 0; `082f018941b5` → `728e55e529b5` |
| A2 | Read-only | Manager registry, Manager → Z2 Bootstrap status, BFF → Z2 Gateway | All HTTP 200; `paired`, `device_match`, `device_authenticated` true |
| B2 | Read-only | Plan for Firmware A, not run | `reuse` true, `activation_required` false |
| **B3** | DUT write | One plan and one run, Firmware A | `PASS` |
| **B5** | DUT write | One plan and one run, Firmware B | `PASS` |
| B9 | Read-only | Z2 snapshot, Gateway Job records | Snapshot equal to P except the Job list |

## P0-A — SWPC Control Station

- `control-station-deploy-log.txt` ends with `PASS: local Control Station Console + Manager are healthy on loopback` and `deployment complete: 728e55e529b5`. The script restarted `plasma-local-manager.service` and `plasma-control-station.service` and nothing else.
- Previous release `082f018941b5` is still on disk as the rollback target (`swpc-state-after.txt`).
- `registry.json` and `bootstrap-credentials.json` have the same SHA256 before the deploy (`swpc-state-before.sha256`) and after the HIL (`swpc-state-after.txt`). Both services are `active` with `NRestarts=0`, started 14:11:35Z and 14:11:36Z.
- `manager-z2-bootstrap-status.txt`: pairing `controller_generation` 2, controller `253e8a1f418dee474d5c2d2f27197d3f`, `device_authenticated` true; Bootstrap `bootstrap_ready`.
- `bff-z2-gateway-health-ready.txt` and `bff-z2-gateway-status-site2.txt`: the Console BFF relays to the Z2 Gateway through the Manager (HTTP 200).
- Host-only tests before the deploy: 269 passed (Manager Bootstrap, Bundle programming workflow and REST, OFE-1B Resource Reuse, Resource / Image identity). The test output was not saved as a file.

## Z2 version consistency

From `z2-snapshot-before.txt` and the read-only checks before A1:

- Runtime `/opt/plasma/releases/0.2.1-6cf7057ce546`.
- `/opt/plasma/bootstrap/control-plane.json` SHA256 `609d4308…b8fa`, unchanged across the run. Its content (release `6cf7057ce`, `plasma.ppu.site-worker.v3`, `ppu_site_adapter_abi5.py`, `plasma_swd` ABI `[5]`) was read on screen and is recorded in the [Full-Copy deployment evidence](../full-copy-deploy-site2-ab-2026-11-10/README.md); a copy was not saved here.
- Both Job records report `opf_driver_abi` `plasma_swd:5` and adapter `z2-abi5-swd-openocd5088`.

## P0-B — Resource Reuse and Job Binding

The PPU reported its own Resource identity as `VERIFIED`, and the Manager reused it. Both plans list the steps `RESOURCE_REUSE`, `FLASH_CYCLE_JOB`, `VERIFY_RECEIPT`. Both runs have an empty `activation` record and no B1, B2 or B3 step.

| Scope | Firmware A (Blue Pill CDC v0.1) | Firmware B (Blue Pill CDC v0.2) |
| --- | --- | --- |
| Manager run | `2055adfc72b8eefa23fe3dc71197ee83` | `6cfc26ebba9f394b01d621d51ae5daea` |
| Runtime Job ID | `job-20261110-141332-5efbd172` | `job-20261110-141359-ae092c6f` |
| Resource Set SHA256 | `39e4bf851bdc0128cfbfd502532d235d05dd0423e4e9ada9c865260f18f5e9a7` | Same |
| Active Asset Set | `387b9c8c08822a6d4edb8ac7904a71a6e3143b1714453a35778c372a7517764c`, generation 15 | Same |
| Firmware SHA256 | `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d` | `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c` |
| Image Asset SHA256 | `80d6d142858934c421cd0b2c716a3a5960d5269cb7e820694b0767c82de74568` | `200eb75daeff3dc79b148bb2bfd05956477c7e3d63a1bfa1ebfe4ad6772b6453` |
| Job Binding SHA256 | `10bbf176c63982fb8f4d9bd792f5db2322b47bc1d98fac95cd2ccc63e8484ef0` | `83bb4aec02bea9d44ef1a8276f84c46d243f43e6badefae0176c17f553805af7` |
| Job Binding range | `0x08000000`, 18,768 B | `0x08000000`, 62,800 B |
| Erase range | `0x08000000`, 19,456 B | `0x08000000`, 63,488 B |
| Write / verify / readback address | `0x08000000` | `0x08000000` |
| Readback SHA256 | Equal to firmware SHA256 | Equal to firmware SHA256 |
| `bytes_verified` | 18,768 | 62,800 |
| SAFE_OFF | `true` | `true` |
| Job terminal state | `success`, `attempts` 1 | `success`, `attempts` 1 |
| Job submit count | 1 | 1 |
| Automatic retry | `DISABLED` | `DISABLED` |
| Manager receipt | `PASS`, `failed_checks` empty | `PASS`, `failed_checks` empty |

In each Manager receipt the expected and PPU-observed values are equal for the Resource Set, Job Binding, Image Asset and Flash range. The Gateway Job records carry the same Binding, with `openocd_rc` 0, 2000 kHz, provider `openocd-platform-reference` and profile `stm32f103c8t6-site2`.

## Z2 state that did not change

`z2-snapshot-before.txt` (14:12:58Z) and `z2-snapshot-after.txt` differ only in the timestamp line and the list of the four newest Job directories. Identical in both:

- `active.json` (Bundle B, generation 15) and the Bootstrap upload count (114): no B1 upload.
- SHA256 of `deployment-api.json` and `deployment.json`, and the transaction IDs `bddf7fe6…` / `9b2e8c35…`: no B2 or B3.
- Main PID and start time of `plasma-bootstrap`, `plasma-web`, `plasma-server` and `plasma-site-worker`: no service restart, no Provider reinstall.
- `/run/plasma-z2-swd05/fpga-image-identity.json` SHA256 `f6688d8e…842f` and its mtime; FPGA manager `operating`: no FPGA reload.
- `/etc/machine-id`, controller record (generation 2), `site-worker-engine.json`, `control-plane.json`.
- No OpenOCD process; boot ID unchanged.

After Firmware B, `site2-status-after-firmware-b.json` shows Site 2 `idle`, no current Job, zero queued Jobs, lease free, and `active_resources` still `VERIFIED` with the same Resource Set.

## Not verified / out of scope

- **Job Binding at a non-base address: BLOCKED, not run.** No Flash page of the DUT is proven destructible, and the Manager plan takes the range of an Image Operation from the Image (no address input).
- **G13 request signature: NOT_VERIFIED directly.** No Gateway admission log or signed request was captured. The evidence is that both `POST /api/jobs` were accepted with HTTP 202 under controller generation 2.
- **OpenOCD output lines: NOT_VERIFIED.** The erase, write and verify ranges come from the Job result fields; the Site Worker journal and raw OpenOCD log were not copied.
- **Readback was not dumped independently.** `PASS` rests on the Job's `readback_sha256` being equal to the firmware SHA256, with `bytes_verified` equal to the image size.
- **Site seal: not listed directly.** The snapshot search found no seal file under the Runtime and Bootstrap state directories, and the Gateway reports Site 2 idle; the Site Worker's own seal directory was not listed by name.
- **`control-plane.json` content and the host-only test output** were observed in the session but not saved as files.
- **Browser UI not used.** The Console BFF was driven over HTTP.
- **DUT electrical state was not inspected physically.**
- One Site and one IC only. This is not an 8-Site concurrency result.

## State after this evidence

- SWPC Control Station `728e55e529b5`; Z2 unchanged at `6cf7057ce`.
- Active Set still Bundle B (`387b9c8c…`), generation 15. The DUT now holds Firmware B.

## Files

- `timeline.txt` — UTC timeline.
- `control-station-deploy-log.txt` — full output of the deploy command.
- `swpc-state-before.sha256`, `swpc-state-after.txt` — SWPC state file SHA256, installed release and service state.
- `manager-registry.txt`, `manager-z2-bootstrap-status.txt`, `bff-z2-gateway-health-ready.txt`, `bff-z2-gateway-status-site2.txt` — responses with the HTTP status on the last line.
- `z2-snapshot-before.txt`, `z2-snapshot-after.txt` — read-only Z2 snapshots.
- `firmware-a-plan-only.txt` — the plan that was inspected and left to expire.
- `firmware-a-plan.json`, `firmware-a-run-start.json`, `firmware-a-run-final.json`, `firmware-a-run-console.txt` and the `firmware-b-*` equivalents — Manager plan, run records and script output.
- `ppu-job-20261110-141332-5efbd172.json`, `ppu-job-20261110-141359-ae092c6f.json` — Gateway Job records.
- `site2-status-after-firmware-a.json`, `site2-status-after-firmware-b.json` — Gateway Site status.
- `images.sha256` — SHA256 of the two images; the binaries are not committed.
