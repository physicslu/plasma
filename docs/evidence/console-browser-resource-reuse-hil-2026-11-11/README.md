# Console Browser Resource Reuse on Site 2 — evidence for `job-20261111-002355-13e83290`

**Date:** 2026-11-11, Job at UTC 00:23:55–00:24:04; evidence collected read-only at UTC 00:28–00:33.
**Result:** `PASS` in the Manager run record and in the PPU Job record. Every identity the two records share is equal.
**Authorization:** owner Gate 1 approval for read-only evidence collection. Nothing was flashed, deployed, restarted or loaded for this evidence.
**Origin of the run:** the owner reports starting it from the Console in a browser. The records here cannot confirm that; see [NOT_VERIFIED.md](NOT_VERIFIED.md).
**Target:** Manager alias `z2`, PPU `z2-hil`, Site 2, STM32F103C8T6, image Blue Pill CDC v0.1 (`plasma-blue-pill-cdc.bin`, 18,768 bytes).

## Acceptance

| Check | Manager (SWPC) | PPU (Z2 Gateway) | Result |
| --- | --- | --- | --- |
| Run / Job | run `48ed5e17a6555c269afc6808d4f266f6`, `finished`, outcome `PASS` | `job-20261111-002355-13e83290`, `success` | Same Job ID |
| Resource Set SHA256 | `39e4bf851bdc0128cfbfd502532d235d05dd0423e4e9ada9c865260f18f5e9a7` (plan, receipt expected and observed) | Same (Job Binding; `active_resources` `VERIFIED` after the Job) | Equal |
| Job Binding SHA256 | `10bbf176c63982fb8f4d9bd792f5db2322b47bc1d98fac95cd2ccc63e8484ef0` (plan, receipt expected and observed) | Same (Job Binding and `flash_cycle` result) | Equal |
| Image SHA256 | `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d` | Same | Equal |
| Image Asset SHA256 | `80d6d142858934c421cd0b2c716a3a5960d5269cb7e820694b0767c82de74568` | Same | Equal |
| Readback SHA256 | `8d3ffb02…841d` | `8d3ffb02…841d` | Equal to the image SHA256 |
| Job Binding range | `0x08000000`, 18,768 B | Same | Equal |
| Erase | `0x08000000`, 19,456 B (expected and observed) | Same | Equal |
| Write / verify / readback address | `0x08000000` | Same | Equal |
| Bytes verified | 18,768 | 18,768 | Equal |
| Attempts | 1; `job_submission_count` 1; `auto_retry` `DISABLED` | `attempts` 1, one entry in `attempt_history`, `retry_exhausted` false | One attempt |
| SAFE_OFF | `safe_off` true | `safe_off` true | — |
| Receipt | `VERIFY_RECEIPT` `PASS`, `failed_checks` empty | `openocd_rc` 0, result `PASS` | — |

The Manager record was read twice: from the journal file and from the Manager `GET …/programming/runs/{run_id}` route. The two are identical. The Job record was read from the Z2 Gateway directly and through the Console BFF relay; the two responses are byte-identical.

## Resource Reuse, B1 / B2 / B3 and FPGA

- Run steps are exactly `PREFLIGHT`, `RESOURCE_REUSE: PPU_VERIFIED`, `FLASH_CYCLE_SUBMIT`, `VERIFY_RECEIPT`. There is no `B1_UPLOAD`, `B2_ADMIT`, `B3_SUBMIT` or `B3_ACTIVATE` step. The run's `activation` record is empty; the plan has `resource.reuse` true, `activation_required` false and `fpga_load` false.
- The Z2 Bootstrap HTTP log for 00:23:40–00:24:20Z has only `GET /v1/status`, `GET /v1/auth/challenge` and `GET /v1/assets`. There is no POST, so no upload, admission or activation request reached Bootstrap in the Job window.
- `z2-snapshot.txt` (00:29:46Z) equals the snapshot of 2026-11-10T14:14:30Z from the [previous evidence](../p0-control-station-ofe1b-resource-reuse-2026-11-10/README.md) except for the timestamp and the Job list. Unchanged: boot ID, main PID and start time of the four services, `active.json` (generation 15), upload count 114, SHA256 of `deployment-api.json` and `deployment.json` with their transaction IDs, SHA256 and mtime (2026-11-03) of `fpga-image-identity.json`, FPGA manager `operating`.
- Between the two snapshots, the only path modified under the Bootstrap state, Asset, control-plane, `/etc/plasma` and `/run/plasma-z2-swd05` trees is the `/run/plasma-z2-swd05` directory itself, at 00:24:03Z (the end of the Job).

**FPGA reload: not independently verified for this Job.** No snapshot was taken immediately before it. The points above support "no reload", and nothing collected contradicts it.

## Duplicate submission, OUTCOME_UNKNOWN, recovery, seal

- The Manager journal has six runs. One was created on 2026-11-11 and one contains this Job ID: the same run. All six ended `PASS`; the journal contains no `OUTCOME_UNKNOWN`, recovery or seal text (`manager-journal-summary.txt`).
- On Z2 the only Job directory newer than `job-20261110-141359-ae092c6f` is this Job.
- Run `reason` is null; `acknowledged` is false, which is the stored value for a `PASS` run that needed no operator acknowledgement.
- Controller generation 2, mode and state `NORMAL`; Bootstrap `bootstrap_ready`; last deployment record `succeeded` (the Bundle B activation of 2026-11-10); pairing `device_match` and `device_authenticated` true.
- Site 2 after the Job: `idle`, no current Job, zero queued, PPU execution not busy, no lease owner.
- Files named `*recover*` on Z2 are dated 2026-11-02 to 2026-11-10 and predate this Job. No file named `*seal*`, `*outcome*` or `*quarantine*` was found. The Site Worker's own seal state was not queried.

## Source versions

| Layer | Version | Source |
| --- | --- | --- |
| Console / BFF and Manager (SWPC) | release `728e55e529b5`, git `728e55e529b58ea22d736553c50bee237a9962f4`; both services started 2026-11-10T14:11:35–36Z, `NRestarts` 0 | `control-station-release-identity.txt` |
| Z2 Runtime (Gateway, Site Worker) | `0.2.1-6cf7057ce546`, git `6cf7057ce5460a8f40207840ebd4d85ef144cdb8`, `runtime_active` | `manager-z2-bootstrap-status.json`, `z2-snapshot.txt` |
| Z2 Bootstrap | version `0.1.0`, API `1`; `control-plane.json` SHA256 `609d4308…b8fa`, unchanged since 2026-11-10 | Same |
| Driver / adapter | `plasma_swd:5`, `z2-abi5-swd-openocd5088`, OpenOCD SHA256 `b8a7db67…f861` | Job record |

`6cf7057ce` → `728e55e52` changes `docs/` only. `728e55e52` → main `c106fd791` changes `docs/` and one Playwright spec. The deployed code on both hosts is therefore the code of current main. The JavaScript the browser actually loaded was not captured.

## Limits of this evidence

- Collected after the fact. The Console display values come from the owner's report; no screenshot exists.
- Browser origin, raw OpenOCD output, an independent Flash dump and the G13 request signature are not captured. The full list is in [NOT_VERIFIED.md](NOT_VERIFIED.md).
- The Playwright test of PR #1390 runs against a mocked Manager and is not part of this evidence.
- One Site, one IC, one Job.

## Collection notes

- All HTTP requests were GET. Z2 files were read over SSH with read-only commands.
- A first Z2 command included a recursive `grep` over `/var/log` and exceeded the SSH time limit. Its leftover `grep` and shell were stopped by PID; no PLASMA process was signalled. The check was dropped and the remaining commands were re-run without it.
- No credential, token, cookie or key content was read into the evidence. Home-directory paths are written as `~`.

## Files

- `TIMELINE.txt` — UTC timeline with the source of each line.
- `manager-run-48ed5e17a6555c269afc6808d4f266f6.json` — the run record from the Manager journal, re-indented with sorted keys. `manager-run-api-response.json` — the same record as returned by the Manager, unmodified.
- `manager-run-receipt.json` — the `receipt` object of the run record.
- `manager-journal-summary.txt` — journal SHA256 and one line per run.
- `ppu-job-20261111-002355-13e83290.json` — Z2 Gateway `GET /api/status?job=…`, unmodified.
- `site2-status.json` — Z2 Gateway `GET /api/status?site=2`, unmodified. `z2-gateway-health-ready.json` — Gateway readiness.
- `active-resource-bundle-identity.txt` — Resource Set, Active Asset Set, Bundle, Image and Job Binding identities with the raw file each comes from.
- `manager-z2-bootstrap-status.json` — Manager → Z2 Bootstrap status (Runtime and Bootstrap release identity, controller, last deployment); `upstream_status` 200.
- `manager-registry.json` — Manager registry (aliases and endpoints).
- `control-station-release-identity.txt` — SWPC installed release, service state, source comparison.
- `z2-snapshot.txt`, `z2-job-scope.txt`, `z2-journal-job-window.txt` — read-only Z2 observations.
- `swpc-service-journal-0020-0025.txt` — SWPC Manager and Console service log, 00:20–00:25Z.
- `NOT_VERIFIED.md` — NOT_VERIFIED / NOT_CAPTURED list.
- `SHA256SUMS` — SHA256 of every other file in this directory.
