# PLASMA 通用 Bundle 燒錄 CLI

**入口：scripts/plasma_program.py**。名稱與 Path 2、Path 3、Site 2、特定 MCU 無關；這是原一鍵工具的取代版本，不是另一套 Operator、燒錄引擎或 Deployment Coordinator。

命令：diagnose（唯讀）、deploy（只部署/啟用 Bundle）、flash（只對已啟用 Bundle 執行一次 Job）、run（一次執行部署/啟用及 Flash）、runtime-deploy（只透過既有 Bootstrap Coordinator 更新 Runtime）。所有寫入都必須有既有 Owner／執行環境授權，--approved-once 僅是防誤觸，並非授權憑證。

## 單次執行範例

```bash
python3 scripts/plasma_program.py run \
  --bundle ./firmware-v01.zip \
  --site 2 --host 192.168.2.99 \
  --device-id ppu-device-7ed4b30913a9bf6101da5a7a \
  --runtime-sha 2a5c09f62d07ce15f5c871a2cab99b7bdf64fc92 \
  --approved-once
```

此介面已於 2026-11-08 以新版 S1-C／S2 Runtime 完成單一 Site 2 的 Bundle [B](https://github.com/physicslu/plasma/actions/runs/42463696052) 與 [A](https://github.com/physicslu/plasma/actions/runs/42464939052) 實機燒錄，各自完整 Readback、SAFE_OFF PASS。此範例僅示意參數，執行時仍必須指定 Z2 **當前**實際安裝的 Runtime 完整 SHA。可以額外提供 --source-sha 固定執行程式來源（在 Path 2/3 Work Order 中也必須由 trusted dispatcher 做獨立來源鎖定）。

- --firmware-package：Bundle 有多份 firmware-asset 時必填；若只有一份則自動選取。
- --image：非必要，只核對外部 BIN 與選定 Bundle Firmware SHA/大小完全相同，**不會將 BIN 另送至 Z2**。
- --owner-token-file：讓具既有 Owner 授權的本機/其他路徑使用受保護的 0600 憑證；省略時沿用 SWPC 已配對的 Z2 SSH 憑證路徑。不得在命令參數、PR、Issue、CI log 寫入 Token。
- --site：從 Bundle Programming Profile 宣告的 sites 驗證。提供其他 Site 不代表可執行，Runtime/Site Worker 仍有最後的硬體 Admission 權限。

## Runtime 部署與 Operations Route 相容性

`runtime-deploy` **只更新 PPU Runtime**；不送出任何 DUT Job，也不執行 Erase／Program／Verify／Read 或 FPGA Reload。此命令核對 Bundle v3 Archive SHA256、Platform Target、Provider／Programming Profile、Firmware Asset、Site、已啟用的 Active Asset Set、裝置／Runtime／Kit 身分及 Coordinator 交易。

既有 Runtime CLI 曾在 `read_bundle()` 強制要求 `flash_cycle`，導致已正式啟用、宣告 `erase`／`program`／`verify`／`read` 的 Operations Profile 無法用標準部署入口升級 Runtime。本次僅允許 **`runtime-deploy`** 在既有 Canonical Bundle Verifier 通過後接受有效的新版 Operations Profile。已指定的 Bundle 必須仍與 Z2 Active Asset Set 的 SHA256 **完全相同**，任何不一致均不得提交部署。

**`flash`／`run` 保持舊有 `flash_cycle` Job 契約**，目前不能對僅有新版 Operations 的 Bundle 執行燒錄；不應將其誤認為新版 Operations Job CLI。Legacy 支援僅限後端相容性，不能加入 Console 操作選單。未實作新的 Runtime 部署器、未取消 Owner、Site、Target、Active Set、Kit/Release、SAFE_OFF／Recovery 等現有安全機制。Host-only 測試不是實機部署資格。

## 硬體與部署邊界

先使用現有 Bundle v3 Host-only Verifier 驗證 Archive SHA、Manifest、Package/Files，確認 FPGA Image 不在此 Firmware-only 路徑。B1/B2/B3 僅透過 ppu_deploy_api.BootstrapAPIClient 的 reconcile_bundle_assets，B3 由原 Coordinator + quiesce lease 執行，fpga_load=false；只有確認 Active Set 身分與 Runtime Git SHA 後，才送一筆 flash_cycle Job，使用 asset_set_sha256、asset_package_id、bundle_asset_sha256，絕不傳送 asset_base64。

Job 的 Erase/Program/Readback、Site Ownership、Root Admission、FPGA Reload Lock、SAFE_OFF 仍由既有 Z2 Runtime / Site Worker 負責。只有 Readback SHA、Verified Bytes、SAFE_OFF、Job/PPU Idle 全部相符才可 PASS。若 HTTP 結果、B3 Journal 或 Job 結果不明，只能唯讀對帳，不得自動重新提交。

此 CLI 是**受控單機工程入口**，Bootstrap commissioning HTTP 的私有網路連線不具備生產部署的 TLS 安全資格。對多 PPU、生產線及八 Site 的資格需要獨立實機證據。實作的 Host-only CI 不能宣稱 Z2 或 DUT PASS。

## Gate

Gate 1：Draft PR、Host-only 正負向測試與 CI。Gate 2：Owner 核准後才合併；部署 Z2 與 DUT A/B 實機 Flash 是獨立執行範圍。原歷史性 `scripts/plasma_site2_path2_ops.py` 已退休；本次 S2/S3 收斂再刪除硬編碼 v0.1 的 `scripts/plasma_site2_single_flash_path2.py` 與其專屬測試。**唯一通用受控 Bundle Flash CLI 是 `scripts/plasma_program.py`**，並繼續使用既有 PPU Runtime、C-3/Root/Site 安全機制。
