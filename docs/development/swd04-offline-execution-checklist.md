> **HISTORICAL / INTERNAL-FIXTURE ONLY — NOT a Blue Pill Path 3 operator runbook.** The `z2-swd03-axi` synthetic responder is retired for external SWD; its DPIDR is not from Blue Pill. Follow root `AGENTS.md` and [retired path inventory](swd-legacy-path-retirement.md) for current PS-local OpenOCD → WordPort → PL SWD. This document remains only for referenced host-only/legacy testing, not hardware authorization.

# SWD-04 offline staging and controlled execution checklist

This document is a procedure, **not hardware authorization**. Offline tests are
not Z2 acceptance. Z2_HIL, PHYSICAL_SWD and REAL_IC_PROGRAMMING remain NOT_RUN.
Use the reviewed/merged tools only in a separately authorized maintenance window.
Do not run the historical Identity-only operator script for this new design.

## Host staging gate

- Candidate: SWD-03 source `d39e85194f27e20f0ae7f2eb7c0623b293ff1108`;
  BIT/HWH hashes are pinned in `pl.hil.swd04.contract`.
- Convert a **copy** of that BIT with Xilinx Bootgen 2026.1:
  `bootgen -arch zynq -image candidate.bif -process_bitstream bin -w off`.
  BIF contents: `all: { candidate.bit }`. Output is `candidate.bit.bin`.
  Do not generate BOOT.BIN, include an FSBL, or execute ps7_init.
- `staging.verify_bin` parses the BIT envelope and compares **every** byte of
  the raw word-swapped payload, its exact observed trailing NOP, length, pinned
  BIN digest and synchronization word.
  Raw BIT, unswapped data, boot images and extra/truncated bytes are rejected.
- Offline kit: pure Python source, Python >=3.10, standard library only;
  no pip install, numpy, PYNQ import or native wheels required by the tools.
  The read-only collector queries installed PYNQ metadata without importing it.
  Target needs systemctl, sha256sum, curl, a usable shell and approved root access.
- A kit without verified original base.bin AND base.hwh is **NO-GO** for loading.
  A historical checksum is not possession of recovery bytes. Never substitute
  another board's base image or download a similarly named unverified file.
- Run `sha256sum -c SHA256SUMS` after unpacking. Keep the kit read-only and use
  a fresh private evidence directory outside it. Archive and checksum all logs.
  The `staging-report.json` records missing recovery without claiming P0 PASS.

## Current physical GO / NO-GO (before stopping anything)

The operator must independently verify all items at the board, immediately
before loading. The previous day's UART/power observations are insufficient.

1. No DUT, SWD cable or PMOD target connected. Confirm PYNQ-Z2, ARMv7 Linux,
   Python >=3.10, PYNQ 3.1.1, FPGA Manager operating and enabled FCLK0 100 MHz.
2. UART login and output work NOW. Keep it logged in throughout the operation.
   Operator is physically present and can independently disconnect/restore power.
   SSH alone is not recovery; verify public-key SSH separately.
3. Preserve current kernel log, clocks, manager state/flags/firmware, service
   states, sockets, process identities, `/proc/*/maps`, driver bindings and
   PYNQ overlay state. Keep raw inventories private.
4. Identify the actual current PYNQ metadata directory. Historical platform used
   `$PYNQ_ROOT/pl_server` (resolve the installed PYNQ root first): `global_pl_state_*.json` and, if present,
   `_current_metadata.pkl`. Back up those exact bytes, preserve modes/ownership,
   and record individual SHA256s. **Do not unpickle metadata** or remove files.
5. Copy the current original `/lib/firmware/base.bin` and original base overlay
   HWH into the evidence recovery directory. Verify exact pinned recovery hashes
   with the offline contract. Check original base.bit too if retained.
6. Required services are Jupyter plus plasma-bootstrap, plasma-server,
   plasma-web and plasma-runtime-activation. All must initially be active.
   Unknown services, drivers, metadata or PL consumers require review: NO-GO.
7. Run the read-only inventory collector with the actual metadata file and save
   `before.json`. Collecting debugfs clock information can require root.
8. Complete the operator attestation manually after observing UART, power,
   ownership plan and recovery prerequisites. Never bulk-set all flags true.
9. Copy `templates/attestation.json` to the evidence directory and review every
   false flag individually. Session templates for all three phases also default
   to false; fill the actual P0 and supervised-load log hashes and observed
   conditions before each phase. Do not modify the read-only kit templates.
10. Run P0 using actual BIT, HWH, manifest, recovery pair, fresh inventory and
   attestation. Require `SWD04_P0_OFFLINE_PASS_NO_HARDWARE_ACTION`.
   P0 PASS still does not itself authorize the load.

Example offline/target command, from unpacked kit root (repository-style
`pl/` directory, no installation):

```sh
python3 -m pl.hil.swd04.collect --metadata-file "$METADATA_FILE" --output "$E/before.json"
python3 -m pl.hil.swd04.preflight \
  --bit artifacts/candidate.bit --hwh artifacts/candidate.hwh \
  --manifest artifacts/manifest.json \
  --recovery-bin "$E/recovery/base.bin" --recovery-hwh "$E/recovery/base.hwh" \
  --inventory "$E/before.json" --attestation "$E/attestation.json" \
  --output "$E/p0.json"
```

`E`, `METADATA_FILE`, exact service/driver identities and HTTP endpoints must be
set from the fresh audit. Never use placeholder paths as executed commands.
Use `umask 077`; choose a new evidence directory, not a previous run.

## Exclusive ownership and one supervised load

These are **operator-executed privileged operations after hardware approval**.
Use one interactive UART shell and `sudo -s`; authenticate there. Do not expose
credentials, change sudoers or assume authentication transfers across SSH sessions.
Keep a second read-only SSH observer if available. Stop immediately on any failed
condition. Do not use PYNQ Overlay/download, clock/reset MMIO or ps7_init.

1. Stop only the five identified services, recording each result. Historical
   stop order: Jupyter, bootstrap, web, runtime-activation, server. Confirm each
   inactive and its cgroup/processes empty. Do not stop SSH or networking.
2. Review every process mapping `/dev/mem` or `/dev/uio*`, DMA owners and bound
   platform drivers. Inspect `maps`, not only file descriptors. Unknown ownership
   means NO-GO. Do not kill broad process classes.
3. Historical UIO devices were `40000000.fabric` and
   `43c00000.audio-codec-ctrl`, driver `uio_pdrv_genirq`. Match names, addresses,
   sizes and current driver links before unbinding; never assume uio0/uio1.
   Record exact binding paths. For the confirmed pair ONLY:

```sh
printf '%s\n' 40000000.fabric > /sys/bus/platform/drivers/uio_pdrv_genirq/unbind
printf '%s\n' 43c00000.audio-codec-ctrl > /sys/bus/platform/drivers/uio_pdrv_genirq/unbind
```

4. Verify neither driver link remains. Verify original recovery firmware still
   matches the pinned SHA256. Copy candidate.bin to a **new unique** name under
   `/lib/firmware`, e.g. `plasma-swd04-d39e8519.bin`; refuse to overwrite. Rehash
   the staged bytes against kit candidate.bin and record the digest.
5. Preserve `dmesg`, clk_summary and manager state before loading. Require full
   configuration flags 0; review any other flags, do not change PS registers.
   Load **once**, recording command/time/result:

```sh
printf '%s\n' plasma-swd04-d39e8519.bin > /sys/class/fpga_manager/fpga0/firmware
cat /sys/class/fpga_manager/fpga0/state
```

6. Require operating, no configuration error/timeout or new kernel AXI error,
   FCLK0 enabled at 100 MHz, and reviewed reset/GP0 platform configuration.
   The HWH proves design connections, not live reset register state. Do not probe
   arbitrary PS registers to investigate a discrepancy. NO-GO if uncertain.
7. Only after this check create the phase-specific live session from the actual
   observations. It must bind P0 hash, BIT/HWH/BIN/recovery hashes, load-log hash,
   operator/ownership confirmations and stage. Required keys are defined in
   `live.require_live_session`. No automated attestation is provided.

## HIL-01 / HIL-02 / HIL-03 (stop on first failure)

Run each in a fresh process and save separate immutable JSON evidence. A blocked
physical AXI read can hang Linux despite Python polling/subprocess deadlines.
Do not repeatedly probe a failed address. CPU MMIO success is not observation
of physical AXI RRESP signals.

```sh
python3 -m pl.hil.swd04.live --stage HIL01 --p0-report "$E/p0.json" \
  --session "$E/session-HIL01.json" --candidate-bin artifacts/candidate.bin \
  --output "$E/hil01.json" --execute-live --ack-unrecoverable-axi-stall-risk
python3 -m pl.hil.swd04.live --stage HIL02 --p0-report "$E/p0.json" \
  --session "$E/session-HIL02.json" --candidate-bin artifacts/candidate.bin \
  --previous "$E/hil01.json" --output "$E/hil02.json" \
  --execute-live --ack-unrecoverable-axi-stall-risk
python3 -m pl.hil.swd04.live --stage HIL03 --p0-report "$E/p0.json" \
  --session "$E/session-HIL03.json" --candidate-bin artifacts/candidate.bin \
  --previous "$E/hil02.json" --output "$E/hil03.json" \
  --execute-live --ack-unrecoverable-axi-stall-risk
```

- HIL-01 reads 21 allowlisted words only: eight Identity words (MAGIC,
  version 0x100, ABI 1, flags 0 and four source Build ID words), old Control/
  Waveform defaults and new Transaction ABI/defaults. No writes.
- HIL-02: explicit line reset, DPIDR 0x2BA01477, ACK OK, DATA_VALID, one attempt,
  retained response stability and explicit acknowledgment.
- HIL-03: fixture-only unsupported write with half-period 65535, observed BUSY,
  explicit ABORT, ABORTED result, restore divider 2, explicit line reset and three
  successful DPIDR reads. The existing 10 ms hardware watchdog bounds the abort
  attempt. Linux scheduling can miss that BUSY window: STOP, record failure,
  restore base. Never accept TIMEOUT as ABORTED or retry until it passes.

## R0 restoration and emergency recovery

Run restoration whether HIL passes or fails, provided Linux/UART is responsive.
No more AXI probes after failure. Configure the verified original base.bin once
through FPGA Manager; never repeat candidate configuration automatically.

```sh
printf '%s\n' base.bin > /sys/class/fpga_manager/fpga0/firmware
cat /sys/class/fpga_manager/fpga0/state
```

Require operating and clean kernel log. Preserve metadata backup and compare
current bytes; raw FPGA Manager should not update them. If changed, stop consumers
and restore **only** the audited original files with original ownership/modes;
unknown new metadata needs review, not deletion. Rebind only the recorded original
pair after base is operating:

```sh
printf '%s\n' 40000000.fabric > /sys/bus/platform/drivers/uio_pdrv_genirq/bind
printf '%s\n' 43c00000.audio-codec-ctrl > /sys/bus/platform/drivers/uio_pdrv_genirq/bind
```

Restore the previously active services in this historical order: Jupyter,
server, runtime-activation, web, bootstrap. Confirm current status, UIO name/map/
size/driver links, metadata checksum, clock state and kernel errors. Verify
public-key SSH, Jupyter HTTP, Gateway live and ready using the audited endpoints.
Collect `after.json`, then run `pl.hil.swd04.restore --before ... --after ...
--evidence ... --output ...` with individually observed restoration assertions.
Do not mark overall HIL PASS before R0 PASS.

If configuration fails but Linux is responsive: STOP probes, preserve logs, try
one verified original base restoration. If that fails, or Linux/AXI/SSH hangs,
use the already verified UART. If UART/kernel is unresponsive, only the physically
present operator may disconnect/restore board power and verify normal SD boot,
base overlay, services and APIs. **Never auto power-cycle**, loop configuration,
or claim SSH can recover a kernel AXI hang. Power recovery capability is a
precondition; actual recovery success must be observed separately.
