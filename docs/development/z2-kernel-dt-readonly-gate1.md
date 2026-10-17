# Z2 Kernel / Device Tree read-only inventory — bounded Gate 1

**Status: Gate 1 implementation + synthetic validation; real Z2 collection NOT RUN unless a separate, current SWPC evidence bundle is produced. M1 = NO-GO.** This follows PR #1001 (Phase 2C; exact target Kernel build/source is still UNRESOLVED).

## Objective and scope

Use the operator-enrolled **real PYNQ-Z2** on SWPC, not `z2like` QEMU, to obtain a fresh boot-bound, non-invasive inventory of relevant Kernel, Device Tree and FPGA-management resource facts. Confirm what was actually observable, not what a public Xilinx 2024.1 source *might* do. **Never infer AXI drain, Kernel/DMA exclusivity, electrical IO safety, or source-to-binary lineage solely from sysfs presence or a Host test.**

`pl/tools/z2_kernel_dt_readonly.py` is a self-contained Python-3.11+ stdlib script. It only reads explicitly enumerated `/sys` and `/proc` paths with bounded byte counts. It does not SSH, run subprocesses, inspect `/dev`, mmap, send MMIO, write FPGA Manager, install packages, bind/unbind drivers, control clocks/reset/power or write a report. It prints one sanitized JSON document to stdout; the **caller** owns private evidence retention on SWPC.

Observation fields:
- UTC collection timestamp, kernel release, **SHA256 of boot ID** (not the raw ID), SHA256 of `/proc/version` (not the build-host string).
- Compressed and decompressed `/proc/config.gz` hashes, selected FPGA/UIO compile flags, with missing config explicitly marked `UNAVAILABLE`.
- Device Tree model/compatible, optional `/sys/firmware/fdt` SHA256 (a byte snapshot only; not proof of active overlays), FPGA Manager state/driver/DT compatible/syscon property digest.
- FPGA Region driver and hashed `fpga-mgr`/`fpga-bridges` DT properties; FPGA Bridge class entries (null=unavailable, []=empty snapshot); UIO mapN physical `addr/size/offset` and bound driver.
- **Permanent `M1 NO_GO` flags**, unresolved exact Kernel binary/source/patchset, no AXI drain attestation. Status remains NOT_ATTESTED even on apparently matching resource names.

`pl/tools/runtime_fpga_phase1.py` remains the canonical independent UIO/resource candidate analyzer. An inventory snapshot is **not** an atomic owner audit. Host-only regression tests use fake roots; they have no physical access.

## SWPC Codex autonomous assignment (owner-approved READ-ONLY scope)

> **A Codex task packet is not evidence of execution**. This repository workflow cannot itself make an SSH connection to the owner's private SWPC/Z2 network. A hardware-connected Codex instance must actually execute it. Use only existing authorized access and the existing private credential store per `AGENTS.md §1B`.

```text
PLASMA / GATE 1 / Z2 KERNEL-DT READ-ONLY / EXECUTE

Read AGENTS.md and docs/development/z2-kernel-dt-readonly-gate1.md.
The owner approved this limited read-only inventory Gate 1. Do NOT request
a duplicate hardware approval. Use SWPC, the existing locally enrolled
real PYNQ-Z2 identity and the private SSH credential store; do not guess
the Z2 IP, paste secrets into commands or confuse it with QEMU.

Read-only repo check: resolve main/current task branch, inspect local
uncommitted changes without overwriting them. Check SSH reachability with
the enrolled target only. Feed the Python source via SSH stdin to
`python3 -`; **do not copy/install files to the board**. Do not use
sudo unless already authorized and genuinely needed for this read-only
scope; do not modify permissions or sudoers.

From the approved checkout containing this script, run its contents
on the remote board with the existing authorized SSH mechanism
(equivalent to: ssh -T <ENROLLED_Z2> 'python3 -' <
pl/tools/z2_kernel_dt_readonly.py). Command text uses a placeholder,
not a literal hostname/IP or a request to reveal credentials.

Privately retain command, UTC timestamp, tool commit, exit status,
sanitized stdout, redacted stderr, SHA256 manifest in a new owner-only
SWPC .work/ directory. No public raw board identifiers, passwords,
network endpoints or operator data.

Validate target identity from enrolled board and actual Kernel/DT
observations (NOT from a synthetic JSON field), compare freshness and
facts with prior Issue #975/#977 records and pinned Phase 2C public
reference. Missing /sys/firmware/fdt, config.gz, source/patchset or
FPGA Bridge is UNKNOWN/UNAVAILABLE unless direct read-only facts prove
otherwise. Do not equate booted DT, DT base blob and overlays.

STOP if board identity/host is uncertain, SSH/credentials unavailable,
collect command fails, the board looks unlike expected PYNQ-Z2, or
privileges/hardware mutation would be needed. Do not run HIL, load
FPGA, access MMIO, restart anything, operate DUT/LA/USB Hub, modify
PR #972, merge or deploy.

Report VERIFIED / UNKNOWN / BLOCKED for each observation, the raw
evidence location (private SWPC), actual exit code, SHA256 manifest,
Kernel/DT/source limitations and next measurable AXI/ownership
qualification. Keep M1 NO-GO and Gate 2 separate.
```

## Independent offline verification (this PR's actual CI scope)

```sh
python3 -m pytest -q \
  pl/tests/test_z2_kernel_dt_readonly.py \
  pl/tests/test_runtime_fpga_kernel_lineage.py \
  pl/tests/test_runtime_fpga_m1_gate.py \
  pl/tests/test_runtime_fpga_phase1.py
```

Tests cover realistic Kernel config, DT, Manager/Region/Bridge, UIO fixtures;
boot-ID/privacy redaction; missing mandatory attributes; optional unavailable
state; malformed gzip, symlink escape, oversized input and no file mutation.

**Not authorized or claimed:** Live Z2 already PASS; exact booted binary
digest; full source+patchset/DTB provenance; readback of AXI/SLCR;
quiesced PL AXI transactions; noncooperating process/DMA exclusion; actual
Bridge isolation; electrical or UART/power recovery. Source and Kernel
claims remain **UNKNOWN** until authenticated primary evidence exists.

Stop at a distinct **Gate 2 merge approval** for this PR; no deployment,
hardware writes or PR #972 modification.
