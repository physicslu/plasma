# KINGST PWM1 → CH0: real loopback evidence, 2026-10-16

**Observed functional PASS, two settings.** This archives actual KINGST LA2016
measurements following the USB-only checkpoint in
[PR #961](https://github.com/physicslu/plasma/pull/961). It does not change that
historical checkpoint or claim any Z2, DUT, SWD or IC programming acceptance.
This archive PR performs offline verification only; it does not rerun hardware.

## Results

The owner confirmed **KINGST PWM1 → the same KINGST CH0**. Both endpoints share
the instrument's internal ground. The source is the KINGST generator, not Z2.
The AppImage identified the device and successfully controlled PWM1. Both runs
used 1 MHz sampling (1 µs sample spacing) and a 1.40 V threshold.

| Setting | Measured frequency | Period | Duty cycle | High / Low | Edges (rising / falling) | Complete cycles | Actual samples |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 kHz, 50% | 1,000 Hz | 1,000 µs | 50% | 500 / 500 µs | 205 (103 / 102) | 102 | 102,386 |
| 2 kHz, 25% | 2,000 Hz | 500 µs | 25% | 125 / 375 µs | 406 (203 / 203) | 202 | 101,645 |

The first capture started at 10:49:11 UTC; the second at 10:51:12 UTC on
2026-10-16. Each acquisition requested 100,000 samples; the actual archive
lengths above include the device's additional samples. Measurements use the
actual metadata and bytes, not the requested length.

Each complete cycle runs from one rising edge to the next and contains exactly
one falling edge. Frequency is sampling rate divided by mean cycle length;
duty is total complete-cycle High samples divided by total cycle samples.
Every complete cycle and pulse width matched the setting at sample resolution.
Partial pulses at capture boundaries are excluded from duty calculation.

The valid edges, doubled frequency and reduced pulse width establish actual
generator-to-input behavior, rather than treating an empty or constant capture
as PASS. Both the source control and capture path passed. Generator and sampler
share an instrument timebase: this is **not independent frequency calibration**
or an analog amplitude/jitter qualification.

## PWM shutdown

Each run executed an explicit `enabled=off` command in the supervisor's `finally`
path. Both shutdown commands exited zero and the driver logged PWM1 disabled.
Each subsequent OFF capture contains **22,496 samples, all Low, zero edges**.
The instrument was left with PWM1 OFF.

## Driver and electrical contract

The existing AppImage reported sigrok-cli `0.8.0-git-f44dd91` and libsigrok
`0.6.0-git-883c2ac`; its digest is in [tool.json](tool.json). System sigrok was
not replaced. The `kingst-la2016` driver advertised `enabled`,
`output_frequency` (Hz), and `output_duty_cycle` (percent) on PWM1.

The matching [driver source](https://github.com/sigrokproject/libsigrok/blob/883c2ac/src/hardware/kingst-la2016/api.c)
initializes PWM defaults on device open; its displayed current settings are
software state, not hardware readback. Configure PWM and acquire within the
**same invocation**, using separate device/PWM channel-group config lists.
The saved debug logs show the enabled settings and threshold applied. Every
hardware invocation reused the existing LA FPGA image: **No upload required**.

The KINGST-authored [User Guide, page 5 (third-party mirror)](https://supereyes.ru/img/instructions/Kingst_Virtual_eng.pdf)
specifies nominal PWM output **+3.3 V**, 50 Ω, and LA2016 inputs ±50 V,
220 kΩ / 12 pF, with adjustable threshold. The documented same-device loopback
is compatible with the applied 1.40 V threshold. **Actual voltage amplitude,
overshoot and electrical margins: NOT RUN**; a digital capture cannot measure
these. The current [official download page](https://www.qdkingst.com/en/download)
also links the vendor guide. Vendor software, firmware and PDFs are not
redistributed in this archive.

## Reproduction command contract

The following parameterized commands represent the actual successful invocations.
Set `SIGROK_APPIMAGE`, `SIGROK_FIRMWARE_PATH`, and `OUT` to existing approved
local resources and a new output filename. The original used `--loglevel 4`.
Select the **currently enumerated** KINGST connection as `LA_CONN`; never reuse
a historical bus address or select `ftdi-la` / the Z2 interface. Ensure no other
application owns this LA, and confirm the same-device wiring before execution.

```bash
export SIGROK_FIRMWARE_PATH
"$SIGROK_APPIMAGE" --appimage-extract-and-run --loglevel 4 \
  --driver "kingst-la2016:conn=$LA_CONN" \
  --config samplerate=1m \
  --config channel_group=PWM1:output_frequency=1000:output_duty_cycle=50:enabled=on \
  --channels CH0 --samples 100000 --output-file "$OUT"
```

The second run changed only the PWM list to
`channel_group=PWM1:output_frequency=2000:output_duty_cycle=25:enabled=on`
and used a separate output file. Always execute shutdown in the controlling
supervisor's `finally` path, including acquisition failure:

```bash
"$SIGROK_APPIMAGE" --appimage-extract-and-run --loglevel 4 \
  --driver "kingst-la2016:conn=$LA_CONN" \
  --config channel_group=PWM1:enabled=off --set
```

For the OFF check, acquire CH0 with `samplerate=1m`, `--samples 20000`, no PWM
enable config, and a separate output file. Preserve logs and inspect actual
sample data. A fresh `--get` of PWM state alone is not proof of physical OFF.
The archived [first execution](1khz-50pct/execution-sanitized.json) and
[second execution](2khz-25pct/execution-sanitized.json) retain full arguments,
timestamps, return codes and stdout/stderr with operator identifiers replaced.
These are explicitly sanitized derivatives; private original logs remain intact.

## Saved evidence and offline verification

- [Combined measurements](measurements.json), [tool identity](tool.json),
  [SHA256SUMS](SHA256SUMS).
- First run: [ON .sr](1khz-50pct/on.sr), [OFF .sr](1khz-50pct/off.sr),
  [edges](1khz-50pct/edges.csv), [complete cycles](1khz-50pct/complete-cycles.csv).
- Changed setting: [ON .sr](2khz-25pct/on.sr), [OFF .sr](2khz-25pct/off.sr),
  [edges](2khz-25pct/edges.csv), [complete cycles](2khz-25pct/complete-cycles.csv).

All four `.sr` files are **byte-for-byte original archives**; only their filenames
have changed. They contain no operator paths or transient USB addresses. Derived
JSON/logs omit those identifiers; no original private evidence was overwritten.
Run the standard-library-only [verifier](verify.py) from any working directory:

```bash
python3 docs/evidence/la2016-pwm-loopback/2026-10-16/verify.py
```

It checks all archive digests, parses raw CH0 bytes, recomputes complete-cycle
timing/edges, compares both settings, and verifies constant-Low OFF captures.
It **never opens USB or performs a new hardware test**. This experiment did not
operate Z2, change FPGA images, cycle the USB hub, modify services, or program a DUT.
