# PSPL-02 / SWD-00 internal waveform HIL

This procedure is limited to the **three-aperture** `control_waveform_loopback`
baseline, source `cbe2fb9d012d8ea3df3098ac9ceae0f3d2e468f9`.
Do not substitute SWD-03/SWD-04 tools or their four-aperture firmware.
Identity ABI v1 and physical capability flags 0 remain unchanged.
The baseline project and all earlier Identity artifacts/evidence are immutable.

## Authorization and current status

Root AGENTS.md's two gates apply. Gate 1 covers the agreed implementation and
conditional hardware work; Gate 2 covers merging the resulting PR. Passing a
preflight is a technical prerequisite, not another user approval gate. Neither
this document nor a boolean in an evidence file grants hardware authorization.

The 2026-10-15 read-only audit found an operating FPGA Manager, active original
services, working Gateway live/ready, matching original recovery hashes, and the
original fabric/audio UIO bindings. UART hardware was visible and an existing
terminal owned it. UART login/power recovery were **not independently verified**;
noninteractive privileged access was unavailable. Full process-map/clock checks
were incomplete. **HARDWARE NO-GO; all new Z2 HIL tests NOT RUN.**
Historical HIL-PSPL-01 FULL PASS does not qualify this candidate or current recovery.

No external SWD pins, PMODB, DUT power, IC programming, ps7_init, DDR
initialization, arbitrary PS/PL register probes, Hub Port 3 operation, management
network changes or shared Plasma service restarts are permitted by this plan.
The tools never load firmware, bind/unbind drivers, change metadata or services,
or control power. If safe ownership/recovery requires shared service changes,
STOP and request a revised Gate 1 scope. Never reuse the old Identity operator
script: it stops/restarts services and does not test this register contract.

## Host verification and staging

The retained unique Vivado run is identified in
`pl/projects/z2-control-waveform/baseline-host-2026-10-15.json`.
Its BIT, HWH, original manifest and evidence digests were independently rechecked.
Existing synthesis/implementation/timing/DRC evidence is retained; HIL tool
changes do not change RTL or require overwriting/rebuilding that run.
Any RTL/build-input change requires a new unique Vivado run and reviewed new
artifact pins; this harness intentionally rejects other builds.

Run Verilator lint as in `.github/workflows/pl-pspl02-swd00.yml` and:

```sh
python3 -m pytest -q pl/tests/test_pspl02_hil.py pl/tests/test_z2_control_waveform_build.py
python3 -m pytest -q pl/verification/test_pspl02_swd00_rtl.py pl/verification/test_pspl02_hil_rtl.py
```

Older Verilator 4.038 names the unused-signal warning `UNUSED`; newer CI uses
`UNUSEDSIGNAL`. This spelling difference is not a waiver for other lint errors.
The original regression covers all WSTRB masks, independent AW/W ordering,
backpressure, reset, semantic errors and waveform boundaries. The additional
Cocotb runner executes the exact HIL functions through the actual Control and
Command RTL, checking the intentional SLVERR response in simulation.
No PS CPU MMIO result is reported as direct physical AXI response observation.

For conversion, use a **copy** of the pinned BIT in a fresh directory with
`candidate.bif` containing `all: { candidate.bit }`:

```sh
bootgen -arch zynq -image candidate.bif -process_bitstream bin -w off
```

This is raw FPGA Manager firmware, not BOOT.BIN or an FSBL/SD boot image.
Bootgen 2026.1 output SHA256:
`3d473eee307cf6dc36c66ffc9a80055a44141fa5b37c27acd0a850d0ab8f72e4`.
Verification checks every word-swapped BIT payload byte and the exact trailing
NOP, plus the pinned digest. Raw BIT, unswapped payloads and extra bytes fail.

The following are shell templates. Set paths from verified actual files; do not
use placeholder paths as executed commands. `ART` points to the retained build's
`artifacts` directory, `BIN` to the converted copy, `REC` to an independent copy
of this board's original base.bin/base.hwh, and `KIT` to a new private directory:

```sh
python3 -m pl.hil.pspl02.staging \
  --bit "$ART/plasma-z2-control-waveform-0.1.0.bit" \
  --hwh "$ART/plasma-z2-control-waveform-0.1.0.hwh" --manifest "$ART/manifest.json" \
  --bin "$BIN" --base-bin "$REC/base.bin" --base-hwh "$REC/base.hwh" --output "$KIT"
```

The kit contains verified candidate/recovery bytes, pure Python >=3.10 sources,
false-by-default templates, this checklist, SHA256SUMS and an archive. It needs
no pip installation, native wheels or PYNQ import. Three existing SWD-04 modules
are included only as parser/hash/read-only collection dependencies; their
four-aperture live runner is not included. Use only `pl.hil.pspl02` commands.
Unpack without overwriting files and run `sha256sum -c SHA256SUMS`. Set
`PYTHONDONTWRITEBYTECODE=1` when running kit commands to avoid cache writes. Keep the kit
unchanged; choose a new private evidence directory `E` outside it (`umask 077`).

## Before loading: all conditions mandatory

1. Independently verify current UART login and a physically present operator's
   independent power recovery ability without using Hub Port 3. Keep UART open.
   Do not interrupt another terminal owner. Confirm no DUT/SWD/PMOD target.
   SSH alone, a serial device node or a historical attestation is insufficient.
2. Obtain authorized root access without publishing credentials or changing
   sudoers. Do not assume a UART sudo session authenticates an SSH session.
3. Audit active PL/DMA/DRM users, `/proc/*/fd` **and** retained `/proc/*/maps`,
   drivers, service cgroups and asynchronous PYNQ/overlay loaders. Incomplete
   visibility, unknown ownership or required service restarts means NO-GO.
4. Retain kernel log, enabled 100MHz FCLK0, FPGA Manager flags/state, original
   service states and PYNQ metadata. Resolve installed PYNQ metadata location;
   copy every `global_pl_state_*.json` and `_current_metadata.pkl` if present to
   an independent private backup, preserving ownership/mode. Never unpickle.
   Verify recovery bytes again. Original base.bit should remain intact too.
5. Collect the baseline using root, actual metadata/backup directories:

```sh
python3 -m pl.hil.pspl02.inventory --metadata-dir "$META" \
  --backup-dir "$BACKUP" --output "$E/before-raw.json"
```

The collector is read-only and leaves `original_drivers_reviewed=false`.
Preserve that raw output. In a separate reviewed copy `before.json`, mark only
the driver-review field after independently reviewing all PL drivers and DMA
owners. Complete a separate attestation from the kit template, one observed
field at a time. Never bulk-set booleans. Process users/errors must be empty;
the tools never turn permission errors into proof of exclusivity.
Inventory/session timestamps expire after ten minutes. Recollect if stale.

From the kit root, the artifact arguments below refer only to verified kit files:

```sh
python3 -m pl.hil.pspl02.runner preflight \
  --bit artifacts/bit --hwh artifacts/hwh --manifest artifacts/manifest \
  --bin artifacts/bin --base-bin artifacts/base.bin --base-hwh artifacts/base.hwh \
  --inventory "$E/before.json" --attestation "$E/attestation.json" --output "$E/p0.json"
```

## Supervised load and bounded tests

Only after approved scope and every technical prerequisite passes: reconcile
the **audited** original `40000000.fabric` / `43c00000.audio-codec-ctrl` UIO
bindings without changing shared services. The original fabric map is 64KiB
and overlaps all three candidate apertures. Verify the unbind and absence of
retained mappings. Do not use unstable uio indexes as resource identity.
Do not unbind unknown devices or perform broad process termination.

Stage verified candidate BIN under a new unique `/lib/firmware` filename,
refusing overwrite; rehash that exact staged file. Review FPGA Manager flags
for full configuration (0), current FCLK/reset/GP0 assumptions and PYNQ/XRT
side effects. Load once through the reviewed FPGA Manager sysfs mechanism.
Record command, filename, staged hash, time, return status, operating state,
kernel delta and clocks in a real private load log. No Overlay.download(),
PS register writes, DDR initialization, retries or automatic rollback loop.

Run each stage in a new process: `IDENTITY`, `PSPL02`, `SWD00`, `ERROR`, `RESET`.
Make a fresh session from its false template, binding the actual load log,
preflight hash, current timestamp and original metadata/backup path and hash.
The runner verifies all metadata backup bytes, current clocks, process maps,
original driver absence, board/root identity and unchanged active services before
opening /dev/mem. Independently verify no asynchronous reload source remains.
It checks Identity/Build ID before every stage's writes.

```sh
python3 -m pl.hil.pspl02.runner live \
  --bit artifacts/bit --hwh artifacts/hwh --manifest artifacts/manifest \
  --bin artifacts/bin --base-bin artifacts/base.bin --base-hwh artifacts/base.hwh \
  --p0 "$E/p0.json" --session "$E/session-IDENTITY.json" --stage IDENTITY \
  --output "$E/IDENTITY" --execute-live --ack-unrecoverable-axi-stall-risk
```

For each next stage use its own session/output and add `--previous` pointing
to the preceding stage's `result.json`. Never skip a failed or missing result.
The same preflight and actual load-log hash must bind every stage.

| Stage | Required observation |
|---|---|
| IDENTITY | Eight exact Identity words, ABI/flags/Build ID, SWD command ABI 1; read only |
| PSPL02 | HIL-PSPL-02A CONTROL vectors and 02B STATUS XOR readback |
| SWD00 | HIL-SWD-00A/B internal commands, bounded completion, repeated DONE/RX reads and explicit CLEAR; echo, independent RX and digital OE-low vectors |
| ERROR | HIL-SWD-00C START with reset count 0, sticky config ERROR=3, unchanged RX, explicit CLEAR |
| RESET | HIL-SWD-00D observed BUSY then soft RESET, exact defaults and successful transfers again |

ERROR intentionally requests a **known** semantic SLVERR at a valid command
address. ARM may deliver SIGBUS or a kernel abort; the runner cannot promise
recovery or directly observe physical BRESP. Such termination is failure, not
permission to continue probing. Busy reset uses a roughly 42ms window; if Linux
scheduling misses it, STOP rather than retry until it passes. External reset,
illegal addresses, AXI backpressure and byte strobes remain offline checks.

Each live stage exclusively creates an evidence directory and `started.json`
before opening MMIO, then `result.json` on observed completion. A SIGBUS/kernel
stall may leave only the start record. Missing PASS means STOP. Poll budgets
bound software loops, **not a blocking physical AXI transaction**.

## Original-image recovery, on success or failure

If Linux responds, stop further AXI probes and use the verified original
base.bin through FPGA Manager once. Require operating and inspect kernel delta.
Compare all original metadata bytes to backups; restore only audited changed
files with original ownership/modes, without touching unrelated metadata.
If this needs shared service changes, STOP: current scope does not allow them.
Rebind only the original audited driver pair after base is operating. Verify
UIO names/addresses/sizes and driver links, clocks, unchanged active services,
UART/public-key SSH, Jupyter HTTP and Gateway live/ready. Record actual outcomes.
Collect a fresh `after.json` using the inventory collector and compare:

```sh
python3 -m pl.hil.pspl02.recovery --before "$E/before.json" --after "$E/after.json" \
  --observed "$E/recovery-observed.json" --output "$E/recovery-result.json"
```

`recovery.verify` lists every separately observed assertion and exact recovery
digests; boolean statements are operator observations, not machine-proven facts.
Restoration acceptance alone does not imply the HIL stages passed. Overall PASS
requires all five stage results and recovery PASS in the same loading session.

If AXI/SSH stalls, use the verified UART; if kernel/UART also stalls, the present
operator uses the previously verified independent power path and known-good SD
boot. No automatic power cycling or Hub Port 3 operation. Verify the recovered
platform; never report an unexecuted emergency recovery as PASS.

Keep raw kernel, process, metadata and operator infrastructure evidence private.
Publish only reviewed results and hashes, never private hostnames, paths,
credentials or binary artifacts. Never overwrite old HIL evidence.
