# 交接：SWD 整合這一路（2026-11-04）

狀態：工程交接文件。本文件不授予任何 Gate 1 範圍、硬體操作、部署或合併權限；
這些仍依 [AGENTS.md](../../../AGENTS.md) 的 Gate 1 / Gate 2 規則。

另一路（Driver / FPGA）的交接見
[2026-11-04-swd-driver-fpga-track.md](2026-11-04-swd-driver-fpga-track.md)。
兩路的**介面契約**在本文 §5，兩份文件內容一致。

## 1. 這一路的範圍

| 負責 | 不負責（屬於 Driver / FPGA 那一路） |
|---|---|
| Runtime、C-3 Site Worker、`ppu_site_adapter_abi5.py`、Package Actions、REST / Gateway / Manager | `pl/rtl/swd/`、Vivado Image、Image 信任登記 |
| `/etc/plasma/site-worker-engine.json`（選定 Runtime 用哪一版 OpenOCD） | `software/native/swd/`（`plasma_swd` adapter）與它的 CI build |
| Bootstrap / Runtime kit 部署、Site 啟用、端到端燒錄 | `scripts/z2/plasma_swd_site_admission.py` 的行為 |
| OpenOCD 以 Bundle Package 部署（新功能，尚未開始） | adapter 的 HIL 範本與時脈驗證 |

## 2. 目前狀態（main `8195f4082`）

### Z2（192.168.2.99）
| 項目 | 值 |
|---|---|
| Bootstrap + privileged tree | main `3d0f911c7`（code manifest `c30404a3…`；Root devmem 表只有 `d0add58c`） |
| Runtime | `/opt/plasma/releases/0.2.1-3d0f911c7385`，6 個服務 active |
| **#1286（REST flash_cycle）** | **已合併到 main，尚未部署到 Z2** |
| FPGA | `z2-independent-swd-v5-d0add58c`，Keep Loaded，Active Set gen 6（含 Stage C 測試 Package `c-iso`、`c-timeout`、`c-site2`） |
| OpenOCD 目錄 | `0.12.0-5088db4c9154`、`0.12.0-9ea7f3d647c8`、`…-plasma-swd-b916b9f3f9bd`（逐筆版）、`…-plasma-swd-b8a7db670649`（pipeline 版，**建議 Runtime 採用**） |
| `/etc/plasma/site-worker-engine.json` | 目前 Z2 的 Bootstrap 是 `3d0f911c7`，還是舊的固定 pin 版本；部署 #1286 後才會改讀這個檔，**目前還沒有寫入** |
| DUT | Blue Pill 在 Site 2（PMODB），跑 CDC heartbeat `8d3ffb02…`；SWPC `ttyACM0`（`cafe:4001`）可收 heartbeat |

### Runtime 燒錄路徑的已知狀況
- Driver 那一路的 HIL 都是**直接以 root 跑 OpenOCD**，Runtime 路徑（REST → Router → Site Worker → adapter → OpenOCD）**還沒有在 Z2 上端到端成功過**。
- 2026-11-03 Stage C D6：Package（uid 998 `plasma-package`）連 `/run/plasma-site-worker/transport.sock`（`root:plasma-package 0660`）得到 `PermissionError`，D6/D7 為 BLOCKED / NOT_RUN（證據 `.work/z2-stage-c-deploy-20261103/evidence/90-d6-c-site2.json`）。之後是否已修正需重新確認。
- Site 設定：installer 會產生 Site 1..8（預設 disabled）；Gateway `POST /api/settings/sites/{id}` 需要帶引號的 strong ETag（If-Match）。

## 3. 必須先處理（P0）

### 3.1 `flash_cycle` 要改成 `reset halt`
`scripts/ppu_site_adapter_abi5.py`（#1286）組出的 argv 是 `init; halt; flash erase_address …`。
Driver 那一路 2026-11-04 的實測（13 次，逐筆版與 pipeline 版都一樣，100 % 相關）：
**只要 halt 時 DUT 韌體正在執行，stm32f1x 的 write 演算法就不會啟動**（`rp` 停在 FIFO 起點，
`timeout waiting for algorithm`），而且 erase 已經做完，所以 Flash 會變空。改成 `reset halt`
之後 5/5 PASS。證據：`.work/z2-swd-pipeline-flash-20261104/evidence/44-flow-d3.log`、`50-resethalt-*`；
runbook [§10](../swd-abi5-openocd-dpidr-hil-runbook.md)。

建議修改：
```diff
-            "-c", "halt",
+            "-c", "reset halt",
```
副作用：reset 後 CPU 在 8 MHz HSI，write / verify 比 `halt` 慢（verify 約 46 → 286 ms），正常。

### 3.2 選定 Runtime 的 OpenOCD
部署 #1286 後，寫入 root 擁有、不可被 group/other 寫入的 `/etc/plasma/site-worker-engine.json`
（欄位必須剛好是這 7 個）：
```json
{
  "schema": "plasma.ppu.site-worker-engine.v1",
  "openocd_root": "/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154-plasma-swd-b8a7db670649",
  "openocd_sha256": "b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861",
  "admission_sha256": "1838d082222429083e3aca91290677d3873f5c681cac004a703b75f40d86c345",
  "adapter_driver": "plasma_swd",
  "driver_abi": 5,
  "adapter_khz": 2000
}
```
寫入後在 Runtime quiesce 下重啟 `plasma-site-worker`。`adapter_khz` 建議 2000（已驗證上限 5000，7143 失敗）。

### 3.3 文件字串過時
`ppu_site_adapter_abi5.py` 開頭仍寫「owner electrical attestation」與「admission record per MMIO word」。
PR #1285 之後 adapter 不讀 admission record、不讀電氣確認紀錄，admission 腳本也不再要求它
（record schema v3，`voltage_source: NOT_MEASURED`）。

## 4. 後續工作（建議順序）

1. §3 的三項，加上部署 #1286 到 Z2（Bootstrap + privileged tree + Runtime；Gate 1）。
2. 確認或修正 D6 的 `transport.sock` 權限問題。
3. 啟用 Site 2，走 REST `flash_cycle` 在 Z2 上端到端燒錄 Blue Pill：readback 必須等於 `8d3ffb02…`，SWPC 收得到 heartbeat。可要求 Driver 那一路同時用 LA2016 擷取比對。
4. Stage C D7（seal fault + Operator Recovery）。
5. OpenOCD 以 Bundle v3 Package 部署（例如 `programming-engine` kind），取代 SSH 並排安裝；完成後 engine selection 改由部署流程寫入。

## 5. 兩路之間的介面契約

**Driver / FPGA 那一路提供：**
1. 每個 adapter 版本 = 一個 ARMv7 CI artifact（`swd-openocd5088-armv7-candidate.yml` 的 `plasma-openocd5088-armv7-candidate`），記錄 CI run、source SHA、`openocd` SHA256、`plasma_swd_site_admission.py` SHA256。安裝目錄 `/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154-plasma-swd-<openocd SHA256 前 12 碼>`。
2. Adapter 的 OpenOCD 使用規則：
   - `adapter driver plasma_swd`、`plasma_swd site <1|2>`、`transport select swd`。
   - 在 `-f target/stm32f1x.cfg` **之後**設定 `adapter speed <kHz>`（該 cfg 會強制 1000）。建議 2000，已驗證上限 5000。
   - **任何 Flash 操作之前必須 `reset halt`，不能只 `halt`。**
   - 不需要 admission record 或電氣確認紀錄。adapter 需要 root、PL 已載入 Image（Root journal `IMAGE` + 同一個 boot）、Site lock 可取得。
3. 現行 Image：`z2-independent-swd-v5-d0add58c`（BIN `0d99ecaf…`），信任登記已在 main。

**整合這一路負責：**
- 選定 Runtime 用哪一版 adapter（engine selection），並在 Runtime quiesce 下切換。
- 不修改 `software/native/swd/`、`pl/rtl/swd/`、`scripts/z2/plasma_swd_site_admission.py` 的行為；有需求請開 issue 或在交接文件留言，由 Driver / FPGA 那一路處理。
- Runtime 或 adapter 呼叫方式的變更若影響 OpenOCD 指令（速度、reset、Site），請同步告知 Driver / FPGA 那一路。

## 6. 參考資料與工具

| 項目 | 位置 |
|---|---|
| Adapter 契約、燒錄流程、時脈結果 | [swd-abi5-openocd-dpidr-hil-runbook.md](../swd-abi5-openocd-dpidr-hil-runbook.md) §9、§10 |
| Bootstrap + privileged tree 部署（SSH root、自動 rollback、重啟 Site Worker） | `.work/z2-main-3d0f911c7-deploy-20261104/tools/m1_deploy_tpl.py` |
| Runtime 部署（Bootstrap API `kind=ppu-runtime`） | `.work/z2-main-3d0f911c7-deploy-20261104/tools/runtime_deploy.py` |
| B1→B2→B3 Image 載入 | `.work/z2-bluepill-heartbeat-flash-20261103/tools/b3_active_set.py` |
| Kit 來源 | `ppu-bootstrap.yml`（artifact `ppu-bootstrap-factory-bundle`）、`z2-ps-release.yml`（artifact `plasma-z2-ps-kit-0.2.1-<sha12>`），兩者都可在 main 上 `workflow_dispatch` |
| SSH 與檔案傳輸 | `scripts/z2/hil/abi5_openocd_dpidr/z2run.py`、`.work/…/tools/upload.py`（Z2 無法從 SWPC 用 HTTP 拉檔案） |
| heartbeat | `docs/evidence/bluepill-z2-flash-2026-10-27/scripts/cdc_heartbeat.py` |
| 證據（SWPC 本機） | `.work/z2-main-3d0f911c7-deploy-20261104/`、`.work/z2-swd-pipeline-flash-20261104/`、`.work/z2-stage-c-deploy-20261103/` |

## 7. 規則提醒

- Gate 1：新的實作、部署或硬體操作前要有 owner 核准的計畫；Gate 2：每個 PR 合併前要 owner 核准指定 HEAD。合併不代表可以部署。
- 不新增任何阻擋性檢查、fail-closed 前置條件或核准步驟，除非 owner 要求（owner 2026-11-03 的明確指示）。
- PASS / FAIL / NOT_RUN 必須對應實際觀察；host 測試、CI、mock 不等於 Z2 或 DUT 結果。
- 只停止確定的 PID，不用 `pkill`/`killall`；刪除或覆寫前先看目標並備份；複製 root 檔案後要確認擁有者（曾發生 `ppu.yaml` 變成 root:root 讓 Runtime 失效）。

## 8. 整合這一路的回覆（2026-11-04，G1-B 分支 `agent/g1b-engine-selection-20261104`）

- §3.1 已改：`flash_cycle` 在 `init` 之後用 `reset halt`（C-3 adapter 與 Host-only 計畫一致）。
- §3.2 改由工具完成：`ppu_site_engine.py install <artifact>` 接管已並排安裝的 `…-plasma-swd-b8a7db670649`，
  再 `select <runtime_id> --adapter-khz 2000 --restart`。實際寫入 Z2 仍需部署核准。
- §3.3 已修正 adapter 開頭的過時說明。
- **給 Driver / FPGA 那一路的請求（不改你們的 CI，由你們決定）：** 在
  `plasma-openocd5088-armv7-candidate` 的 `candidate-evidence.json` 加入
  `adapter_driver`、`driver_abi`、`adapter_khz`（driver 預設值）、`openocd_version`。
  有這四個欄位時安裝工具直接採用；沒有時由 operator 在 `install --declare-*` 聲明並記錄為 operator 聲明。

## 9. Z2 部署與測試狀態（2026-11-04 11:30，整合這一路）

Owner Gate 1（2026-11-04）：只清理燒錄路徑這一層，保留 Root Entry / journal / privileged tree /
FPGA / Active Asset Set / Bootstrap 登錄 / Python / OpenOCD / 帳號，部署後以 REST `flash_cycle` 實測。
證據全在 SWPC `.work/z2-g1b-test-20261104/`（`evidence/` 編號依步驟，`tools/` 為實際執行的腳本）。

### 9.1 Z2 目前狀態
| 項目 | 值 |
|---|---|
| Bootstrap 程式碼 | main `4dbb58a7c`（#1289），以完整安裝取代舊目錄；unit / 登錄 / token 不變 |
| Runtime | `/opt/plasma/releases/0.2.1-622e17465ea7`（PR #1291 merge-ref = main `d4ffae9c9` + installer 修正），6 個服務 active |
| OpenOCD 選擇 | `/etc/plasma/site-worker-engine.json` → `0.12.0-5088db4c9154-plasma-swd-b8a7db670649`，`adapter_khz` 2000；由 `ppu_site_engine.py` 接管（engine 欄位 operator 聲明） |
| Site 2 | `enabled`、`interface: openocd`、`target: STM32F103C8T6`、`openocd.site_worker_socket: /run/plasma-site-worker/control.sock`（SSH 直接改 `ppu.yaml`，見 9.3） |
| FPGA / journal | 未變：`d0add58c` IMAGE、journal `986446e7…`、Active Set gen 6 |
| 備份 | Z2 `/var/backups/plasma-g1b-clean-20261104T090540/`（舊 Bootstrap、舊 releases、`/var/lib/plasma` 內容、HIL 殘留、`b8a7` 目錄原有的 `runtime.json`）；`/etc/plasma/ppu.yaml.bk-site2-c3-20261104T112119` |
| 燒錄 | **NOT_RUN**（燒錄前 heartbeat 基準已記錄：`hb/cdc-before.json`） |

### 9.2 部署過程與已修正的問題
1. 唯讀盤點（`evidence/00-inventory.json`）。
2. Phase 1（SSH root，自動 rollback）：停服務 → 搬移 → 安裝 Bootstrap → engine install/select → 啟動。
   第一次因 `b8a7` 目錄多一個 HIL 範本寫的 `runtime.json` 而 `EXISTING_INSTALL_DIFFERS`，rollback 成功；
   將該檔搬入備份後重跑 APPLIED。其餘檔案與 CI run 41681514427 的 artifact 逐位元組一致。
3. Phase 2（Bootstrap API `kind=ppu-runtime`）：main `4dbb58a7c` 的 kit 失敗 ——
   #1289 的 installer 從自己旁邊載入 `ppu_package_units.py`，但 Runtime kit 沒有這個檔
   （啟用前失敗，Runtime / `ppu.yaml` / unit 皆未變）。兩份 Bootstrap 部署紀錄以 operator 步驟標記為終結
   （`tools/p2r_journal_recovery.py`，原紀錄備份為 `*.recovery-20261104T091005`）。
   修正：**PR #1291**（從已安裝的 Bootstrap 載入產生器；CI 全過，**未合併，待 Gate 2**）。
   以 #1291 的 kit 重跑 PASS。
4. Phase 3：設定 Site 2（見 9.3），重啟 server/web，lease 閒置。

### 9.3 已知缺口（後續工作）
- **Gateway 無法把 Site 接到 C-3**：`POST /api/settings/sites/{id}` 只允許 `enabled/interface/target`，
  不能設 `openocd.site_worker_socket`。建議：plasma-server 從 Stage C 設定
  （`ppu-package-actions.json` 的 `site_worker_control_socket`）自動帶入，`interface: openocd` 即走 C-3。
- `GET /api/status` 的 `capabilities.operations` 尚未列出 `flash_cycle`。
- D6（Package 連 `transport.sock` 的 `PermissionError`）尚未重測；REST `flash_cycle` 走 control socket，不受影響。
- **同時操作**：11:21:40–45 有另一個 SWPC SSH `sudo` session 在 Z2 執行 HIL 腳本（輸出 `mode`/`attempt`），
  並重置了 Blue Pill。兩路共用 Z2 / Site 2 / DUT，實機操作前需先協調。C-3 遇到其他 OpenOCD 或 admission
  紀錄會拒絕，但無法防止之後才開始的外部操作。
- `z2run.py` 只印遠端輸出最後 60,000 字元（輔助腳本的設計，不是 SSH 限制）；大輸出請在 Z2 上先彙總。

### 9.4 下一步
1. 協調好 Z2 使用權後，`POST /api/jobs` `{"site_id":2,"operation":"flash_cycle", 內嵌 asset}`，
   韌體 `.work/bluepill-ab-20261028/plasma-blue-pill-cdc.bin`（18,768 B，`8d3ffb02…`）。
   驗收：Job success、readback SHA = `8d3ffb02…`、`safe_off`、Site 未 seal、FPGA/journal 未變、
   SWPC heartbeat 恢復且 uptime 重新起算。
2. #1291 Gate 2；9.3 的產品缺口另開 Gate 1 / PR。
3. D6 / D7、OpenOCD Bundle Package kind（§4.5）。
