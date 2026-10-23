# Blue Pill USB CDC PR #1132 — Gate 1 / Phase A Code Review repair

Executor: Codex Path 3 on `SWPC`, continuing the existing PR branch. Fixed
original PR HEAD: `7225813304997be7916fbccbfb87caadafa7a0b8`. Rebuilt
source commit: `2ea56883c610e60516b5ba9d80fcace82cce854d`.

The original [Phase A evidence](../blue-pill-usb-cdc-phase-a-20261023/README.md)
is retained. This directory records the review delta and its fresh build.

## Review repairs

- Indexed the original and repair evidence in `docs/README.md`; local
  Documentation Integrity returned `PASS (630 Markdown files)` after the new
  entry was added.
- Continuous heartbeat observation now requires `seq == previous_seq + 1`.
  A deliberate **Host Port close/reopen** may skip received frames once; the
  following uninterrupted frames again require exact `+1`. Physical USB
  disconnect/reconnect remains a distinct, unexecuted test.
- Every received heartbeat is printed and flushed immediately. Normal live
  observation leaves the port open. The optional
  `--host-port-pause-seconds` switch is required to close/reopen it.
- `CAFE:4001` remains an experimental placeholder. PLASMA has no documented
  ownership or authorization for this pair. It is not an official PLASMA USB
  ID and is unsuitable for distribution or formal release until an assigned
  or otherwise authorized VID/PID is selected.

## Actual SWPC results

| Check | Observation | Result |
| --- | --- | --- |
| ARM CMake/Ninja cross-build | GCC 10.3.1, binutils 2.38, CMake 3.22.1, Ninja 1.10.1; exit 0; [full log](build.log) | PASS |
| ELF/HEX/BIN/MAP and `size`/`readelf`/`objdump` | Flash 18,328/65,536 B; RAM 5,936/20,480 B; vector SP `0x20005000`, Reset `0x0800094D`, SysTick `0x0800037D`, USB IRQ `0x08000381`; [inspection](inspection.log) | PASS |
| Host C regression with UBSan | 500 ms boundaries, BUSY, command parser, LED, overflow and reconnect checks; exit 0 | PASS |
| Host Python CDC probe tests | 8 tests, including default continuous output, exact sequence, explicit Host Port pause and printed heartbeats; exit 0; [test log](host-tests.log) | PASS |
| Documentation Integrity | Exit 0 after both evidence index entries | PASS |
| Live serial probe, USB enumeration/timing, physical disconnect/reconnect, LED, ST-LINK, Flash, Reset, Z2/PL, HIL | No physical device operated in Phase A | NOT_RUN |

The [SHA256SUMS](SHA256SUMS) file records the exact [ELF, HEX, BIN and MAP](artifacts/)
from a clean build in `/tmp/plasma-blue-pill-pr1132-review-build`. All four
artifact hashes match the original Phase A artifacts because the review delta
changes probe/tests/docs and a source comment, not executable bytes. The ARM
toolchain and ST dependency revisions remain as recorded in the original
Phase A evidence. The live Python probe was **not** run against a serial port.

The PR remains Draft. This evidence does not claim real USB or HIL acceptance.

## Gate 1 / Path 3 post-review Blue Pill LED diagnostic — 2026-10-23

The owner flashed an independent Blue Pill PC13 Blinky test using a Mac/ST-LINK
and observed LED blinking, while the original PLASMA USB CDC firmware did not
produce a new macOS CDC device. This proves only basic board startup and PC13,
**not** the HSE/USB clock, D+/D- electrical route or USB enumeration.

[SWPC Path 3 Run #39926444502](https://github.com/physicslu/plasma/actions/runs/39926444502)
and [its downloaded build evidence](https://github.com/physicslu/plasma/actions/runs/39926444502/artifacts/12489826706)
include an independently rebuilt diagnostic firmware image and source patch at
input HEAD `827a734267fcb0c618f25de47c029f94b63b572c`.
SWPC ARM build/static inspection, host C UBSan tests and 11 Python tests all
PASS; Flash 18,636/65,536 bytes, RAM 5,944/20,480 bytes.
Diagnostic HEX SHA256:
`1d4eae03a76dd27cbab91cbf7f8e50f3a64d09938815c61f94fe1b0ae11cd863`.
BIN SHA256:
`2a6c642a9f8628c7a259e86a88a9cf199d15bed13f4908e779bd410fe5798092`.

The new PC13 autonomous LED heartbeat starts on before HAL/PLL/USB init;
normal mode toggles every 500 ms, manual LED ON/OFF overrides it, LED AUTO
restores the heartbeat, and Error_Handler uses a double-flash fault pattern.
The pinned USB Core ignores several lower-level status returns; PCD
initialization, PMA and start failures now enter Error_Handler. This is
diagnostic hardening, **not a confirmed fix of Mac USB enumeration**.
The published source fixes match the SWPC candidate; SWPC test results are from
the pre-publication candidate at the pinned input HEAD. GitHub-hosted CI on the
published HEAD must be verified independently.

Physical flashing of this diagnostic build, USB enumeration, CDC 60-second
output and LED pattern **NOT_RUN by SWPC**; owner Mac tests are separately
reported, not asserted as platform HIL. The provisional CAFE:4001 pair is
retained solely for this isolated development PoC; no release or VID ownership
claim. PR #1132 remains Draft; no merge, deployment, or remote hardware action.
