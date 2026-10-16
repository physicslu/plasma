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

## Six-aperture supervisor (host-verified; real execution NOT RUN)

`pl.hil.ms01.supervisor` is a dedicated local Z2 supervisor, separate from
both the data runner and the historical five-aperture orchestrator. Its
**default is dry-run**: verify the pinned plan, source bundle, artifacts and
full BIT-to-BIN payload; print `hardware=NOT_RUN`; create no journal, acquire
no control lock and touch no hardware. This remediation authorizes only
host verification, not staging or invoking its live path on Z2.

The shared ownership audit retains LT02's five-aperture default; MS01 supplies
`0x40006000` as the exclusive end. It reads every process's maps independently
of fd presence and compares `/dev/mem` physical offsets plus VMA length.
UIO offsets are map selectors: physical ownership comes from **all** sysfs
UIO maps. Unknown UIO, malformed/inaccessible inventories and retained sixth
aperture mappings reject admission. Full reconfiguration also checks GP0 PL
resources through `0x80000000`, including the original audio driver; no active
UIO users are admitted even during the pre-unbind audit. These snapshots and
advisory locks cannot exclude a privileged, noncooperating process racing a
check; the dedicated development-board contract still applies.

### Reviewed plan and separate source versions

Build source and runtime source are independent. Preserve the existing BIT,
HWH, manifest and converted BIN; PS-only changes require no Vivado rebuild.
A plan JSON contains these required fields:

```json
{
  "fpga_source_sha": "404d2ef0152c50e9b2d6599f093752064198e895",
  "manifest": "/ABSOLUTE/PINNED/manifest.json",
  "bit": "/ABSOLUTE/PINNED/candidate.bit",
  "hwh": "/ABSOLUTE/PINNED/candidate.hwh",
  "candidate_bin": "/ABSOLUTE/PINNED/candidate.bin",
  "recovery_bin": "/ABSOLUTE/PINNED/base.bin",
  "recovery_hwh": "/ABSOLUTE/PINNED/base.hwh",
  "manifest_sha256": "b816dc86b4d74b29c31862a7f656fd2ebdd98de3af24f83d07655c5dfeeff6a2",
  "candidate_bin_sha256": "6027531ac1a3235484aad26c18fc02a60de04e9d7b489b54a710170d054aa9ab",
  "recovery_bin_sha256": "c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c",
  "recovery_hwh_sha256": "222898ef2c0ccc4a0c47608e99d8dc7c9c6cdfed5130964884ff35005827ef3a",
  "iterations": 8,
  "trials": 3,
  "payload_sizes": [2048, 8192, 65536],
  "worker_timeout_s": 900,
  "health_urls": {
    "gateway_live": "http://127.0.0.1:18080/api/health/live",
    "gateway_ready": "http://127.0.0.1:18080/api/health/ready",
    "bootstrap": "http://127.0.0.1:18081/v1/health",
    "jupyter_login": "http://127.0.0.1:9090/login",
    "jupyter_api": "http://127.0.0.1:9090/api"
  }
}
```

Replace the absolute paths with verified retained files and use the target's
actual existing health URLs. The helper
`seal_plan(template_dict, Path('new-plan.json'))` runs **on the host after
committing**: it rejects modified/untracked runtime Python, adds the exact
`runtime_source_sha` and `runtime_files` SHA256 map and returns the complete
plan's SHA256. Review/pin that digest. Never fill provenance using invented
values. Preserve the source bundle; a target need not have a Git checkout.

Host-only validation command (substitute the returned digest):

```bash
PYTHONPATH=software/python python -m pl.hil.ms01.supervisor \
  --plan new-plan.json --expected-plan-sha256 REVIEWED_PLAN_SHA256 \
  --output NEW_UNIQUE_JOURNAL_DIRECTORY
```

No current-boot candidate receipt is required before a candidate load.
Only a separately authorized live invocation with **both** `--execute-live`
and `--ack-unrecoverable-axi-stall-risk` can proceed. It additionally requires
the qualified ARMv7 Python 3.12.13, root-protected inputs/runtime, a healthy
original base image, enabled 100 MHz clock, local HTTP/services, exact hashes,
current ownership and original bindings. No service restart, metadata rewrite,
sudoers change, SSH credential handling or clock change is implemented.

### State machine, restoration and failure boundary

The configuration lock spans the experiment. The production global
`/run/lock/plasma-mmio.lock` is held during preflight/load/restore, then closed
before the production data runner acquires that **same** lock. The runner
never uses an alternative owner lock. Its existing exclusive lock, six-range
allowlist, native aligned word accesses and LoopTestDriver remain unchanged.
A competing owner blocks restoration; it is never killed or bypassed.

Each mutation has a preceding fsync'd immutable checkpoint:
`PREFLIGHT -> UNBIND_INTENT -> LOAD_INTENT -> CANDIDATE_LOADED ->
WORKER_INTENT -> TEST_DONE -> RESTORE_INTENT -> ORIGINAL_LOADED ->
REBIND_INTENT -> RECOVERY_VERIFIED`. Original driver bindings (including
originally unbound devices) are recorded before changes. Only the two known
platform devices with `uio_pdrv_genirq` may be reconciled. A fresh guard admits
no kernel owners before loading either image. The candidate is staged to a
unique firmware filename and its current-boot receipt is recorded only after
an observed new FPGA Manager load. The worker uses `pl.hil.ms01.native` and
production LinuxMMIO, never a live mock.

Ordinary load/data errors attempt exact original restoration without replaying
the data test. Loader and worker children inherit the configuration lock;
loader children also retain the MMIO exclusion if the parent dies. Durable
child completion records, PID/start-time identity and current-boot checks are
required before recovery. After a supervisor crash, **explicit**
`--recover-only` with the original output directory, exact plan digest and
both live flags resumes restoration; it never starts another benchmark.
A rebind failure records FAIL, attempts the remaining original bindings and
allows a later explicit repair without another load when restoration was
already established. A recovery load failure leaves drivers unbound and
reports `RECOVERY_FAILED`, without pretending that the original image is live.

Restoration is verified from a fresh independent observation, rather than a
loader exit code: base load identity, manager state/flags, same boot, metadata
hashes, exact UIO maps/bindings, clock, services/PIDs, HTTP and kernel delta.
Raw child stdout/stderr, immutable state files, receipt, native results and
post-recovery snapshot are retained. A failed data test stays FAIL even when
recovery succeeds. This local verifier cannot prove remote SSH reachability:
the authorized SWPC observer must separately verify SSH and HTTP before an
overall real HIL PASS. Real UIO/FPGA/load/restore behavior remains NOT RUN
until that hardware phase actually executes.

**AXI stall is outside software recovery guarantees.** Timeout, signal death
(including SIGBUS), surviving child, or absent durable completion means
`EXTERNAL_RECOVERY_REQUIRED`, AXI safety UNKNOWN. Stop subsequent MMIO,
reconfiguration and rebind; never retry the benchmark or assert that killing
Python released the AXI bus. The supervisor makes no automatic reboot or
power-cycle attempt. An independent console/recovery operator must establish
whether Linux is responsive and whether a child remains uninterruptible;
when needed use the already established external power/boot recovery method
under its applicable authorization. After that intervention, independently
recheck SSH, original image/metadata, UIO, 100 MHz clock, kernel, services and
HTTP. An old-boot journal cannot authorize writes on a new boot. Record the
intervention separately; do not relabel the interrupted experiment PASS.
