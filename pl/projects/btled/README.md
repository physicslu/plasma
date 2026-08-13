# btled

這個範例將 Z2 的四顆按鍵直接連到四顆 LED，用來驗證遠端 RTL 開發與 Vivado
bitstream 建置流程。

## 建立 Vivado project

在 SWPC 執行：

```bash
cd /storage/projects/plasma
vivado -mode batch -source pl/projects/btled/create_project.tcl
```

建立後可開啟：

```bash
vivado pl/build/btled/btled.xpr
```

## 建置 bitstream

```bash
cd /storage/projects/plasma
vivado -mode batch -source pl/projects/btled/build_bitstream.tcl
```

預設使用 6 個工作執行緒，可用環境變數調整：

```bash
PLASMA_VIVADO_JOBS=4 vivado -mode batch \
  -source pl/projects/btled/build_bitstream.tcl
```

預期輸出位置：

```text
pl/build/btled/btled.runs/impl_1/btled.bit
```
