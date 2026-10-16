# MMIO-MS-01 — Dual-Site PS/PL concurrency and resource benchmark

Status: **Gate 1 implementation candidate, NOT real hardware PASS**.
Root contract: AGENTS.md. The closed LinuxMMIO v1.1 LT02 Site-1 real
HIL remains unchanged.

## Candidate hardware

Independent source: pl/projects/z2-ms01-axi, Vivado 2026.1. Six GP0
apertures: identity_0 0x40000000, control_0 0x40001000,
swd_0 0x40002000, transaction_0 0x40003000,
lt02_0 0x40004000 (Site 1), lt02_1 0x40005000 (Site 2).
Each LT02 block owns an independent 2 KiB scratchpad and hardware
read/write counters. No external PL IO, DUT, SWD, power or reset pins.

The new BIT/HWH/manifest must prove exactly six disjoint 4 KiB apertures,
100 MHz FCLK0, synchronized reset, no external PL IO and clean implemented
timing/DRC. Hash BIT/HWH/manifest, independently inspect an exact BIN
conversion and retain known-good base.bin before loading real FPGA.

## PS execution modes

- thread: shared production LinuxMMIO owner, one dedicated Site lease,
  LoopTestDriver and worker thread per Site.
- process-ipc: child producer/validator processes exchange real payload
  bytes with the parent PPU MMIO owner over duplex Pipes. Each Site has
  an independent parent server thread and LoopTestDriver. This measures
  IPC overhead and Python process scheduling, not direct child MMIO.
- process-direct: NOT IMPLEMENTED/NOT RUN. Existing LinuxMMIO exclusive
  inter-process flock forbids competing owners. Do not bypass it using
  alternative lock paths. First design safe per-aperture cross-process
  claims together with a global FPGA reload-exclusion protocol.

On dual-core Cortex-A9, software workers do not imply physical CPU cores.
Production LinuxMMIO serializes native 32-bit calls under a short RLock.

## Measurements

Use equivalent payload/iteration matrices (start at 2, 8, 64 KiB), identical
per-Site deterministic payloads, byte/CRC verification and DATA hardware
counter deltas. The current benchmark includes cold process-start overhead;
do not present it as pure FPGA AXI bandwidth.

The PS benchmark exports wall seconds, total bytes, effective MiB/s,
DATA word operations/s, latency p50/p95/p99/max, average process-tree CPU
utilization (100%=one core), machine-normalized CPU%, sampled peak CPU%,
peak aggregate RSS, peak PSS if Linux permits it, and per-Site counters.
save_reports persists JSON, CSV and five SVG comparison charts in a new
unique output directory.

RSS aggregates can double-count shared pages; PSS is preferred when
available. A null means it was not measured. Peak samples are limited
by 100 ms resolution. CPU includes parent and child process usage.
No automatic retries after uncertain MMIO failures.

## Gate 1 acceptance plan

1. Host Python 3.12 tests: benchmark, independent dual-site HWH fault
   injection, LinuxMMIO regression and production LoopTestDriver.
2. Vivado: new isolated SWPC build under pinned board files and source,
   preserve clean timing/DRC/BIT/HWH/manifest evidence.
3. Real Z2 preflight: bound artifact SHA, current image load receipt,
   known-good base.bin, ARMv7 CPython 3.12.13, 100 MHz FCLK0 and
   non-overlapping kernel/driver/userspace MMIO ownership.
4. Real dual-Site: compare one Site vs two Sites in thread/process-IPC,
   byte-level checks, independent DATA counters and per-Site isolation.
5. Independently restore exact original FPGA image and verify clock,
   HWH, UIO, kernel, services, SSH and HTTP before full HIL PASS.
6. Direct multiprocess and 4/8 physical Site extension must be reported
   NOT RUN until explicit hardware and ownership implementations exist.

This repository's GitHub Actions run host-only tests. They are not
evidence of real Z2 HIL, FPGA load, Direct MMIO processes, production
programming, or physical eight-Site behavior.

**No Gate 2 merge without a separate explicit owner approval.**


## Dual-Site live entrypoint (not a programming command)

The guarded runner is pl.hil.ms01.native. It is inert without explicit
--execute-live and --ack-unrecoverable-axi-stall-risk flags. An authorized
external SWPC supervisor must first build/verify the exact six-aperture
candidate, convert BIT to a reviewed BIN, reconcile ownership, load the
candidate via FPGA Manager, and record a root-owned current-boot receipt
using --record-loaded-image. Before the runner, confirm and preserve
original PYNQ base.bin/base.hwh. Do not reuse LT02-05 five-aperture
load receipts or HWH files.

The runner independently requires:
- --manifest / --bit / --hwh / --candidate-bin
- --recovery-bin / --recovery-hwh / --receipt / --output
- --expected-manifest-sha256 / --expected-candidate-bin-sha256
- --execute-live and --ack-unrecoverable-axi-stall-risk

Optional bounded matrix: --iterations N, --trials N (1..3), and
--payload-sizes 2048 8192 65536. The default is three trials, 1-Site
and 2-Site, Thread and Process-IPC, three payload lengths = 36 runs.
Each run captures cold end-to-end wall/CPU/RAM, full data CRC and actual
LT02 hardware counter deltas. Repeat trials are NOT long-term reliability
qualification. The runner does not estimate unmeasured bus throughput.

Result status MS01_REAL_DATA_CASES_PASS_RECOVERY_NOT_RUN is NOT full HIL
PASS: the independent supervisor still must restore original base.bin
and independently reconcile HWH/UIO/services/HTTP/clock/kernel/SSH.
On SIGBUS/AXI stall a started.json alone is NOT PASS. No automatic replay.

Process-Direct and 4/8 physical Site experiments remain distinct
NOT RUN stages; do not reinterpret Thread or Process-IPC results as proof
of direct parallel AXI bus masters.
