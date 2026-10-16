# LT02-04 — Z2 PS↔PL five-aperture MMIO loopback image candidate

**Status: source/build recipe only.** An actual Vivado implementation,
.bit/.hwh/manifest and hardware loopback HIL are **NOT RUN** until the SWPC
build and separate Z2 acceptance are observed.

This is an **independent** project in `pl/projects/z2-lt02-axi/`, derived
from the retained four-aperture SWD-03 architecture. It does not replace or
modify the earlier SWD-03 source and its qualified internal DPIDR evidence.
No external PL pins, power, DUT, SWDIO, SWCLK or nRESET are exported.

| GP0 aperture | Vivado module | Meaning |
|---|---|---|
| `0x40000000` | `identity_0` | Existing Identity ABI and Git Build ID |
| `0x40001000` | `control_0` | Existing CONTROL/STATUS echo |
| `0x40002000` | `swd_0` | Existing digital SWD-00 loopback |
| `0x40003000` | `transaction_0` | Internal synthetic DPIDR SWD-03 |
| `0x40004000` | `lt02_0` | New LT02 2 KiB AXI4-Lite scratchpad |

All five are disjoint, 4 KiB GP0 address ranges, FCLK0 at 100 MHz,
synchronized active-low reset. The `transaction_0` ↔ `fixture_0` DPIDR
connection remains internal. LT02 IP has no PL physical IO.
The actual Vivado address map must match the HWH and manifest before
software ever opens the new MMIO aperture.

## Offline gates

- Reuse existing Cocotb/pytest SWD-03 regressions.
- Run the **production** `LoopTestDriver` against the actual LT02 RTL via
  Cocotb AXI BFM, and Python word-port boundary tests.
- Validate the HWH with fault injection for all five apertures, decoder
  values, FCLK0 and reset. Do not probe invalid AXI addresses on hardware.
- Build with Vivado 2026.1, pinned PYNQ-Z2 board files, perform implementation,
  timing, DRC/methodology checks, then verify .bit/.hwh/manifest digests.
- Retain a new, timestamp-independent uniquely named build directory. A
  historical SWD-03 PASS does not imply a LT02 bitstream PASS.

## SWPC isolated build (no Z2 access)

Use an isolated **clean committed worktree** of the reviewed LT02 feature
commit (or approved `main` once merged). Do not switch the worktree of
an already-running Vivado build.

```bash
cd /storage/projects/plasma
git status -sb

# Use the owner's EXISTING pinned, verified PYNQ-Z2 board-files checkout.
export PLASMA_BOARD_REPO=/absolute/path/to/checked-pinned-pynq-board-files
export PLASMA_TEST_PYTHON=/absolute/path/to/working-cocotb-python
export PLASMA_VIVADO_JOBS=4
export PLASMA_BITSTREAM_VERSION=0.1.0
bash pl/projects/z2-lt02-axi/build-on-swpc.sh
```

The source-script prints `LT02_BUILD_DIR=...` before running tests.
It uses `flock` to prevent duplicate builds in the same worktree and
places each attempt under `pl/build/z2-lt02-axi/run.XXXXXXXX/`.
The pinned board-file commit is
`e02d6a3866b5465218f777168cdc51344ac94e07`.

**No SSH to Z2, no FPGA reload and no service change are performed by
this build.** If mandatory offline verification or Vivado fails, retain
the failing logs and do not claim a new image exists.

A real `LT02_HOST_ARTIFACT_PASS_NO_Z2_OR_TARGET_CLAIM` after finalization
means host synthesis/implementation/timing and five-aperture HWH passed.
It **does not** prove ARMv7 MMIO, PYNQ-Z2 loading, PL end-to-end Gateway
behavior or real IC programming. LT02-05 and LT02-06 remain NOT RUN.

For hardware development HIL, use the existing supervised rollback/FPGA
ownership approach with the *new* candidate bytes/HWH/Build ID — never
reuse the SWD-03 four-aperture receipt as a five-aperture receipt.

See [LT02 ABI and full acceptance matrix](../../../docs/development/mmio-lt02-ps-pl-loopback.md).
