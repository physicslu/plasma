# PLASMA 單一 PPU Bundle Commissioning 工具

**入口：scripts/plasma_program.py**。名稱與 Path 2、Path 3、Site 2、特定 MCU 無關；不是另一套 Operator、燒錄引擎或 Deployment Coordinator。

> **正式燒錄入口是 `plasmactl program`（Manager Batch API，多 PPU／多 Site、Start ID、Reconciliation；見 [Unified CLI](../../utilities/plasmactl/README.md)）。** 本工具直接對單一 PPU 的 Bootstrap／Gateway 操作，保留給 Bundle 啟用（B1/B2/B3）與受信任 CI Runtime Kit 部署；它不送出任何 Programming Job。Credential 取得與 Bootstrap Transport 位於執行路徑中立的 `scripts/ppu_bootstrap_transport.py`，不再匯入 Path 2 模組。

命令：diagnose（唯讀）、deploy（只部署/啟用 Bundle）、runtime-deploy（受信任 CI Runtime Kit）。原 flash／run 已於 U7 退休：PPU 只在 Manager Batch 的 ACTIVE Resource Reservation 下接受 Programming Job，單 Site 燒錄請用 `plasmactl program --target <alias>:<site>`。所有寫入都必須有既有 Owner／執行環境授權，--approved-once 僅是防誤觸，並非授權憑證。

## 單次執行範例

```bash
python3 scripts/plasma_program.py deploy \
  --bundle ./firmware-v01.zip \
  --site 2 --host 192.168.2.99 \
  --device-id ppu-device-7ed4b30913a9bf6101da5a7a \
  --approved-once
```

（歷史）2026-11-08 曾以本工具已退休的 run 指令完成單一 Site 2 的 Bundle [B](https://github.com/physicslu/plasma/actions/runs/42463696052) 與 [A](https://github.com/physicslu/plasma/actions/runs/42464939052) 實機燒錄，各自完整 Readback、SAFE_OFF PASS。此範例僅示意參數，執行時仍必須指定 Z2 **當前**實際安裝的 Runtime 完整 SHA。可以額外提供 --source-sha 固定執行程式來源（在 Path 2/3 Work Order 中也必須由 trusted dispatcher 做獨立來源鎖定）。

- --firmware-package：Bundle 有多份 firmware-asset 時必填；若只有一份則自動選取。
- --image：非必要，只核對外部 BIN 與選定 Bundle Firmware SHA/大小完全相同，**不會將 BIN 另送至 Z2**。
- --owner-token-file：讓具既有 Owner 授權的本機/其他路徑使用受保護的 0600 憑證；省略時沿用 SWPC 已配對的 Z2 SSH 憑證路徑。不得在命令參數、PR、Issue、CI log 寫入 Token。
- --site：從 Bundle Programming Profile 宣告的 sites 驗證。提供其他 Site 不代表可執行，Runtime/Site Worker 仍有最後的硬體 Admission 權限。

## 硬體與部署邊界

先使用現有 Bundle v3 Host-only Verifier 驗證 Archive SHA、Manifest、Package/Files，確認 FPGA Image 不在此 Firmware-only 路徑。B1/B2/B3 僅透過 ppu_deploy_api.BootstrapAPIClient 的 reconcile_bundle_assets，B3 由原 Coordinator + quiesce lease 執行，fpga_load=false。本工具不送 Job；燒錄由 Manager Batch 在 Resource Reservation 下提交。

Job 的 Erase/Program/Readback、Site Ownership、Root Admission、FPGA Reload Lock、SAFE_OFF 仍由既有 Z2 Runtime / Site Worker 負責。只有 Readback SHA、Verified Bytes、SAFE_OFF、Job/PPU Idle 全部相符才可 PASS。若 HTTP 結果、B3 Journal 或 Job 結果不明，只能唯讀對帳，不得自動重新提交。

此 CLI 是**受控單機工程入口**，Bootstrap commissioning HTTP 的私有網路連線不具備生產部署的 TLS 安全資格。對多 PPU、生產線及八 Site 的資格需要獨立實機證據。實作的 Host-only CI 不能宣稱 Z2 或 DUT PASS。

## Gate

Gate 1：Draft PR、Host-only 正負向測試與 CI。Gate 2：Owner 核准後才合併；部署 Z2 與 DUT A/B 實機 Flash 是獨立執行範圍。原歷史性 `scripts/plasma_site2_path2_ops.py` 已退休；本次 S2/S3 收斂再刪除硬編碼 v0.1 的 `scripts/plasma_site2_single_flash_path2.py` 與其專屬測試。`scripts/plasma_program.py` 是唯一的直接 PPU Bundle commissioning 工具，並繼續使用既有 PPU Runtime、C-3/Root/Site 安全機制；Manager 管理的燒錄一律使用 `plasmactl program`。
