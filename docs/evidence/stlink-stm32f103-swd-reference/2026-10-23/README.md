# ST-LINK → STM32F103 SWD golden reference, 2026-10-23

This archive preserves an **observed STLINK-V3SET reference programmer** experiment on the STM32F103C8T6 Blue Pill DUT. The KINGST LA2016 was a passive SWCLK/SWDIO observer. The future PLASMA PYNQ-Z2 PS/PL SWD controller is the experimental design that may be compared with these traces; **Z2 physical SWD programming was NOT_RUN**. The archive PR performs offline analysis only and does not repeat hardware work.

The reference firmware is the PR #1132 merge `5949f371078a0f67c6fc3c0d99e85da738235d08`, including its PA12 boot disconnect pulse. Its BIN SHA256 is `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d` (18,768 bytes). The archived three independent readback binaries each have exactly that length and digest. The original 64-KiB prewrite Flash backup remains in controlled SWPC storage and is **not** in Git; its SHA256 only is in [tool.json](tool.json). No production DUT data is claimed.

## Experimental identity and connection

| Role | Observed or owner-confirmed configuration |
| --- | --- |
| Reference programmer | STLINK-V3SET V3J17S1, SWD; exact serial redacted. `st-info --probe` identified chip ID `0x0410`, 64-KiB Flash, 20-KiB SRAM. |
| DUT | Owner-designated STM32F103C8T6 Blue Pill; USB CDC `cafe:4001`. Owner confirmed exclusive ST-LINK SWD wiring and no concurrent Z2/PmodBB SWD drive. |
| SWD | ST-LINK T_VCC, GND, SWCLK, SWDIO and stated NRST path to DUT. ST-LINK later warned `NRST is not connected`, so electrical NRST continuity is unverified. |
| Analyzer | KINGST LA2016 `77a1:01a2`, common GND; CH0 = PA14/SWCLK, CH1 = PA13/SWDIO, CH2 = Blue Pill 3.3-V logic. CH3 NRST was not connected/confirmed. |
| Analyzer tool | Pinned sigrok AppImage SHA256 `b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475`, sigrok-cli `0.8.0-git-f44dd91`, `kingst-la2016` driver, 5-MHz sampling, 1.40-V current logic threshold. No PWM output was enabled. |
| Flash tool | `st-flash` 1.7.0, `--freq=100`; each command logged that it selected **50 kHz**. OpenOCD 0.11.0 sensed 3.316944 V after T_VCC was connected. |

Before T_VCC was connected, OpenOCD had sensed 0.003189 V and programming was stopped. The owner connected T_VCC, after which 3.316944 V was observed; [round-2](round-02-voltage-sanitized.log) and [round-3](round-03-voltage-sanitized.log) voltage logs are archived. The first corrected voltage observation is retained in the controlled SWPC HIL report/command record rather than a separately saved voltage log. CH2 being digitally HIGH in the `.sr` files proves only that its input exceeded the selected logic threshold during sampling; it does not qualify analog rail quality.

## Three-round acceptance matrix

| Measurement | Round 1 | Round 2 | Round 3 |
| --- | --- | --- | --- |
| ST-LINK Flash command, exit 0, 19 pages | PASS | PASS | PASS |
| Separate 18,768-byte Flash readback equals firmware SHA256 | PASS | PASS | PASS |
| Synchronized 3-channel LA acquisition, CH0/CH1 activity | PASS | PASS | PASS |
| Sigrok SWD DP/AP requests and ACK decode | PASS | PASS | PASS |
| SWD clock timing qualification | EVIDENCE_INSUFFICIENT | EVIDENCE_INSUFFICIENT | EVIDENCE_INSUFFICIENT |
| First **saved** 60-second CDC probe with ID | PASS* | FAIL | FAIL |
| Original unconditioned round-1 attempt | EVIDENCE_INSUFFICIENT* | NOT_RUN | NOT_RUN |
| CDC after recorded empty-line recovery | PASS | PASS | PASS |
| Electrical NRST assertion | EVIDENCE_INSUFFICIENT | EVIDENCE_INSUFFICIENT | EVIDENCE_INSUFFICIENT |

The machine-readable [acceptance matrix](acceptance-matrix.json) uses PASS, FAIL, NOT_RUN and EVIDENCE_INSUFFICIENT. `st-flash reset` exited 0 and Blue Pill USB reenumerated after each round, but every reset log warns `NRST is not connected`. This archive does not convert that warning into an NRST PASS.

\* The surviving file named `round-01-cdc.log` in the original workspace is a successful **retry**: the original unconditioned round-1 attempt had exited 1 after 120 Heartbeats without an ID, but its full raw log was accidentally overwritten by the retry. Its old digest and partial tool output remain in the controlled SWPC record. The archived derivative is named [round-01-saved-pass-cdc-sanitized.log](round-01-saved-pass-cdc-sanitized.log) to prevent it from being mistaken for the initial attempt. Thus the **saved named first-probe files** show 1/3 PASS, whereas the known initial unconditioned attempt cannot be independently replayed for round 1. Strict post-reset CDC acceptance is **FAIL** because rounds 2 and 3 have preserved unconditioned ID failures.

## Original waveforms and SWD decoding

The six `.sr` files were copied **byte for byte** from controlled SWPC `.work/blue-pill-hil-unblock-20261023/` evidence, with build context in `.work/blue-pill-hil-reproduction-20261023/`. Source and checkout SHA256 were independently recomputed and matched; the six paired results and sizes are in [source-integrity.json](source-integrity.json). Each ZIP archive contains 24 logic chunks, sigrok metadata, 5-MHz sample rate and CH0/CH1/CH2 map; archive metadata contains no operator path, private USB serial or host address. The ZIP bytes were not repacked, truncated or resampled.

| Round | Program waveform SHA256 | Verify waveform SHA256 |
| --- | --- | --- |
| 1 | [`ada6be5f…`—program](round-01-program.sr) | [`8790576e…`—verify](round-01-verify.sr) |
| 2 | [`d01dd54f…`—program](round-02-program.sr) | [`efddfe31…`—verify](round-02-verify.sr) |
| 3 | [`36e0f764…`—program](round-03-program.sr) | [`027f019a…`—verify](round-03-verify.sr) |

The full digests are in [SHA256SUMS](SHA256SUMS) and [measurements.json](measurements.json). All six captures are about 10 seconds and contain 50 million samples. Program CH0 rising-edge counts are 692,700 / 694,940 / 694,349; Verify counts are 221,899 each. Program CH1 rising-edge counts are 118,058 / 118,322 / 118,250; Verify counts are 39,988 each. CH2 remained HIGH at the digital threshold through all six captures. Per-round Program and Verify receipts establish acquisition/Flash-command time overlap and are labelled `*-sanitized.json` because private paths and transient USB addresses were removed.

The saved sigrok decoder outputs contain DP/AP read/write requests, ACK OK and WAIT, and `0x1ba01477` IDCODE in every Verify capture and in Program rounds 2–3. Round-1 Program starts with AP traffic and contains no IDCODE annotation in its saved window. [Decode summary](swd-decode-summary.json) and the six full `*-decode.txt` derivatives retain exact annotation counts. No FAULT annotation was emitted. Sigrok did **not** explicitly annotate turnaround, and the decoder output is not an independently qualified, exhaustive transcript of every SWD bit or the entire erase/program process.

## SWCLK period distribution: unresolved tool/trace discrepancy

The offline verifier parses **every** saved rising-to-rising SWCLK interval from the 5-MHz raw samples; [measurements.json](measurements.json) retains the full integer-sample histograms. At 5 MHz one sample is 0.2 µs. In all six windows the modal period is **50 samples (10 µs, nominally 100 kHz)**, while the `st-flash` logs say the requested 100 kHz was rounded to **50 kHz**. A separate 80–88-sample population and long idle gaps are also present. Selected counts:

| Capture | Modal 50-sample periods | 49–53-sample periods | 80–88-sample periods | Maximum gap (samples) |
| --- | ---: | ---: | ---: | ---: |
| Round 1 Program | 487,858 | 638,260 | 38,614 | 53,700 |
| Round 1 Verify | 145,291 | 198,290 | 18,416 | 1,806 |
| Round 2 Program | 489,169 | 640,212 | 38,921 | 53,500 |
| Round 2 Verify | 145,127 | 198,288 | 18,419 | 2,937 |
| Round 3 Program | 488,830 | 639,606 | 38,905 | 53,577 |
| Round 3 Verify | 145,147 | 198,300 | 18,421 | 2,821 |

These distributions cannot be reduced to total edge count divided by the 10-second capture, because long command idle windows and more than one local period population are present. The exact cause of the difference between the tool's 50-kHz message and the sampled 50-sample mode is not established. Possible clock selection or analyzer timebase interpretation requires a separate calibrated investigation. **SWD clock timing qualification is EVIDENCE_INSUFFICIENT**; this archive preserves the raw material for that work and makes no analog edge-quality or jitter claim.

## CDC, recovery and known defects

The original, unmodified `cdc_probe.py` was used for each 60-second run. It waits for an autonomous `HB version=0.1 ...` before sending `ID`. The accepted round logs each show 121 consecutive Heartbeats, zero sequence gaps, monotonic Uptime and a near-0.500-second interval; the raw timestamped lines and recomputed statistics are in [CDC summary](cdc-summary.json) and `*-cdc-sanitized.log`. The round-2 and round-3 initial logs each show 120 uninterrupted Heartbeats followed by probe exit 1 because `ID` got `ERR UNKNOWN_COMMAND`. A recorded single newline then allowed the same original probe to pass. The exact source of any partial command line has not been proved; the fault is not attributed to a specific host service or firmware routine by this archive.

The [Host Port Close/Reopen log](host-reopen-cdc-sanitized.log) shows a 5-second deliberate close, reopen, resumed Heartbeats and original-probe exit 0. Its one receive sequence gap and 5.042-second interval cross the intentional pause and are **not** evaluated under uninterrupted 500-ms timing. Physical USB unplug/replug was NOT_RUN.

An independent ST-LINK reset command exited 0, and the same Blue Pill USB path reenumerated. Its new TTY lost the temporary operator ACL; no post-reset port reopen/ID/Heartbeat probe was completed. The [recovery summary](recovery-summary.json) therefore marks the full independent MCU Reset Recovery **NOT_RUN** and preserves the NRST warning. The last saved ACL snapshot after this reset was `root:dialout 0660` without the temporary operator grant; that is an archived snapshot, not a claim about the device's future state. Physical PC13 LED observation was NOT_RUN. The exact-match temporary TTY ACL and its loss on reenumeration are described here without committing operator identity or changing system permission rules.

## Reuse, confidentiality and offline verification

This baseline can compare future controller SWD requests, ACK behavior, activity windows and readback evidence against a proven ST-LINK reference on the **same DUT class**. It does not establish that PLASMA's Z2 controller can Flash, Verify, Reset or meet SWD timing.

The six `.sr` archives and six decoder text outputs were inspected and are byte-identical to their controlled sources. The three archived 18,768-byte readbacks are exactly equal to the public candidate firmware SHA256; the **64-KiB prewrite backup is excluded**. Program/Verify receipts, CDC logs, voltage/reset logs and newline receipts are explicitly labelled sanitized derivatives: private absolute paths, full USB serials and transient bus addresses were omitted. Original files in `.work` were neither deleted nor overwritten by this archival task. Full privileged logs and secrets are not committed.

Run the standard-library-only verifier from any working directory after checkout:

```bash
python3 docs/evidence/stlink-stm32f103-swd-reference/2026-10-23/verify.py
```

It validates [SHA256SUMS](SHA256SUMS), reopens all six original `.sr` archives, recomputes all channel edges and complete SWCLK period histograms, checks program/readback/capture receipt consistency, recomputes the saved decoder annotation and CDC log statistics, and checks the acceptance matrix. It opens **no USB or serial device**. No hardware command, Flash, Reset, LA acquisition, Z2 operation, permission change or deployment is part of this archival PR.
