# Plasma PL

`pl/` 保存 Zynq Programmable Logic 的可維護原始檔。Vivado project 是建置產物，
應由版本控制中的 RTL、XDC 與 Tcl script 重新產生。

## 目錄

```text
pl/
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
│   └── examples/
│       └── btled.sv
├── tests/
│   └── test_source_layout.py  # 不需 Vivado 的結構一致性測試
└── build/                     # Vivado 產物，不提交 Git
```

## 原則

1. RTL 的唯一正本放在 `rtl/`。
2. XDC 的唯一正本放在 `constraints/`。
3. `projects/` 只保存建立與建置專案所需的 Tcl 和說明文件。
4. `.xpr`、`.srcs`、`.runs`、bitstream 等檔案都由 Vivado 產生並忽略。

目前的 `btled` 是開發流程驗證範例；正式的 Plasma 通道 RTL 會另外放在
`rtl/channel/`、`rtl/bus/` 與 `rtl/top/`。

## 快速測試

不需安裝 Vivado，即可在 repository 根目錄執行：

```bash
python3 -m unittest discover -s pl/tests -v
```

這組測試會檢查唯一 RTL 正本、XDC port/pin 完整性、Tcl 的可攜式路徑，以及
repository 內是否殘留 Vivado project 產物。
