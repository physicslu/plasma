# Blue Pill WEB -> PS -> PL -> SWD minimal programming PoC

**Development Mode; Gate 1 approved; phase 1 Path 1; phase 2 Path 2.**
**Stage 1 is a candidate, not HIL or a Production programmer.**
This is one explicitly disposable STM32F103C8T6 Blue Pill at Site 1.
The goal is actual WEB Job -> local PS OpenOCD -> PL SWD pins ->
target identify / erase / write / readback compare. No ST-Link or
PS GPIO shortcut is acceptable as evidence for this route.

## Upstream OpenOCD isolation

- Candidate upstream commit: `5088db4c9154ca833c6d558381074b33672e127a`
  (2026-10-21 `openocd-org/openocd` master, fixed source).
- `specs/bluepill-poc/openocd-remote-bitbang-v1.json` pins this SHA.
- `scripts/build-openocd-bluepill-poc.sh <new-output-dir>` builds only an
  isolated Development toolchain, then checks `remote_bitbang` adapter and
  `transport select swd` admission. This is **not** ARMv7 qualification.
- `release/openocd.json` remains the previously validated 0.12.0 baseline,
  and no other ICPN is promoted by this experiment.
- Before `init`, a trusted PS supervisor must set `remote_bitbang host`
  to an explicitly owner-controlled local UNIX socket. The reference
  `specs/bluepill-poc/openocd-remote-bitbang.cfg` does not start a listener,
  open hardware or burn Flash by itself.

## Software / RTL split and actual deliverables

- `software/python/plasma_interfaces/bluepill_remote_bitbang.py` handles
  upstream wire commands O/o (SWDIO OE), d..g (SWCLK and SWDIO), c (SWDIO
  read), Q (quit), r (no reset asserted), B/b (no-op). All active reset,
  JTAG, remote sleep and unknown commands are refused, not emulated.
- It only receives an injected `read32/write32/write_barrier` port.
  It never creates a privileged device mapping or declares any board
  safe. A private owner-controlled UNIX listener exists only when
  `serve_local_unix_once` is invoked with an already qualified port. A caller must independently prove one
  exclusive PS word-port owner, manifest/bitstream/board identity, power,
  external pins, signal level and rollback.
- The separate Host-only RTL candidate is
  `pl/rtl/bus/plasma_poc_swd_gpio_axi_lite.sv`, a single-site AXI4-Lite
  register endpoint at candidate address 0x40008000. **It has no Z2 top,
  pin constraints, approved FPGA image or physical address assignment**;
  the address is an offline simulation convention only.
- Register 0x00: read-only Magic 0x50425357; 0x04: ABI 0x00010000;
  0x08: write-only DRIVE (bit0 SWCLK, bit1 SWDIO-out, bit2 OE);
  0x0C: read-only SAMPLE (bit0 input, bit1 SWCLK, bit2 OE, bit3 OUT).
  Power, NRST and other Sites are not mapped. RTL reset drives
  SWCLK low and OE inactive; **this alone cannot guarantee board electrical
  safe-off**.
- Host-only pytest and Cocotb verify wire ordering, OE release, sample,
  separate AXI AW/W beats, alignment/byte strobe/address/restricted values,
  invalid reset/JTAG messages, exact ABI and fail-closed MMIO uncertainty.

## WEB and PS runtime: integration requirement, not a mock claim

The **existing** Control Station `ProgrammingJobPanel`,
`plasma-api.ts` and Gateway `/api/jobs` remain the canonical WEB Job
entry. Phase 1 must ultimately bind an *explicit PoC provider* to that
standard job path and an owner-admitted OpenOCD worker, not create a
parallel operator-only service, a fake completion or a second Job owner.
Until such a provider, image upload, job-stage telemetry, OpenOCD-to-bridge
UNIX socket startup and verified boot-bound PS/PL port exist, WEB→PS→PL
**end-to-end is NOT_RUN**.

The canonical WEB REST -> real PS Protocol v3.3 route has now been
included in the same Host-only CI as a **negative execution test**:
`software/python/tests/test_bluepill_web_ps_admission.py` starts actual
loopback HTTP and Plasma Server listeners, sends an immutable SHA-256-bound
Programming Asset to `POST /api/jobs`, and verifies the OpenOCD route is
refused before Job registry/queue/lease creation. It also forbids caller-
supplied runtime admission metadata. This is proof of the **existing WEB/PS
request path and truthful refusal only**; it is not proof of a positive
OpenOCD Programming Job, a browser UI interaction, or any connected PL.

Phase 1 now also has an **inert opt-in candidate Job adapter**:
`software/python/plasma_interfaces/bluepill_openocd_job.py` and the
matching exact-ICPN branch in `plasma_server/execution_router.py`.
The normal `OpenOCDInterface` created by the Production SiteManager
remains non-executable. The candidate can be created only by an
explicitly injected trusted Site `interface_factory` with a plan
executor, *external* admission function and safe-shutdown hook.
No YAML/REST boolean enables this route. Only Site 1 and
`STM32F103C8T6`/STM32F1 medium-density are allowed.

`software/python/tests/test_bluepill_web_ps_job.py` exercises a real
WEB HTTP -> PS Protocol v3.3 -> SiteWorker programming Job using a
**synthetic injected executor** and tests revocation. Synthetic PASS
proves the canonical execution seam, staging and Job state transitions,
NOT an OpenOCD flash command process, FPGA BIT/HWH identity, hardware
admission or a programmed Blue Pill. Path 2 still needs the actual
exclusive owner/electrical/rollback admission provider, reviewed native
ARMv7 port and physically connected bridge before ANY positive
real-hardware Job is permitted.

### Real OpenOCD Job process candidate (still Host-only and NOT Flash PASS)

`software/python/plasma_interfaces/bluepill_openocd_session.py` is the
opt-in process/socket lifecycle around the **existing**
`OpenOCDPlanExecutor` and an explicitly injected qualified
`WordPort`. It launches the pinned executable with
`specs/bluepill-poc/openocd-remote-bitbang-adapter-only.cfg`,
provides a private UNIX socket, and then loads canonical
`target/stm32f1x.cfg`. It cannot load a Z2 FPGA image or acquire
live MMIO by itself, and is **not installed by the default SiteManager**.

`software/python/tests/test_bluepill_web_ps_real_openocd.py`
submits a canonical WEB Job to the real PS/SiteWorker, uses a real
pinned OpenOCD subprocess, and connects to the independent **virtual
DPIDR-only** responder. Because this responder does **not** implement
Flash, an Erase Job MUST be terminal failure, even if SWD DPIDR
is correctly read. The test also checks private socket teardown and
PPU execution lease cleanup. The new test is separate from the
positive synthetic-Executor WEB Job test. **Passing this negative
Host-only integration test does not qualify real Erase/Program/Verify**.
At the current stage, the test's actual hosted CI result must be
reported from its specific run; source presence is not a PASS claim.

Host-only admission can test this seam without claiming a connected IC.
The current isolated candidate and hosted tests cannot supply an actual
electrical / hardware-ownership proof. No CI PASS may reclassify it.

## Stage 2: Path 2 hardware acceptance (not executed in Stage 1)

Before any Z2 load/Blue Pill Flash write:
1. Bind an exact reviewed BIT/HWH/BOOT image, current boot identity, safe
   AXI/UIO ownership, tested native ARMv7 DMB, exclusive Site 1 mapping,
   and reliable rollback of the original FPGA configuration. Candidate
   address 0x40008000 must be *physically verified* rather than assumed.
2. Verify board's actual SWDIO/SWCLK pins and bidirectional/Hi-Z voltage
   behavior, Blue Pill external 3.3V supply/reference, GND, powered-off
   defaults and an LA monitoring trace. A Z2 3.3V logic label is not
   proof of DUT voltage compatibility.
3. Verify exact target identity and Flash geometry (STM32F103C8T6 is
   64 KiB; do not accept a Blue Pill 128 KiB board-config override).
4. Use an owner-approved disposable firmware and bound hash for
   identify -> erase -> program -> readback binary compare. Record
   actual WEB Job ID, PS runtime, OpenOCD/PL sources and versions,
   waveforms, expected/observed output and restore outcome.
5. If any prerequisite is missing, record actual reason and `NOT_RUN`;
   never substitute an ST-Link, mock target or direct PS GPIO path.

Z2 Load, external SWD, real Flash, full WEB integration and HIL are
`NOT_RUN` unless their own execution evidence exists. No deployment,
Production binary replacement, PR merge or unapproved DUT actuation.
