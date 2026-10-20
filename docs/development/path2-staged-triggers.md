# Path 2 Development Mode — 三階段與可選自動銜接 (Gate 1 Draft)

本案沿用 `SWPC-plasma-codex` Runner、共用 Workflow、既有 Vivado Host Build Engine 及 F1-B 受控 ABI/安全函式。**不建立第二套 Supervisor、Runner、FPGA Manager 或 Vivado Pipeline。**

## 執行語意

`BUILD`、`DOWNLOAD`、`TESTING` 均有**獨立 Trigger**；使用者不必每次從 BUILD 開始，也不會因單獨 BUILD 成功就自動載入 FPGA。

僅有兩個 **per-request、預設 OFF** 的可選旗標：

| 本次 Trigger | `--auto-download` | `--auto-testing` | 意義 |
| --- | --- | --- | --- |
| BUILD | OFF | OFF | 只 BUILD |
| BUILD | ON | OFF | BUILD PASS 後自動 DOWNLOAD；結束 |
| BUILD | ON | ON | BUILD PASS → DOWNLOAD PASS → TESTING |
| DOWNLOAD | 不適用 | OFF | 只 DOWNLOAD |
| DOWNLOAD | 不適用 | ON | DOWNLOAD PASS 後自動 TESTING |
| TESTING | 不適用 | 不適用 | 只 TESTING |

不允許跳過 DOWNLOAD：BUILD 設 `--auto-testing` 但未設 `--auto-download` 必須拒絕。任一階段失敗時**停止後續階段**，不能對失敗的 FPGA Write 自動重試，也不能從 Workflow 成功推論硬體 PASS。

## 既有 Owner Issue #981 CLI（示意；不可直接視為硬體授權）

```text
/plasma-dispatch run fixed-site1-vivado-host-build 981
/plasma-dispatch run fixed-site1-vivado-host-build --auto-download 981
/plasma-dispatch run fixed-site1-vivado-host-build --auto-download --auto-testing 981
/plasma-dispatch run z2-path2-download 981
/plasma-dispatch run z2-path2-download --auto-testing 981
/plasma-dispatch run z2-path2-testing 981
```

未合併 PR 指定來源時，使用既有 `--pr N --sha <exact HEAD>` 於旗標之前。選項只能出現在允許的 Stage Task，解析器與 Registry 嚴格驗證。觸發指令必須由可信 `main` Dispatcher 辨識；**候選 PR 的程式碼存在不代表已部署**。不得用一般 GitHub-hosted CI 觸發 SWPC/HIL。

## 強制硬體邊界

**此 Draft PR 只建立路由契約與離線測試。** 現在 `DOWNLOAD` 與 `TESTING` 沒有通過審查的 privileged Z2 adapter；既有 `pl/hil/f1b.py` 只提供離線安全驗證／可注入介面，並非實際載入入口。可信 Dispatcher 不提供 `hardware_authorized=True`、download 或 testing 的 live callbacks，因此這些路徑（包含自動銜接）**預設拒絕**，不能被字面上的 `--auto-*` 旗標提升權限。

未來啟用 live adapter 前，至少須獨立證明：
- 已明確包含實體操作的同一 Gate 1 授權範圍；正確的 Owner／PR SHA／Runner／實際 Z2 root 權限；
- 已驗證的 BIT/HWH/BIN、當前 boot ID、目前 FPGA 映像及不可偽造的目標端執行收據；
- 原始 `base.bin` Hash 有效、Restore Route 可執行；不能因 UIO Driver 綁定直接推論 AXI 正在活動，亦不能據此盲目 unbind；
- 排除活躍 MMIO Consumer、未知 AXI 存取、不可安全恢復的 Kernel/Child Stall；
- DOWNLOAD 與下一次 TESTING 可能相隔很久，須有**獨立於測試 Trigger 之外仍有效**的恢復責任／期限／失聯復原方案。僅有一張 `DOWNLOAD PASS` Receipt 不能作為安全證明；
- 在 TESTING 時重新驗證 boot/ownership/FPGA，而非信任舊收據；使用 native aligned 32-bit MMIO 且子程序可回收，測試後驗證恢復原始映像。

此外，本案並未核准 SWPC、Z2、FPGA、DUT、LA、USB、Power、Service Restart、部署或 Merge 操作。正式 HIL 證據皆為 `NOT_RUN`。

## Gate 與證據

**Gate 1 一次涵蓋選定範圍**，每一 Trigger 可以獨立下達，兩個 Auto Options 是本次執行設定、不是新的人工 Gate。Build 仍使用 `fixed-site1-vivado-host-build`，下載和測試由 `z2-path2-download`、`z2-path2-testing` 辨識。每階段具來源 SHA 與獨立結果，失敗不能偽稱 PASS；需 Merge 才進入 Gate 2。

本次允許執行：純離線單元測試、GitHub-hosted pull_request CI。不得使用 Issue #981 觸發自架 SWPC Runner。
