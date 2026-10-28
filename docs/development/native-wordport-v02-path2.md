# PLASMA Native C WordPort v0.2 — Path 2 and Z2 direct Gate 1

This is a minimal adapter for the *already merged* PR #1199, not another
Bridge, Dispatcher or hardware authority. The new reviewed Python entrypoint is
scripts/plasma_native_wordport_v02.py; both routes use the SAME source bytes.

## Scope and safety

- Path 2: Owner-authenticated, source-pinned operator-cli / guarded-hardware
  on the existing non-root SWPC Runner, using the enrolled SSH/sudo channel.
- Direct Z2: The same installed Python entrypoint invoked as root after
  actual owner/electrical attestation. Both paths launch OpenOCD locally on Z2
  PS, connected through the SHA-pinned Native C WordPort and PS-local UNIX
  socket to Z2 FPGA PL and the Blue Pill. Do not put live target OpenOCD on SWPC.
- Input: PR #1197 CDC v0.2, exactly 62,800 bytes, SHA256:
  e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c
- Destructive operation: erase pages 0–61 (0xF800 bytes), ONE flash write,
  verify and independent 62,800-byte readback/SHA. The job does not perform
  mass erase, automatic retries, reset, resume, FPGA load or Golden restore.
  The user must approve the destructive scope and have a recovery plan.
- Admission: exact script SHA on both hosts; current Z2 Root source/SHA,
  Boot ID, held/tested FPGA Image, Manifest, Golden SHA, Native .so SHA,
  OS root/sudo credentials and device ownership are checked before the job.
  The existing bridge holds the single FPGA, MMIO and Site 1 owners throughout
  the socket session. Missing/safety-uncertain facts require NOT_RUN/FAIL.
- Real device electrical safety (3.3V VTref, shared GND, correct pins, power)
  remains an explicit owner attestation; it is NOT proven by a source SHA.

## Important Flash Loader timeout diagnostic

Do not run a *second* OpenOCD instance while the Bridge or a previous OpenOCD
owner is active. The new entrypoint uses a single private OpenOCD Tcl file and
Tcl catch around erase, program, verify and readback. On command error it:

1. Records DHCSR; SRAM FIFO WP/RP at 0x2000003C; the requested eight words
   at 0x20000040; FLASH_SR 0x4002200C; FLASH_CR 0x40022010; CFSR/HFSR.
2. Only after these reads, issues halt, then reads PC, LR, SP, xPSR, PRIMASK
   and debug_reason. Each diagnostic command is independently caught so
   one failing read does not hide the remaining evidence.
3. Uses shutdown error (nonzero process exit), stops without retry/reset and
   releases bridge/MMIO resources through existing cleanup.

This is a **post-OpenOCD-error** state snapshot. An OpenOCD flash-algorithm
timeout may already have changed the CPU before the Tcl catch returns.
It is not evidence of exact PC at the first FIFO stall.

An optional diagnose-after operation connects a NEW OpenOCD session to
inspect the surviving state (no erase/program/reset); it does halt the CPU.
Label that evidence POST_SESSION_REATTACH, never original failure-instant.

## Deployment: performed by owner, not this PR

After review and the appropriate Gate authorization, install the exact
reviewed Python entrypoint on both SWPC and Z2. The Z2 destination is the exact reviewed Z2_ENTRY constant in the script;
substitute <Z2_NATIVE_BUNDLE> with the corresponding enrolled device path:

    <Z2_NATIVE_BUNDLE>/scripts/plasma_native_wordport_v02.py

Keep the existing PR #1199 ARMv7 native library, barrier library, guarded
bluepill-wordport-session.py, Root source pin, tested FPGA Image/Manifest and
OpenOCD installation intact. Do not silently change pin, sudoers or FPGA Image.

Supply the **real Z2 path** to the v0.2 BIN after checking the size and SHA.
Do not infer the v0.2 filename from the historical v0.1 scripts.

### Automatic read-only preflight (run first, also enforced before programming)

The same reviewed script now exposes `--operation preflight`; it never
launches OpenOCD, a Bridge, or a DUT transaction. It checks the precise
script/Firmware/Native/Bridge hashes, OpenOCD binary executable and scripts,
Root source pin and checksum manifest, current Boot ID, FPGA Manager state,
held/tested Image, Manifest and Golden checksums, MMIO owners and existing
OpenOCD/Bridge processes. It reports one JSON receipt with explicit PASS or
NOT_RUN/BLOCKED reason; no special `--owner-attested` flag is needed for
this **read-only** mode. Z2 root is still required to read Root state and
inspect the owner processes. It does **not** check electrical wiring,
Vref, power or physical SWD signal quality; those require the operator.

On Z2, using the newly installed **reviewed SHA-pinned** script:

    S="<Z2_NATIVE_BUNDLE>/scripts/plasma_native_wordport_v02.py"
    SCRIPTSHA="$(sha256sum "$S" | cut -d' ' -f1)"
    sudo /opt/plasma/python/3.12.13/bin/python3 -I -B "$S" \
      --role z2 --operation preflight \
      --firmware <Z2_V02_BIN> \
      --source-sha256 "$SCRIPTSHA"

Or from SWPC, substitute `--role swpc` with the same exact script,
firmware and source SHA. SWPC's enrolled SSH/host-key/sudo rights remain
a requirement; no new sudo privilege is provided.

The *program-v02* and *diagnose-after* operations always repeat this
preflight, and still require `--owner-attested` for physical operations.
A successful read-only preflight is **not** authorization to erase Flash.

### SWPC direct CLI (or identical argv under Path 2 operator-cli)

    SCRIPTSHA="$(sha256sum scripts/plasma_native_wordport_v02.py | cut -d' ' -f1)"
    python3 scripts/plasma_native_wordport_v02.py \
      --role swpc --operation program-v02 \
      --firmware /absolute/path/on/Z2/v02.bin \
      --source-sha256 "$SCRIPTSHA" --owner-attested

Path 2 dynamic Work Order uses:
- schema: plasma.development.work_order.v1
- execution_path: path2-cli
- capability: operator-cli
- scope: guarded-hardware
- script: scripts/plasma_native_wordport_v02.py
- argv: the exact switches shown above, with the actual pinned SHA/path
- timeout_seconds: 900
- pr_number/source_sha: exact approved candidate HEAD or trusted main

Use existing Issue #981, Dispatcher and SWPC non-root Runner. Do not
create another Workflow/Stage/Profile/task_id. Work Order admission does NOT
install code or grant sudo/SSH rights.

### Direct Z2 CLI

    S="<Z2_NATIVE_BUNDLE>/scripts/plasma_native_wordport_v02.py"
    SCRIPTSHA="$(sha256sum "$S" | cut -d' ' -f1)"
    sudo /opt/plasma/python/3.12.13/bin/python3 -I -B "$S" \
      --role z2 --operation program-v02 \
      --firmware /absolute/path/on/Z2/v02.bin \
      --source-sha256 "$SCRIPTSHA" --owner-attested

Never run both paths concurrently, and do not paste these commands into a
hardware terminal until wiring, recovery and the approved operation are checked.

## Evidence and acceptance

Each attempt creates private Z2 records under:

    <Z2_NATIVE_BUNDLE>/.work/native-v02-path2/run-*

Receipt.json, exact openocd.tcl, full openocd.log, bridge.log and a readback
BIN (only on completed dump) are preserved on Z2, not automatically published
or transferred to SWPC. Exit code 0 AND matching independent v0.2 readback
SHA are required for an individual program PASS. No reset means no CDC
heartbeat qualification. Timeout/diagnostic FAIL must not be reported as
successful programming. Post-error PC is not failure-instant PC.

Host-only syntax and negative checks:

    python3 -m py_compile scripts/plasma_native_wordport_v02.py \
      software/python/tests/test_native_wordport_v02_entry_host.py
    PYTHONPATH=software/python python3 -m unittest discover \
      -s software/python/tests -p test_native_wordport_v02_entry_host.py -v

No hardware was operated, and no deployment or merge was performed to
produce this source-only candidate.
