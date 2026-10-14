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

## 先驗證現有 SWPC Runner 的 Vivado 環境

這個階段先判斷 **Runner 執行帳號 `plasma-ci`** 是否能啟動 Vivado 並辨識 Zynq-7020 / PYNQ-Z2 Board Part；不建立 Bitstream、不需要連接 Z2。

2026-10-14 在 SWPC 實測：`/storage/tools/xilinx/2026.1/Vivado/settings64.sh`、
Vivado 2026.1 BASIC License（至 2027-08-01）、`xc7z020clg400-1` 都已通過；
兩個帳號的 `board.repoPaths` 預設都為空，但下列**固定版本**的 Board Files
透過 `board.repoPaths` 已在 `plasma-ci` 成功載入，Board ID
`tul.com.tw:pynq-z2:part0:1.0`。

為確保 CI 重現性，使用 [XUP Shanghai PYNQ-supported-board-file](https://github.com/xupsh/pynq-supported-board-file)
的 Git Commit `e02d6a3866b5465218f777168cdc51344ac94e07`。
`prepare-board-repository.sh` 會將它下載／快取在**被 Git 忽略的**
`pl/build/z2-swd-gpio/board-repository`；且每次驗證 Commit、
Git 工作樹與 `board.xml`、`preset.xml`、`part0_pins.xml`。
Vivado Tcl 會明確設定 `board.repoPaths`，不依賴 GUI Board Store、個人
`~/.Xilinx` 目錄設定，也不往 Vivado 安裝目錄複製資料。

**注意：** 這是 2018 年版本 Board Files，已完成 **Vivado 2026.1 Board Part 識別 PASS**，
尚未證明 PS7 Block Design Preset、RTL Synthesis／Implementation／Timing PASS。
Board Files 不是本工程的 RTL 功能測試或實體 Z2 驗證。

第一階段可在 SWPC 終端機以 `plasma-ci` 帳號執行 `check-swpc-vivado-runner.sh`。檢查器不會安裝套件或重新配置 Runner，結果會列印 `PLASMA_VIVADO_PREFLIGHT_PASS` 或明確失敗原因。如 `vivado` 不在 Runner PATH，需先確認已安裝 Vivado 的實際 `settings64.sh`，可透過環境變數 `VIVADO_SETTINGS64` 指定（不要盲目猜測路徑）。

更精確的第二階段是在此 PR 合併後，從 GitHub Actions 的 `SWPC Vivado Runner Environment` Workflow 在 **main** 手動觸發。這才會實際驗證 Actions Runner Job 的 PATH、執行帳號與 Board Files；Workflow 僅接受 `workflow_dispatch` + `main`，絕不在未審核的 PR 上執行持久化 SWPC Runner。驗證腳本只產生暫存日誌，不安裝任何工具。

**重要：** 這個 environment PASS 仍不是 Vivado 授權、Synthesis／Implementation／Timing、Bitstream 或實機 HIL PASS。後續必須執行下方的完整 Vivado Build 才能驗證上述能力。

## GitHub Actions 自動 Vivado Build（main only）

正式納入版本控制的 Workflow：
[SWPC Vivado Bitstream Build](../../../.github/workflows/swpc-vivado-bitstream-build.yml)。
在 PR 合併至 `main` 且經過 Merge Approval 之後，於 GitHub Actions
手動觸發 `workflow_dispatch`，限定來源為 `refs/heads/main`，
專用 Job 使用已驗證的 `SWPC-plasma-ci` Runner（`plasma-integration`
標籤），並以固定的 Vivado 2026.1 `settings64.sh` 執行同一支
`build-on-swpc.sh`。Build PASS 才上傳 `.bit`／`.hwh`／Manifest／報告，
錯誤日誌獨立保存；**不會載入 FPGA、重啟 Z2 或操作 IC**。

PR CI 的 Verilator/Cocotb 在 GitHub-hosted Runner 上完成；
**不能將未審核 PR checkout 到持久化高權限 SWPC Runner**。
如需在合併前真正進行 Vivado Block Design／Bitstream 相容性驗證，
只能在 SWPC 以開發者互動登入、使用隔離 worktree 執行一鍵 Script。
這是工具權限例外，不代表對 PR 加入持久化 Runner 的 PR trigger。

## SWPC 一鍵驗證

Prerequisites: a **clean committed checkout** of this PR (prefer an independent worktree), Python 3, Git, SWPC Vivado 2026.1 and its BASIC License. `build-on-swpc.sh` defaults to the SWPC-qualified `settings64.sh` if it exists, and automatically prepares the exact pinned PYNQ-Z2 Board Repository above. **No manual Board Store installation is required**; first-time cache creation requires network access to GitHub. The script fails closed if the exact Git commit, Board Part or preset is missing.

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

**Vivado 2026.1 observed integration failure (2026-10-14):** During `create_bd_cell -type module -reference pl_identity_axi_lite`, IP Integrator's independent HDL parser could not resolve `plasma_identity_generated.vh`, despite `sources_1` include directories. The fix creates `generated/pl_identity_axi_lite.sv` as a **fully expanded, standalone compilation unit** by replacing the single include directive in the checked-in authoritative RTL with immutable generated constants. Vivado only adds this expanded module, while cocotb continues to test the original RTL against a fixed test fixture. `rtl-lint.sh` also lints the exact generated standalone module.

The same SWPC attempt reported four `PSU-1..4` critical warnings for negative DDR DQS-to-clock delay values from the pinned PYNQ-Z2 PS7 board preset. These must be assessed before physical Z2 loading and DDR/PS qualifications; **a Build PASS is not evidence that these board-level warnings are benign**.

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
    pl_identity_axi_lite.sv
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

### RTL Lint + Cocotb（GitHub PR 必須通過）

每次此工程的 RTL／XDC／驗證程式修改，`pl-z2-swd-gpio.yml`
會在 GitHub-hosted Ubuntu Runner 執行 **Verilator 連接/寬度 Lint** 及
**Icarus Verilog + cocotb + pytest** 真實 RTL 功能模擬。

Cocotb 測試包含：AXI-Lite 身分 Register Map、非零 PS 實體基底位址、
非法/未對齊位址的 SLVERR、寫入唯讀 Register 的 SLVERR、AW/W
先後順序與 Backpressure、Reset 中斷/復原，以及 EMIO SWDIO
高阻態／輸入採樣／SWCLK／NRST 低電位或高阻態。

在本機安裝 `verilator`、`iverilog` 後，可執行：

```bash
python3 -m pip install 'pytest' 'cocotb==1.9.2' 'cocotb-test==0.2.6'
bash pl/projects/z2-swd-gpio/rtl-lint.sh
python3 -m pytest -v pl/verification/test_z2_swd_gpio_rtl.py
```

驗證的 Xilinx `IOBUF` 是 `pl/sim/IOBUF.sv` 的**純數位四態模型**，
不參與 Vivado 合成，也無法證明硬體實際電氣安全。AXI 上游 Interconnect
的基底位址解碼歸 Vivado Block Design 驗證，不由此 IP 的低 12-bit
Register Decode 判斷是否屬於該周邊。

### Source-only test

```bash
python3 -m pytest -q pl/tests
bash -n pl/projects/z2-swd-gpio/build-on-swpc.sh
```

The `pl/tests` source-only tests **do not** simulate RTL; simulation is done separately by `pl/verification/test_z2_swd_gpio_rtl.py`. Neither suite executes Vivado synthesis/implementation/timing or physical Z2 HIL.
