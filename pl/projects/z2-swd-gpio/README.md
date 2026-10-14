# Z2 SWD EMIO GPIO + PL Identity — B/C Proof of Path

**Status:** Source implementation / first Vivado build candidate; no Vivado or Z2 real hardware PASS is claimed until SWPC/HIL evidence is recorded. This PR does **not** load the FPGA or program an IC.

## 目標

PYNQ-Z2 (`xc7z020clg400-1`) 的 **Site 1** 實驗配置：

```text
Embedded Linux / Zynq PS
  ├─ GPIO EMIO[0] -- IOBUF -- PMODB JB[0] W14  SWCLK
  ├─ GPIO EMIO[1] -- IOBUF -- PMODB JB[1] Y14  SWDIO (input / output / Hi-Z)
  ├─ GPIO EMIO[2] -- OD     -- PMODB JB[2] T11  nRESET (low / Hi-Z)
  └─ AXI GP0 --> PL Identity AXI-Lite (read-only; ABI v1)
```

`EMIO[0..2]` are *hardware offsets*, not a fixed `/dev/gpiochip*` mapping or Linux GPIO line number. Linux `gpiochip` enumeration, base offset, GPIO ownership, SWDIO turnaround and electrical levels require **real Z2 HIL**.

**This PoC is software GPIO bit-banging, NOT the production FPGA SWD Master.** It provides no target power, voltage translation, DUT isolation, Socket EEPROM, IC presence sensor or per-Site eight-way scheduling.

## 正式 PL Identity v1

The read-only identity register block uses AXI4-Lite, a 100MHz PS FCLK0, `MAGIC=0x504C534D` and:
- `0x00` Magic; `0x04` version `0x00MMmmpp` (`0.1.0` → `0x00000100`);
- `0x08` ABI Version `1`; `0x0C` Flags `bit 0 = swd_gpio`;
- `0x10..0x1C` four words of Git source SHA prefix (128-bit) in hexadecimal word order.

The AXI base address is **assigned and exported by Vivado**, not hard-coded by Linux. `manifest.json` records the actual base address; `.hwh` provides hardware handoff. Invalid read addresses or write attempts return AXI `SLVERR`. Hardware Identity does not prove .bit binary equivalence; verify the `.bit` SHA-256 before an approved load and then read back Identity.

This follows the accepted design proposal in [PR #855](https://github.com/physicslu/plasma/pull/855); it does not depend on that PR being merged to build.

## SWPC 一鍵驗證

Prerequisites: a **clean committed checkout** of this PR in `/storage/projects/plasma`, Vivado on PATH, Python 3, Git, and the **official PYNQ-Z2 TUL board files** installed in the running Vivado version. The script deliberately fails if no correct board preset is found or multiple revisions cause ambiguity.

```bash
cd /storage/projects/plasma
bash pl/projects/z2-swd-gpio/build-on-swpc.sh
```

If `vivado` is not on PATH, load AMD Vivado's `settings64.sh` first or set `VIVADO_SETTINGS64` to its actual path. Optional:

```bash
PLASMA_VIVADO_JOBS=4 PLASMA_BITSTREAM_VERSION=0.1.0 \
  bash pl/projects/z2-swd-gpio/build-on-swpc.sh
```

The script runs `artifact.py prepare` → source-controlled Tcl Project/BD generation → synth/impl/bitstream → timing checks → `artifact.py finalize` → SHA-256 verification. It **does not** connect to Z2 or load a bitstream. Only `pl/build/z2-swd-gpio/project` (ignored generated build state) is deleted and recreated.

Expected build outputs:

```text
pl/build/z2-swd-gpio/
  artifacts/
    plasma-z2-swd-gpio-0.1.0.bit
    plasma-z2-swd-gpio-0.1.0.hwh
    manifest.json
    *.sha256
  generated/
    plasma_identity_generated.vh
    build-identity.json
    identity-axi-base.txt
  reports/
    timing_summary.rpt
    drc.rpt
    utilization.rpt
  logs/vivado-console.log
```

Reports distinguish **implemented setup/hold timing** from unconstrained PMODB physical paths. No real Z2/SWD qualifications are claimed.

### 回傳供工程審查

After running the command on SWPC, provide `pl/build/z2-swd-gpio/logs/vivado-console.log` last 35–70 lines, `pl/build/z2-swd-gpio/artifacts/manifest.json`, and, if a stage fails, its error section or `timing_summary.rpt`. No private keys, device pairing tokens or IC firmware images are needed.

### 安全限制

Do **not** connect a Blue Pill or any DUT to PMODB before reviewing 3.3V I/O limits, SWDIO direction timing, external nRESET pull-up, board grounds, target VTref/voltage and overcurrent protection. `NRST` is only low / Hi-Z. A generated `.bit` file must not be automatically flashed into QSPI or written to the board as part of this B/C task.

### Source-only test

```bash
python3 -m pytest -q pl/tests
bash -n pl/projects/z2-swd-gpio/build-on-swpc.sh
```

The tests above do not execute Vivado, FPGA RTL simulation or physical HIL. Use `run Vivado` evidence for B/C and explicit later HIL acceptance for site programming.
