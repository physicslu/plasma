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
