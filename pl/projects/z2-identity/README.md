# PYNQ-Z2 Identity-only PS/PL qualification

This variant reuses `pl/rtl/bus/pl_identity_axi_lite.sv` without enabling EMIO
or exposing external PL I/O. The existing `z2-swd-gpio` project and its default
Identity parameters remain unchanged. This is an AXI identity experiment,
not programming support or a qualified appliance bitstream.

## Hardware contract

PS M_AXI_GP0 and the AXI interconnect use PS FCLK0 at 100 MHz. PS
FCLK_RESET0_N enters the active-low `proc_sys_reset` input; synchronized
peripheral reset drives AXI/Identity. PS DDR/FIXED_IO remain dedicated PS
interfaces, not programmable DUT I/O. No SWD bridge, GPIO EMIO or PMODB ports
are present. There is no target power control.

Vivado explicitly assigns a 4 KiB segment at `0x40000000`; generated BD and
HWH must confirm the assignment. Strict RTL compares the full physical address
above bit 4, rejects unaligned accesses and offsets outside the first 32 bytes,
and rejects all writes with SLVERR. AXI interconnect handles accesses outside
its aperture. Legacy SWD builds retain their original decoding defaults.

| Offset | Value |
|---|---|
| 0x00 | MAGIC `0x504C534D` |
| 0x04 | SemVer `0x00MMmmpp`; 0.1.0 = `0x00000100` |
| 0x08 | ABI 1 |
| 0x0C | Capability flags 0 (no SWD) |
| 0x10..0x1C | Git SHA prefix, four hexadecimal words in order |

## Host-only verification/build

```bash
python3 -m pytest -q pl/tests
python3 -m pytest -v pl/verification/test_z2_swd_gpio_rtl.py pl/verification/test_z2_identity_rtl.py
PLASMA_BOARD_REPO=/path/to/pinned/board-repository \
  bash pl/projects/z2-identity/build-on-swpc.sh
```

Simulation requires Icarus, cocotb 1.9.2 and cocotb-test 0.2.6 (the existing
CI versions). Build requires clean committed sources, Vivado 2026.1, and the
existing pinned board repository at `e02d6a3866b5465218f777168cdc51344ac94e07`.
A supplied cache is only read. Each build gets a fresh `pl/build/z2-identity/run.*`
directory; previous outputs and all `z2-swd-gpio` artifacts are preserved.
The build never contacts Z2, loads FPGA, runs generated `ps7_init`, or changes
Linux services. `VIVADO_SETTINGS64`, `PLASMA_VIVADO_JOBS` and
`PLASMA_BITSTREAM_VERSION` are configurable.

Artifacts include .bit/.hwh, a manifest, SHA256 sidecars, timing/DRC/methodology
reports and the full Vivado log. Finalization checks HWH capability flags,
strict decoder/base, aperture, GP0, EMIO disable and PS clock parameters.
A build PASS is distinct from warning disposition and loading safety. Review
all critical warnings, including the pinned preset's PSU-1..4 DDR warnings;
never initialize DDR on the running Linux system using generated PS7 scripts.
Manifest `loading_safety=NOT_QUALIFIED` and `physical_hil=NOT_RUN` remain truthful
until separately authorized and observed real-board acceptance.

## Platform safety and recovery boundary

Do not run `Overlay(...)` with its default download behavior during an audit.
The installed PYNQ loader can configure PL clocks before FPGA programming,
request shutdown through existing MMIO, set AXI port widths, use XRT, and
replace shared overlay metadata. Raw FPGA Manager loading avoids some PYNQ
metadata actions but does not establish correct clocks/reset or reconcile
existing software users. Neither path is approved here.

Before a future load, identify the current overlay and its hardware consumers,
Jupyter kernels, UIO mappings, open `/dev/mem`/UIO handles and shared PYNQ state.
An open-file inventory is a snapshot; a closed fd can leave a live mmap.
A candidate load must not leave old drivers or mappings accessing replaced IP.
Define how FCLK0/reset will be established without DDR/PS reinitialization.
UIO mappings must match the candidate HWH; do not assume an old `fabric` device
has Identity semantics because the base address matches.

Recovery must identify a known-good .bit/.hwh pair plus SHA256, compatible
loader and software/driver restoration. FPGA configuration errors do not
promise automatic rollback. Invalid/stalled AXI transactions can prevent a
process, SSH, or Linux from recovering; a userspace timeout is not a bus timeout.
Clock changes, reset sequencing and stale DMA/AXI users can also lose SSH.
Before loading, require an independently accessible serial console and an
operator-controlled power recovery path; assess JTAG as an additional recovery
route. This preparation does not authorize reboot, power cycling, service
stops or FPGA loading. If recovery requires any of those, it must be explicitly
included in the future approved hardware plan.

## Read-only platform audit (2026-10-14)

The audited target runs Linux 6.6.10 on ARMv7. The installed PYNQ environment
reports **3.1.1**, rather than the assumed 3.0. Source review found that
`Overlay.download()` sets PL clock divisors before delegating to the device.
`EmbeddedDevice.download()` requests old-IP shutdown, generates metadata,
writes FPGA Manager flags/firmware, sets AXI port width and invokes XRT.
`Device.shutdown()` may write shutdown-manager MMIO based on global state.
No generated PS7 DDR initialization is called in those inspected functions;
this is not proof that every loader/XRT side effect is safe. Do not run
`ps7_init` or reapply a DDR preset to a running Linux system.

FPGA Manager reported `operating`. Cached metadata contains `base.hwh`; no
`global_pl_state_*.json` was present. Cache filenames do not authenticate the
currently loaded FPGA binary or establish exclusive ownership. Jupyter and
Plasma services were running and were left untouched. A sudo snapshot scanned
process fds and maps for `/dev/mem`, `/dev/uio*`, `/dev/dri*`, `/dev/xlnk` and
`/dev/xdevcfg` and found no matches. This does not exclude kernel drivers,
subsequent accesses or use outside those device paths.

The existing UIO resources were `audio-codec-ctrl` and `fabric`. The latter
uses the same base as this candidate but belongs to the existing design; it
must not be reused without reconciling ownership and its device-tree contract.
The GPIO controller exposes 118 lines; GPIO registers were not accessed.
Identity-only removes all EMIO/PMODB connections, so no SWD GPIO default-state
assumption is needed for this candidate. This does not make replacement of
other existing PL peripherals safe for their drivers/users.

The pinned preset retains DQS-to-clock values -0.051, -0.006, -0.009 and
-0.033. PSU-1..4 were observed in the historical SWD build. Retaining these
HWH parameters is not a request to reinitialize DDR, and PL timing does not
qualify them. Review warning applicability against the actual board/boot PS
configuration before any future loading scope; do not change the values merely
to remove warnings.

Known-good recovery candidates are the existing base .bit/.hwh and converted
base.bin. Read-only SHA256 values were:

```text
base.bit 3239e9cc37ee4993c25f02ae6c97da0b3372f0e722e267d10073e20adc5d6717
base.hwh 222898ef2c0ccc4a0c47608e99d8dc7c9c6cdfed5130964884ff35005827ef3a
base.bin c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c
```

These digests identify files only. Recovery has not been executed or qualified.
A future hardware plan must confirm the pre-load image, preserve matching
metadata/driver state, and obtain exclusive ownership. If configuration fails
while PS remains responsive, stop all AXI probes and use an approved reload of
the known-good pair plus metadata/driver reconciliation. If PS/SSH hangs, avoid
repeated probes; use the independent serial console, then an explicitly
approved power/JTAG recovery route. Serial, physical power control and JTAG
availability remain **unverified requirements**, not available capabilities.
Loading remains NO-GO until these requirements and warning review are resolved.

Vivado 2026.1 also reports BD 41-702 because the pinned preset marks
`PCW_M_AXI_GP0_FREQMHZ=10` with USER strength. That property is read-only:
an attempted explicit assignment was rejected with BD 41-737 and is not used
in the final source. The actual GP0 ACLK HWH port is connected to FCLK0 with
`CLKFREQUENCY=100000000`, confirmed by implemented timing. Artifact validation
checks that physical connection instead of pretending to repair the preset's
annotation. The preset and live PS registers remain unchanged.
