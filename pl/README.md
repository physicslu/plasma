# Plasma PL

`pl/` 保存 Zynq Programmable Logic 的可維護原始檔。Vivado project 是建置產物，應由版本控制中的 RTL、XDC 與 Tcl script 重新產生。

進行 `pl/` 下的工作前，除了 repository root 的 `AGENTS.md`，也必須遵守：

- `pl/AGENTS.md` — FPGA/PL 專屬 AI agent 規則
- `docs/development/fpga-development-guide.md` — RTL 與 FPGA 開發架構
- `docs/development/fpga-verification-guide.md` — cocotb/pytest、SVA 與驗證流程

## Domain baseline

Plasma 的可獨立 programming resource 稱為 **Site**：

```text
PPU
├── SITE 1
├── SITE 2
└── ... SITE N
```

因此新的 per-resource production RTL 使用 `site` terminology。Legacy software 的 `Channel` 名稱不得被帶進新的 production Site controller/module 命名；只有在確實描述較低階 bus/protocol channel 時才可使用 channel，並應清楚註明它不是 Programming Site identity。

## 目錄

目前 PL 結構：

```text
pl/
├── AGENTS.md
├── constraints/
│   └── pynq-z2/
│       ├── pynq-z2-base.xdc
│       └── btled.xdc
├── projects/
│   └── btled/
│       ├── README.md
│       ├── create_project.tcl
│       └── build_bitstream.tcl
├── rtl/
│   ├── examples/
│   │   └── btled.sv
│   ├── site/                 # production per-Site RTL placeholder
│   ├── bus/                  # shared bus/interconnect RTL
│   └── top/                  # Plasma PL top-level integration
├── verification/
│   ├── cocotb/               # Python functional tests
│   ├── sva/                  # separate SystemVerilog assertions
│   └── models/               # Python reference/golden models
├── sim/                      # minimal HDL simulation harnesses when needed
├── tests/
│   └── test_source_layout.py
└── build/                    # generated Vivado output; not committed
```

目前尚未有正式 Plasma production FPGA module。`site/`、`bus/`、`top/` 與 verification placeholders 是為第一個正式 module 保留的 source layout；實際 RTL、cocotb、SVA、reference model 或 harness 應在有需求時取代 placeholder，而不是為外觀建立空架構。

## 原則

1. RTL 唯一正本放在 `rtl/`；新 production RTL 預設使用 SystemVerilog (`.sv`)。
2. 新 RTL 優先使用 `logic`、`always_comb`、`always_ff`；真正需要 net semantics 時仍可使用 `wire`。
3. XDC 唯一正本放在 `constraints/`。
4. `projects/` 只保存建立/建置專案需要的 Tcl 與說明文件。
5. `.xpr`、`.srcs`、`.runs`、bitstream 等 generated artifacts 不提交 Git，除非 repository policy 明確指定 deliverable。
6. Functional verification 採 Python-first：`cocotb + pytest`。
7. 時序、protocol 與 invariant 檢查優先採獨立 SVA；verification-only SVA 不可進入 production synthesis source set。
8. 可保留最小 SystemVerilog simulation harness，但不要建立第二套大型 self-checking HDL framework。
9. Per-Site logic 必須保持 Site isolation；共享資源必須顯式建模，不可為方便而序列化所有 Site。
10. CI、Vivado build 與 hardware validation 必須分別回報，不可用 source-layout pytest 宣稱 FPGA 已驗證。

目前 `btled` 只是開發流程驗證範例；正式 Plasma RTL 將依功能放在 `rtl/site/`、`rtl/bus/`、`rtl/top/`，並依 SWD/SPI/I2C 等實際介面需求建立 protocol-specific modules。

## 快速測試

目前不需 Vivado 即可在 repository 根目錄執行：

```bash
python3 -m pytest -q pl/tests
```

這組測試只驗證 repository/source-layout contract，例如 RTL/XDC/Tcl source-of-truth、path portability、Site placeholder naming，以及 generated Vivado artifacts 未混入 source tree。

它**不是** cocotb RTL simulation、SVA regression、Vivado synthesis/implementation、timing closure 或 Z2 hardware validation。這些層級必須在實際執行後分別回報。
