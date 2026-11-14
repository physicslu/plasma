# Site 1 real HIL E/P/V with LA2016 SWD waveform — 2026-11-14

**Verdict: physical Site 1 Flash HIL PASS; synchronized LA2016 capture PASS.** This PR is **Draft / Gate 1 evidence**, not a Gate 2 merge authorization.

## Source, route and physical scope

- Base `main` at `05b2ccc883e9ca4c81f85ed35f3dfe0d139171f0`; actual physical execution used already deployed qualified Manager/Z2 Runtime and loaded FPGA image, **not** this unmerged PR.
- PPU `z2-hil`; **Site 1 only**, Blue Pill STM32F103C8T6; Site 2 remained idle. Existing FPGA `z2-independent-swd-v5-d0add58c`, ABI `plasma_swd:5`, SWCLK 2 MHz.
- This PR also carries the previously unmerged `z2-site1-stm32f103c8t6-operations` route from `site1-hil-gate1` (`bf5e0e3403f20afc6a20e8a3310dba9e93825e57`) and updates two negative tests to use unsupported Site 3. The route is **not already merged into main**. Historical failure evidence remains traceable on that branch; it is not reclassified as PASS.
- Existing qualified image `plasma-blue-pill-cdc.bin`, 18,768 bytes, SHA256 `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d`.

## One new real programming Job

- GitHub Actions [Run #43596359892](https://github.com/physicslu/plasma/actions/runs/43596359892); Work Order SHA256 `bc148959232deaff8e9eaa0d54417462df0e50a8cfb291ab51156535ce7772e2`.
- Start `bfc3acd4f7db4ae7c68302e71ed72c11`; Batch `2ffbe773461e39d62013219a78774061`; Run `ff2822e7f2094f8823d4d030c6b48d1e`; Job `job-20261114-124905-661b6d67`.
- Job 2026-11-14 12:49:05.757074–12:49:12.248010 UTC (6,477 ms); **one submission and one physical attempt, no retry**.
- OpenOCD `PS_OWNER_ATTACHED site 1`, DPIDR `0x1BA01477`, rc=0. Erase **19,456 bytes** at `0x08000000`; Program and Verify/complete readback **18,768 bytes**. Readback SHA256 is **identical** to the bound firmware SHA256 above.
- Manager Batch and terminal Start reconciliation **PASS**. Native `SAFE_OFF_MODE_OFF_VERIFIED` plus admission revoked; Manager `safe_off=true`; no remaining OpenOCD process, seals or Site locks. Both sites idle. No recovery necessary.

## LA2016 — fresh synchronized wave, not the previous capture

- Passive LA2016, CH3=PMODA SWCLK, CH4=PMODA SWDIO, CH5=existing digital target-supply probe; 1.4 V digital threshold, 20 MHz samplerate, **1,000,001,576 samples**, **50.0000788 seconds**.
- Capture armed 2026-11-14T12:49:03.739369Z, **before** Manager Start; its nominal sampling interval covers the entire physical Flash Job. The driver closed by 12:50:05.896413Z, including USB transfer overhead. No extra synchronization accuracy is asserted.
- CH3 **1,817,878 edges**, CH4 **273,948 edges**, CH5 **0 edges**. Modal SWCLK rising period 10 samples / 500 ns = **2 MHz**.
- Real Sigrok decode: **16,822 ACK OK**, **0 WAIT**, **0 FAULT**, one DPIDR value. Wave file `site1-epv.sr` (2,250,393 bytes) SHA256 `9ff7c4df08caa46832a6e7f364507023a2ddaaf857069abfa1696bb513b45bf0`.
- The digital CH5 reading **does not verify analog voltage, power-on/off timing or target-supply OFF**. SWD SAFE_OFF only confirms the interface mode-off condition.

## Evidence and retention

- [Actions Artifact #14115251160](https://github.com/physicslu/plasma/actions/runs/43596359892/artifacts/14115251160) `plasma-development-codex-43596359892`, ZIP SHA256 `d0e41883f7d2fbc2307ea6cc2184ccbf77be20bf78df9c6caa315b914246aeb9`.
- Inside `_temp/plasma-path3-engineering-evidence.tar.gz` (SHA256 `ccaaff6110f673b33892ab453b92c06457d3fc14dfdfea69f5de023112c3a92e`), retrieve `.plasma-path3-evidence/site1-epv.sr`, SWD decoder output, original OpenOCD stdout, Manager receipts and identity records. The inner curated raw evidence tar SHA256 is `054d3009fa02762066101ab7b8c9bad2670339f59959059b9e97c210348e1723`.
- This PR keeps compact machine-readable summaries and SHA256 references, not transient credentials or bulky raw waveform logs. **GitHub Actions Artifacts have retention limits; the raw waveform must be archived separately for long-term retention before expiry.**
- Additional proven previous HIL: [Run #43595608278](https://github.com/physicslu/plasma/actions/runs/43595608278), Job `job-20261114-123804-2d63121f`, PASS. Previous standalone Site 1 DPIDR/LA: [Run #43592688072](https://github.com/physicslu/plasma/actions/runs/43592688072), PASS. Neither is substituted for the new measurements.

## Reproducibility, limitations and Gate

Codex evidence review `validate.py` PASS (native receipt, Manager, waveform statistics and decode, overlap, release and Root identity). No software/RTL changes or FPGA reload/deploy during real Flash; this PR newly integrates the existing unmerged Site1 Route and adjusts two test negative cases, so **PR CI and change review are still required** before Gate 2. LA2016 initial CLI threshold format error was corrected **before** the Start, without an extra hardware attempt. No automatic retry or Site 2 actuation.

**Gate 2: NOT APPROVED. Draft only; do not merge or deploy.**

## 5 MHz SWD + 100 MHz passive capture retest — BLOCKED / NOT_RUN

[Actions Run #43597625441](https://github.com/physicslu/plasma/actions/runs/43597625441), Path 3, source `0e25ac2900c900bdeee08b3b8926f84ffd2c4413`, owner Work Order SHA256 `8d23e5b518381c32f16bc91f1baded88d5bf4b90216f5e34dd0c8a93af2efdf8`. This section records a separate retest; the earlier physical PASS sections remain unchanged.

**Observed blocker: deployed EngineSelection specifies `adapter_khz: 2000`; no deployed runtime session speed API exists.** Read-only authenticated Z2 inspection found `/etc/plasma/site-worker-engine.json` SHA256 `c07ba04c7398979adc7860aea5e0ec54ab088fec2c5891b6f9248ed749b31b05`. The deployed Site Worker control operations are `open_session`, `open_job_session`, `close_session`, `status`, `bind_image`, `bind_range`, `run`. The deployed service passes the verified EngineSelection speed to its adapter at startup; the adapter checks that speed against the verified engine and emits `adapter speed {self.adapter_khz}`. It offers no per-session speed override. The running Worker PID observed was 15799.

Selecting 5,000 kHz requires changing the deployed selection and activating it in the Worker. The Work Order explicitly requires stopping if an unauthorized deployed configuration mutation is necessary. No configuration write, restart, FPGA reload, deployment, PWM, Start, Batch or Job was performed. Site2 was untouched. Native admission/SAFE_OFF, HIL E/P/V/readback, 100 MHz USB acquisition, waveform overlap/edges/ACK decode and measured 5 MHz are **NOT_RUN**. No new `.sr` exists. No 2 MHz Flash was substituted. This is a configuration/API blocker, not an observed DUT failure or analyzer failure.

| Qualification | Earlier baseline | Requested retest |
| --- | --- | --- |
| SWD / sample rate | Measured 2 MHz / 20 MHz | 5 MHz / 100 MHz NOT_RUN |
| E/P/V + full readback | PASS, Job `job-20261114-124905-661b6d67` | NOT_RUN, zero new jobs |
| Waveform / ACK decode | PASS, archived above | NOT_RUN, no raw waveform |

Compact result: `5mhz-100mhz-summary.json`. Sanitized deployed-source inspection and hashes are staged in `.plasma-path3-evidence/deployed-speed-inspection.txt` for the existing workflow artifact `plasma-development-codex-43597625441`. The artifact ID, final archive SHA and upload result are pending workflow completion; no precise artifact URL is claimed before upload. Source patches and new documents are retained by the existing workflow for application to **existing Draft PR #1427 only** if publication is unavailable. GitHub CLI currently has no authenticated token; PR checks/publication are **NOT_VERIFIED** from this subprocess. Wrapper EXIT_ZERO does not imply hardware PASS.

Resolution requires owner authorization for the bounded deployed speed selection/activation (or a separately approved runtime speed API change), followed by a newly authorized physical attempt. No retry was made under this Work Order. Gate 2 remains unapproved; no merge.
