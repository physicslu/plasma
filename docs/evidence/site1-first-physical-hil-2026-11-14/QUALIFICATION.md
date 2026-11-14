# Site 1 first physical HIL, 2026-11-14

## Owner-requested retest after wiring confirmation

The owner confirmed the physical connections and authorized a direct retest. Manager preflight observed Site 1 and Site 2 idle, no active Job, the previous Start terminal `FAIL`, LA2016 USB available, the same qualified Site 1 Route and Resource Set, generation 21 reusable, and no FPGA reload required. A fresh Manager-issued Start ID was used; no automatic retry was configured.

- Start `7b7527c74304ca59efddcd53dd182b3a`; Batch `29ae16dca64f6018db50e2d6f80329d0`; Run `7ddf10e9e90db6f138ac7a382c1a5ffa`; Job `job-20261114-105004-f42cf854`. Manager admitted the Job; Batch result `FAIL` with `SAFE_OFF_NOT_VERIFIED` in the Manager receipt.
- The Job again failed before Erase: `OPENOCD_ERASE_FAILED`, OpenOCD RC 1, no Erase/Program/Verify evidence and no IC readback SHA256. The raw OpenOCD stdout reports `PS_OWNER_ATTACHED site 1`, clock speed 2000 kHz, 330 `plasma_swd: run rc=-4 ... status=5 ack=7` errors, then `Error connecting DP: cannot read IDR`. FPGA RTL defines status 5 as `ST_BAD_ACK`; ACK 7 is not a valid SWD ACK.
- Z2 OpenOCD evidence [`site1-g7ln1e66.json`](site1-g7ln1e66.json) records `safe_off_verified: true` and admission revoked; stdout ends `SAFE_OFF_MODE_OFF_VERIFIED`. Its SHA256 is `468490e81fe7b499f274a8f0c8f61e293f81e6c8df309df72b97debdafdbac7c`. The Manager receipt still reports `safe_off: null`; this discrepancy is unresolved.
- LA2016 [`site1-epv-retest.sr`](site1-epv-retest.sr) captured 600,002,496 samples at 20 MHz over 30.0001248 seconds, SHA256 `c7fd1409af0fde0006b9fffcb4f6e64d4304f4b4857f2ab8de28143ac76bd313`. CH3 SWCLK and CH4 SWDIO had zero transitions; CH5 stayed digital high. The 30-second record spanned the Job. SWCLK frequency, direction, and SWD decode remain unverified.
- Final Start reconciliation: `TERMINAL_CONFIRMED/FAIL`. Site 1 and Site 2 are idle, active Job count 0. No further Flash was submitted after the failed retest.
- Current physical blocker: Site 1 SWD host transaction cannot read target DPIDR, and no SWCLK/SWDIO transition was observed at the LA2016 probe points. The static XDC, block design and implemented I/O audit all specify Site 1 JA1/Y18 SWCLK and JA2/Y19 SWDIO; these documents do not prove a live waveform at the fixture.

Retest evidence: [`batch-retest-result.json`](batch-retest-result.json), [`start-retest-reconciliation.json`](start-retest-reconciliation.json), [`site-retest-status.json`](site-retest-status.json), [`site1-g7ln1e66.stdout`](site1-g7ln1e66.stdout), [`site1-epv-retest-analysis.json`](site1-epv-retest-analysis.json), [`run-retest-report.json`](run-retest-report.json).

## Verdict

| Check | Observed verdict |
| --- | --- |
| Site 1 programming | **SITE1_PROGRAMMING_FAIL** |
| LA2016 raw capture | **LA2016_CAPTURE_PASS** |
| SWD protocol decode | **SWD_PROTOCOL_DECODE_NOT_VERIFIED** |
| Target power timing | **POWER_TIMING_NOT_VERIFIED** |

Site 1 cannot be marked as completing one real E/P/V. The accepted hardware Job failed before Erase because OpenOCD could not read the Debug Port IDR. There is no Program, Verify, or IC readback SHA256. No further Flash was submitted after that Job.

## Identity and preflight

- Base main: `9c58b32aa0a58554a620090c635de6bab14b96e2`; isolated Site 1 route commit: `f1cb86db3664e7e0994bbc905e2e9a8c21b1b952` (clean checkout). No PR merge.
- PPU `z2-hil`; Boot ID `4cefdc0c-f586-4d19-b126-1d8e1108c8f1`; loaded FPGA `z2-independent-swd-v5-d0add58c`, firmware SHA256 `0d99ecafcb570c39217aa39723ccfcf593ae2021158599085a01436665374bc7`. No FPGA reload or Z2 reboot.
- Site 1 enabled/OpenOCD, exact target `STM32F103C8T6`; JA1/Y18 SWCLK, JA2/Y19 SWDIO; owner confirmed common ground and MCU power always on. Site 2 remained idle and had no Job.
- Route `z2-site1-stm32f103c8t6-operations`, file SHA256 `3c2e43571b5db70d318a2f941bd31829d6cdffbf6ef61a7f33d2f109ba9af4a4`; driver ABI `plasma_swd:5`.
- Firmware `plasma-blue-pill-cdc.bin`, 18,768 bytes, SHA256 `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d`.
- Site 1 Resource Set SHA256 `9e353ab4bcfd80d5d0b8c46bce7442ccf3430388b641346a1c5bcd1dc4487a93`. Active Asset Set generation 20 → 21, Asset Set SHA256 `824b3119aba007dc69882fd851af068e53a24f227b9acb3e9c9be1a5c555fef9`; the accepted Job reused generation 21. Site 2 config was unchanged.
- Z2 `/etc/plasma/ppu.yaml` initially lacked Site 1 `openocd.site_worker_socket`; added `/run/plasma-site-worker/control.sock` and restarted only `plasma-server.service`. Config SHA256 `ed59928c38b4177947998dcd793eae07af011171dc16c70c18e82ca45a3135e4` → `ac0cfa215690ddb9095601064836b7e8fd87ebaa3f223d13a8d0810de8297751`.

## Execution

1. First Batch `8d2fc4a1bfceda489e83570bbaecc64a` was rejected by Gateway before Job creation: `PROVIDER_JOB_NOT_AUTHORIZED`. Start `ecf824160b08f7c767e494d9d2a869c9`, Run `8ef0200e5d388f3b192fb8ba5aca0232`, no Job ID and no DUT Flash.
2. After Site 1 socket fix, a request with an unissued Start ID received HTTP 409 `programming_start_not_startable`; no Batch or Job was created. The associated LA capture is preserved.
3. Manager issued Start `58fe4a850c2cb293df4828de1f8573fb`. Accepted Batch `73c50f24323f05a1638c844e602bb20d`, Run `75bb8ffedd3f9913f595b98595c838fa`, Job `job-20261114-103203-e98521a3`. One attempted hardware Job, no automatic retry. Admission and resource reuse passed.
4. Job failed at OpenOCD connection before Erase, with `OPENOCD_ERASE_FAILED`, RC 1; raw stdout shows repeated `plasma_swd: run rc=-4 ... ack=7` and `Error connecting DP: cannot read IDR`. No Erase, Program, Verify, or readback evidence. Manager Batch outcome `FAIL`, reason `SAFE_OFF_NOT_VERIFIED`; its receipt has `safe_off: null`. The independent Z2 OpenOCD evidence JSON reports `safe_off_verified: true`, `admission_revoked: true`, and the stdout ends `SAFE_OFF_MODE_OFF_VERIFIED`. The Manager receipt limitation remains unresolved.
5. Start reconciliation is `TERMINAL_CONFIRMED/FAIL`. Final Gateway status: Site 1 idle, Site 2 idle, active Job count 0, no OpenOCD process, no Site seal in `/run/plasma-z2-swd05`.

## LA2016

- Kingst LA2016 USB `77a1:01a2`; native sigrok capture, CH3=SWCLK, CH4=SWDIO, CH5=target supply logic state. Digital inputs, 1.4 V threshold, 20 MHz sample rate. No output/PWM was enabled.
- Final raw capture [`site1-epv-final.sr`](site1-epv-final.sr): 600,002,496 samples, 30.0001248 s, SHA256 `1430f21704c08acc8eaac7376a4c0f83573e266227a5aa59db7b6b90b87d85b2`. Capture armed at 10:32:02.181 UTC; Job started at 10:32:04.191 UTC. Capture completed at 10:32:38.841 UTC. The 30-second record spans the Job.
- CH3, CH4, CH5 state is `0x20` for every sample: CH3 low, CH4 low, CH5 high. No SWCLK edges, no SWDIO edges. SWCLK frequency/period/activity duration and direction cannot be measured; SWD decode is unavailable. The cause could be missing activity at the probe points or connection/mapping trouble and is not determined by this capture alone.
- CH5 only observes a digital high level. MCU power was always on by owner statement. Power rise and power off were not captured or verified; no precise voltage measurement was made. Z2 SWD SAFE_OFF does not establish target supply OFF.

## Evidence

- Manager Batch and receipt: [`batch-final-result.json`](batch-final-result.json); Start reconciliation: [`start-final-reconciliation.json`](start-final-reconciliation.json); final Gateway status: [`site-final-status.json`](site-final-status.json).
- Z2 raw OpenOCD stdout: [`site1-97ee5iz5.stdout`](site1-97ee5iz5.stdout), SHA256 `abb73a898fcc5e2bf99f898557f4ecb9ef92d8a58ccb9a430ef2c701bff2722f`; integrity and SAFE_OFF metadata: [`site1-97ee5iz5.json`](site1-97ee5iz5.json).
- LA2016 raw waveform: [`site1-epv-final.sr`](site1-epv-final.sr); analysis: [`site1-epv-final-analysis.json`](site1-epv-final-analysis.json); settings/start metadata: [`run-final-report.json`](run-final-report.json), [`site1-epv-final-capture.log`](site1-epv-final-capture.log).
