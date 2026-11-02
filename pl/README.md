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

目前 PL 結構（`rtl/`、`verification/` 等請直接看目錄內容）：

```text
pl/
├── AGENTS.md
├── constraints/pynq-z2/      # XDC 正本
├── projects/                 # Vivado 專案 Tcl 與說明（見下表）
├── rtl/
│   ├── bus/                  # AXI-Lite／interconnect RTL
│   ├── site/                 # per-Site RTL（SWD waveform／transaction 等）
│   ├── examples/             # btled 等流程範例
│   └── top/
├── verification/             # cocotb、SVA、reference models
├── sim/
├── hil/                      # 歷史 HIL 程式與保留的共用安全 helper
├── tests/
└── build/                    # generated Vivado output; not committed
```

| `projects/` | 狀態 |
| --- | --- |
| `btled` | 開發流程範例（按鍵→LED），不是 Plasma 產品 RTL。 |
| `z2-bluepill-rbb` | 目前 Blue Pill SWD PoC 的 Image Manifest；**main 上只有 `image-manifest.json`**，RTL／Vivado 原始碼在未合併的 PR #1142，無法從 main 重新建置。 |
| `z2-fixed-unified-site1` | F1-B 固定 ABI Site 1 PS7 整合；**已淘汰**。 |
| `z2-swd-gpio` | PS EMIO GPIO software bit-bang；**已退役**，建置入口停用。 |
| `z2-swd03-axi` | FPGA 內部合成 DPIDR responder，無外部腳位；**已退役**。 |
| `z2-control-waveform` | PSPL-02／SWD-00 內部 PL loopback；host-only 候選，Z2 載入未驗收。 |
| `z2-identity` | Identity-only PS／PL AXI 實驗。 |
| `z2-lt02-axi` | LT02-04 五 aperture MMIO loopback；只有 source／build recipe。 |
| `swd-transaction` | SWD-01／SWD-02 transaction transport 與 virtual target（host-only）。 |

`site/`、`bus/`、`top/` 與 verification 目錄應隨實際 RTL、cocotb、SVA 需求成長，而不是為外觀建立空架構。

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

## 現行 Blue Pill SWD PoC 與退休路徑

- **Current Path 3:** Z2 **PS-local ARMv7 OpenOCD → UNIX WordPort/RemoteBitbang → PL SWD Image → PMOD → Blue Pill**；實際載入/DPIDR 必須有本次 HIL 收據。請見根目錄 `AGENTS.md`、[`bluepill-wordport-session.py`](../scripts/bluepill-wordport-session.py) 及 [Blue Pill Image Manifest](projects/z2-bluepill-rbb/image-manifest.json)。
- **RETIRED:** [`z2-swd-gpio`](projects/z2-swd-gpio/README.md) 是舊 PS EMIO GPIO software bit-bang；舊建置入口已停用。
- **RETIRED:** [`z2-swd03-axi`](projects/z2-swd03-axi/README.md) 是 FPGA 內部合成 DPIDR，沒有對 Blue Pill 的 PMOD SWD 外部訊號。
- [相依盤點／舊文件判讀與防誤用準則](../docs/development/swd-legacy-path-retirement.md)。保留的共用 Identity、Board Files、RTL、LT02 合成測試不能替代實體 SWD PASS。

## 快速測試

目前不需 Vivado 即可在 repository 根目錄執行：

```bash
python3 -m pytest -q pl/tests
```

這組測試只驗證 repository/source-layout contract，例如 RTL/XDC/Tcl source-of-truth、path portability、Site placeholder naming，以及 generated Vivado artifacts 未混入 source tree。

它**不是** cocotb RTL simulation、SVA regression、Vivado synthesis/implementation、timing closure 或 Z2 hardware validation。這些層級必須在實際執行後分別回報。
