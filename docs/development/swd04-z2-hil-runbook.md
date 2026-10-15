# SWD-04 — Z2 PS→AXI→PL Internal DPIDR HIL Runbook

**Status:** initial SWD-04 merged as PR #917; this remains host-only
preparation. Hardware execution requires a separately authorized maintenance
window. See the [offline execution checklist](swd04-offline-execution-checklist.md)
for verified staging commands, missing-recovery NO-GO and current HIL procedure.
No SWD-04 physical qualification is claimed.

## Provenance and scope

- SWD-03 source commit:
  `d39e85194f27e20f0ae7f2eb7c0623b293ff1108`;
  integrated in `main` via PR #907.
- Candidate Vivado 2026.1 host build:
  `pl/build/z2-swd03-axi/run.4v3Q4ntG/` in the archived isolated SWPC
  worktree, 2397 LUT, 2128 FF, setup WNS +0.345 ns, hold WHS +0.022 ns.
  Exact checked-in immutable hashes:
  - BIT: `80e8a6ef0c86ac000f9f0b16af2ee25ba3f6f1bb61dd3f3e7ab232508bc4c38b`
  - HWH: `96ce1767ec2ca1ec4c45aaa0cdb4b674bd8349f5753e3f35728d18cf646843bc`
- Recovery is the **previous known-good PYNQ base** from HIL-PSPL-01:
  - `base.bin` SHA256 `c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c`
  - `base.hwh` SHA256 `222898ef2c0ccc4a0c47608e99d8dc7c9c6cdfed5130964884ff35005827ef3a`
- Source reference: `docs/evidence/hil-pspl-01/2026-10-14-pynq-z2/`.
  It proves *one historical identity-only* load, MMIO readback and restoration,
  not SWD-04 HIL qualification.
- Target: the same real PYNQ-Z2 ARMv7 Linux/PYNQ 3.1.1, internal DPIDR-only
  fixture, PS GP0 at 100 MHz. No external SWD pin, cable, IC, voltage or
  programmable target. **Only a single Site proof of transport**.

## Human and automation trust boundary

Per `AGENTS.md`, engineering merge and hardware authorization must follow the
approved scope. The initial SWD-04 PR #917 is merged. The current staging task
is host-only: merge status alone does not authorize a new hardware operation.
Use the current execution checklist and obtain the separately scoped maintenance
authorization before target access.

A software/JSON PASS can be fabricated and cannot independently prove a
physical UART cable, a power switch or that every former MMIO mapping has
been released. The operator is accountable for these conditions on site.
A `/proc/*/fd` snapshot is insufficient to rule out live kernel drivers or
retained `mmap` regions. Do not infer exclusivity from a quiet network or
the absence of an open `/dev/uio*` handle.

`pl/hil/swd04/live.py` is inert without the exact two live flags, a root
ARMv7 platform, hardware/session evidence, a staged BIN hash, an operating
FPGA Manager and prior phase evidence. **It never loads firmware** and it
never shuts down or restarts services, and provides no automatic rollback.

## Isolated software staging on Z2 (post-Gate-2 only)

Do not install this HIL tool into the running Plasma PPU Python environment,
alter the PYNQ system packages, or use the existing Jupyter kernel as the
test process. Stage the exact reviewed `pl/hil/swd04/` source into an isolated
read-only source checkout/location, record its source SHA, and run with a
Python version >=3.10. `python3 -m pl.hil.swd04.<command>` requires the
repository root on `PYTHONPATH` (or an equivalent isolated package staging).
The read-only collector's `/sys/kernel/debug/clk/clk_summary` access
may require approved privileges; **missing clock evidence is NO-GO**.
The live MMIO process is an intentionally separate privileged invocation,
not a persistent service or PYNQ Overlay consumer.

## P0 — immutable artifact and read-only environment preflight

After Gate 2, **before any modification to Z2**, create a fresh isolated
evidence directory on a trusted host; do not store credentials or sensitive
raw host inventories in a public PR.

1. Inspect current platform identity, Linux/PYNQ version, FPGA Manager,
   FCLK0/GP0, UIO name/map/driver and PYNQ overlay ownership.
2. Verify required Gateway/Jupyter/Plasma services are active and record
   service/socket/driver state. Confirm no unexpected MMIO or DMA users.
3. Verify the exact candidate BIT/HWH and the known-good base BIN/HWH
   SHA256 above, with separately retained originals. Review the full HWH
   and the original metadata backup. Do not rely on a filename.
4. Confirm physical UART access and independently controlled power
   recovery are **actually available**; verify the supervised service/driver
   release/restoration plan, maintenance window and absence of external DUT.
5. Use read-only collector. On the Z2, **after authorization and while no
   hardware changes are underway**, a suitable operator can invoke:

```bash
python3 -m pl.hil.swd04.collect \
  --metadata-file /path/to/current/pynq-overlay-metadata \
  --output /path/to/private-evidence/preload-inventory.json
```

The collector reads sysfs, device tree, clock-summary and systemctl status
and hashes metadata **without serializing metadata contents**. FCLK0 name/
clock-summary layouts vary by kernel. Unknown or unreadable evidence is a
NO-GO, not an excuse to guess 100 MHz. UIO is matched by **name and physical
address**, never by `/dev/uioN` index.

Use `pl.hil.swd04.preflight` on a trusted isolated host with copies of the
real candidate, manifest, recovery files, this inventory and an independently
reviewed operator attestation:

```bash
python3 -m pl.hil.swd04.preflight \
  --bit /retained/SWD03/artifacts/plasma-z2-swd03-axi-fixture-0.1.0.bit \
  --hwh /retained/SWD03/artifacts/plasma-z2-swd03-axi-fixture-0.1.0.hwh \
  --manifest /retained/SWD03/artifacts/manifest.json \
  --recovery-bin /retained/known-good/base.bin \
  --recovery-hwh /retained/known-good/base.hwh \
  --inventory /private/preload-inventory.json \
  --attestation /private/operator-attestation.json \
  --output /private/p0-report.json
```

The attestation schema is version 1. The operator must individually confirm:
`exclusive_pl_ownership_confirmed`, `uart_console_verified`,
`independent_power_recovery_verified`,
`maintenance_window_confirmed`, `restoration_operator_ready`,
`no_external_dut_connected`, `original_metadata_backed_up` and
`uio_driver_reconciliation_planned`. Do **not** create a script that
automatically writes `true` to these fields.

A P0 PASS **does not grant live hardware authorization**. It only establishes
that the provided artifact/snapshot/attestation values satisfy the offline
contract. A real operator must approve the load/no-go decision at the
maintenance window.

## Staging, exclusive ownership and supervised candidate loading

**Post-Gate-2 only.** Use a separately reviewed Xilinx-qualified BIT→BIN
conversion for Zynq-7000; do not pass the Vivado `.bit` directly to FPGA
Manager or assume its format is accepted. SHA256-check the new `.bin`, record
source BIT hash, conversion tool/version and conversion log. The converted
BIN has its **own** hash; BIT SHA256 is not interchangeable with BIN SHA256.

Before configuring PL, verify no old PL-backed UIO/DMA/AXI resource is still
owned by a service, process or kernel driver. This may require carefully
scheduled service quiescence and driver unbinding. Preserve exact current
metadata/firmware checksums, device bindings and clock/service snapshots.
Do **not** call PYNQ `Overlay(..., download=True)` blindly; it may change
clocks, shutdown IP and XRT state.

Load the reviewed candidate using a **supervised FPGA Manager procedure**
specific to the installed kernel. Capture the original configuration method,
the exact firmware filename/digest, start/end kernel messages, FPGA Manager
`operating` state and owner reconciliation. Do **not** execute `ps7_init`,
generated PS7 init scripts, DDR reinitialization or arbitrary PS register
writes. Never rely solely on the FPGA Manager `operating` flag to prove the
intended candidate's identity.

A **stage-specific** live session JSON must contain:
`stage` (HIL01/HIL02/HIL03), `candidate_source`,
`candidate_bit_sha256`, `candidate_hwh_sha256`,
`recovery_bin_sha256`, `candidate_bin_sha256`,
`supervised_load_log_sha256`, `p0_sha256`, plus explicit `true` for
`confirmed_after_gate2_merge`, `live_fpga_manager_load_supervised`,
`candidate_bitstream_loaded_and_verified`,
`original_services_quiesced_for_pl_access`,
`all_prior_pl_consumers_isolated`,
`uios_unbound_or_ownership_reconciled`,
`uart_console_verified`, `independent_power_recovery_verified`,
`no_external_dut_connected`, `operator_present_at_console` and
`original_metadata_backup_verified`.

These assertions are **not** proof of external conditions by themselves.
Never reuse an earlier session after reloading another image or changing
the Z2 runtime state.

## HIL-01/02/03 — one stage per explicit supervised invocation

The separate phases use a hard-coded 32-bit aligned MMIO whitelist.
There is no CLI parameter to select arbitrary physical addresses.

- **HIL-01:** `/dev/mem` read-only; Identity words and known reset values
  from the four 4 KiB AXI segments. No register writes.
- **HIL-02:** only SWD-03 `COMMAND`=START/ACK,
  `CONFIG`=line-reset / DP-read. Verify 0x2BA01477, ACK, data-valid,
  response retention and explicit consumption.
- **HIL-03:** optional, only after HIL-02. An internal-fixture DP-write
  request is aborted in flight; verify ABORTED and line-reset recovery,
  three subsequent DPIDR reads. This does NOT clear unknown physical
  target effects and is forbidden with an external DUT connected.

After separately creating a valid stage-specific live session and staging
all evidence on Z2, the operator invokes the phase explicitly:

```bash
sudo python3 -m pl.hil.swd04.live \
  --stage HIL01 \
  --p0-report /private/p0-report.json \
  --session /private/hil01-session.json \
  --candidate-bin /private/approved-swd03.bin \
  --output /private/hil01-result.json \
  --execute-live \
  --ack-unrecoverable-axi-stall-risk
```

For HIL-02 and HIL-03, include `--previous` with the preceding stage
PASS result, use a *fresh* stage session and a *new* output path.
HIL-01 MUST be successful before HIL-02; HIL-02 before HIL-03.

**CRITICAL:** Python poll limits only bound repeated successful MMIO reads.
They **cannot interrupt a blocked AXI read/write or unhang the ARM/Linux bus**.
A failing or stuck access means no more probing or automatic retry.
Use out-of-band UART/power and a supervised known-good recovery path.

## R0 — restore exact known-good base image

After HIL (including partial failure where Linux remains responsive):
1. End the exclusive MMIO session. Restore known-good `base.bin` using
   a supervised FPGA Manager procedure; verify the exact recovery hash.
2. Restore the original PYNQ metadata and reconcile UIO driver bindings.
   Never assume `uio0` still refers to the same resource.
3. Restore any services changed for isolation, then verify UART/SSH,
   Jupyter HTTP, Gateway liveness/readiness, FCLK0, and kernel errors.
4. Recollect the same read-only inventory including the original metadata
   hash, using `pl.hil.swd04.collect`.
5. Compare before/after inventory and independent observed restoration
   evidence with `pl.hil.swd04.restore`. Missing observations are NO-GO.

```bash
python3 -m pl.hil.swd04.restore \
  --before /private/preload-inventory.json \
  --after /private/restored-inventory.json \
  --evidence /private/observed-restoration.json \
  --output /private/restoration-acceptance.json
```

Required restoration observations: base.bin loaded/operating, candidate
unloaded, UIO reconciliation, SSH, Jupyter, Gateway live/ready, no new AXI/
FPGA kernel error and no PS7/DDR reinitialization. Keep the original raw
evidence private and publish only reviewed/hash-addressed derivatives.

If SSH/PS is stuck, do **not** send further MMIO probes. The out-of-band
UART console and independent power route must be physically ready beforehand.
The scripts neither perform nor silently promise emergency recovery.

## Acceptance semantics

| Tier | Meaning |
|---|---|
| `SWD04_HOST_SAFETY_TESTS_PASS` | Synthetic code, gating and negative-test PASS only |
| `SWD04_P0_OFFLINE_PASS_NO_HARDWARE_ACTION` | Approved artifacts + supplied readiness evidence checked; no live grant |
| `SWD04_HIL01/02/03...PASS` | Requires separately executed real Z2 MMIO and stage evidence |
| `SWD04_RESTORE_OFFLINE_EVIDENCE_PASS` | Post-operation evidence consistent with original overlay restoration |
| SWD-04 overall HIL PASS | Only after accepted real HIL phases **and** verified R0 restoration |
| Physical SWD / Real IC programming | Always `NOT_RUN` in this stage |

No GitHub-hosted or SWPC Host-only test may be reported as real Z2 HIL.
Existing archived artifacts, `NA/`, worktrees and prior Build runs are
immutable evidence and must not be cleaned to produce a green check.
