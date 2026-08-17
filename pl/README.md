# Plasma PL

`pl/` 保存 Zynq Programmable Logic 的可維護原始檔。Vivado project 是建置產物，
應由版本控制中的 RTL、XDC 與 Tcl script 重新產生。

進行 `pl/` 下的工作前，除了 repository root 的 `AGENTS.md`，也必須遵守：

- `pl/AGENTS.md` — FPGA/PL 專屬 AI agent 規則
- `docs/development/fpga-development-guide.md` — RTL 與 FPGA 開發架構
- `docs/development/fpga-verification-guide.md` — cocotb/pytest、SVA 與驗證流程

## 目錄

目前的 PL 結構已預留正式 Plasma RTL 與 verification 骨架：

```text
pl/
├── AGENTS.md                  # PL/FPGA scoped agent rules
├── constraints/
│   └── pynq-z2/
│       ├── pynq-z2-base.xdc  # 完整 PYNQ-Z2 腳位範本（預設註解）
│       └── btled.xdc         # btled 實際使用的按鍵與 LED 腳位
├── projects/
│   └── btled/
│       ├── README.md
│       ├── create_project.tcl
│       └── build_bitstream.tcl
├── rtl/
│   ├── examples/
│   │   └── btled.sv
│   ├── channel/              # production channel RTL
│   ├── bus/                  # shared bus/interconnect RTL
│   └── top/                  # Plasma PL top-level integration
├── verification/
│   ├── cocotb/               # Python functional tests
│   ├── sva/                  # separate SystemVerilog assertions
│   └── models/               # Python reference/golden models
├── sim/                      # minimal HDL simulation harnesses when needed
├── tests/
│   └── test_source_layout.py # 不需 Vivado 的結構一致性測試
└── build/                    # Vivado 產物，不提交 Git
```

目前尚未有正式 Plasma FPGA module，因此新建立的 production/verification 目錄以
`.gitkeep` 保留於 Git。開始實作後，實際 RTL、cocotb、SVA、reference model 或 simulation
harness 檔案應取代相對應的 placeholder。

## 原則

1. RTL 的唯一正本放在 `rtl/`；新 production RTL 預設使用 SystemVerilog (`.sv`)。
2. 新 RTL 優先使用 `logic`、`always_comb`、`always_ff`；真正需要 net semantics 時仍可使用 `wire`。
3. XDC 的唯一正本放在 `constraints/`。
4. `projects/` 只保存建立與建置專案所需的 Tcl 和說明文件。
5. `.xpr`、`.srcs`、`.runs`、bitstream 等檔案都由 Vivado 產生並忽略，除非 repository policy 明確指定某個 deliverable artifact 需保存。
6. Functional verification 採 Python-first：`cocotb + pytest`。
7. 時序、protocol 與 invariant 檢查優先採獨立 SVA 檔案，必要時用 `bind` 掛入模擬；verification-only SVA 不可進入 production synthesis source set。
8. 可以保留最小的 SystemVerilog simulation harness，但不要重新建立大型傳統 self-checking HDL testbench。
9. CI、Vivado build 與 hardware validation 必須分別回報，不可用 source-layout pytest 宣稱 FPGA 已驗證。

目前的 `btled` 是開發流程驗證範例；正式的 Plasma 通道 RTL 會放在
`rtl/channel/`、`rtl/bus/`、`rtl/top/`，並依實際介面需求再新增 protocol 子目錄。

## 快速測試

目前不需安裝 Vivado，即可在 repository 根目錄執行：

```bash
python3 -m pytest -q pl/tests
```

這組測試目前只檢查唯一 RTL 正本、XDC port/pin 完整性、Tcl 的可攜式路徑，以及
repository 內是否殘留 Vivado project 產物。

它**不是** cocotb RTL simulation、SVA regression、Vivado synthesis/implementation、
timing closure 或 Z2 hardware validation。這些驗證層會從第一個正式 Plasma RTL module
開始依 `fpga-development-guide.md` 與 `fpga-verification-guide.md` 逐步導入。
