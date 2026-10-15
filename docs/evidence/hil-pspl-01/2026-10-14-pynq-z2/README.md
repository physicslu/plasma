# HIL-PSPL-01：PYNQ-Z2 Identity-only 實機驗收

硬體執行日期：**2026-10-14**（Asia/Taipei）。封存日期：2026-10-15。
**Overall HIL-PSPL-01：FULL PASS**，範圍限於此次單一 PYNQ-Z2 的 Identity-only
PS Linux → AXI GP0 → PL Identity → PS Linux 讀回，以及原平台復原。
不是 FPGA SWD Master、完整 Programming Site 或實際 IC programming 資格認證。

## 平台與產物來源

- PYNQ-Z2 / Zynq-7020，FPGA `xc7z020clg400-1`，ARMv7 Linux，PYNQ 3.1.1。
- [Identity-only 工程](../../../../pl/projects/z2-identity/README.md)，[PR #881](https://github.com/physicslu/plasma/pull/881) 已合併。
- Bitstream 來源 Git SHA：`f3249a87e1f3e453efd4c82e0241fa562e75fb71`；Build ID：`f3249a87e1f3e453efd4c82e0241fa56`。
- Bitstream version `0.1.0`、ABI `1`、SWD flags `0`。Vivado 2026.1；固定 board preset。
- GP0 / FCLK0 100 MHz / 受控 reset；無 EMIO SWD、PMODB 或外部 PL I/O。
- AXI base `0x40000000`，segment 4 KiB，八個有效 32-bit 暫存器共 32 bytes。
- Bitstream、HWH、原 build manifest 與載入用 BIN 的 SHA256 見 [artifact-checksums.sha256](artifact-checksums.sha256)。
  完整二進位留在本地，不納入 Git。

原 build manifest 是載入前的不可變紀錄，仍含 `physical_hil=NOT_RUN` 與
`loading_safety=NOT_QUALIFIED`。本封存以獨立的 [acceptance.json](acceptance.json)
記錄後來實際執行的驗收，不回寫原 manifest，也不擴大到其他板卡或用途。

## 實際 Identity 讀回

操作員於 `23:53:47+08:00` 載入一次候選，FPGA Manager 返回 `operating`。
檢查 kernel 與 FCLK0 後，於 `23:57:51+08:00` 只讀下列八個地址；沒有 AXI write。
[identity-readback.log](identity-readback.log) 是經審查的原操作日誌字面摘錄。

| 地址 | 暫存器 | 實際值 | 結果 |
|---|---|---|---|
| `0x40000000` | magic | `0x504C534D` | PASS |
| `0x40000004` | bitstream_version | `0x00000100` | PASS |
| `0x40000008` | hardware_abi_version | `0x00000001` | PASS |
| `0x4000000C` | capability_flags | `0x00000000` | PASS |
| `0x40000010` | build_id_word_0 | `0xF3249A87` | PASS |
| `0x40000014` | build_id_word_1 | `0xE1F3E453` | PASS |
| `0x40000018` | build_id_word_2 | `0xEFD4C82E` | PASS |
| `0x4000001C` | build_id_word_3 | `0x0241FA56` | PASS |

八個讀值獨立依 artifact manifest 推導比對，全數吻合。這證明此次實機 GP0
Identity MMIO 讀回；**沒有直接量測 AXI RRESP 訊號，也沒有 FPGA binary readback**。

## 原平台復原

於 `23:57:51+08:00` 載入一次已驗證的 `base.bin`，Manager 返回 `operating`；
於 `23:58:37+08:00` 完成服務與 Gateway readiness 核驗。
[restoration.log](restoration.log) 區分原日誌摘錄與後續唯讀核驗的正規化摘要。

- 原 UIO 名稱／地址／driver binding 恢復。UIO 編號重排，不能以固定 index 判斷資源身分。
- Jupyter 與四個 Plasma 服務皆 active。公鑰 SSH 復原核驗成功。
- Jupyter 登入頁 HTTP 200；未認證 API HTTP 403。僅驗證 HTTP 回應，不宣稱 notebook kernel 執行成功。
- Gateway `/api/health/live`、`/api/health/ready` 均 HTTP 200，`ok=true`、`gateway=alive`、`execution=ready`。
- Metadata 與 pre-load 備份 checksum 一致。前後 bindings、完整 clock snapshot 與 Gateway health 相同。
- FCLK0 啟用且維持 100 MHz。此次新增 kernel events 僅有候選與 base 載入訊息，未觀察到新增 configuration／AXI 錯誤。
- 未執行 DDR reinitialization、`ps7_init` 或任意手動 PS register writes；未需緊急斷電復原。
  保留的 DDR preset metadata 不等於 DDR qualification。

## PASS / FAIL / NOT RUN

| 檢查 | 結果 |
|---|---|
| `candidate_artifact_integrity` | PASS |
| `candidate_fpga_configuration` | PASS |
| `identity_mmio_8_of_8` | PASS |
| `axi_gp0_identity_readback` | PASS |
| `original_base_restoration` | PASS |
| `uio_driver_bindings` | PASS |
| `public_key_ssh_recovery` | PASS |
| `jupyter_http_responsiveness` | PASS |
| `plasma_gateway_liveness` | PASS |
| `plasma_gateway_readiness` | PASS |
| `original_services_active` | PASS |
| `metadata_restoration` | PASS |
| `fclk0_preservation` | PASS |
| `new_kernel_error_check` | PASS |
| `direct_axi_rresp_observation` | NOT RUN |
| `axi_write_qualification` | NOT RUN |
| `authenticated_notebook_kernel_execution` | NOT RUN |
| `fpga_swd_master_qualification` | NOT RUN |
| `real_ic_programming` | NOT RUN |
| `fpga_binary_readback` | NOT RUN |
| `ddr_reinitialization` | NOT RUN |
| `ps7_init` | NOT RUN |
| `emergency_power_recovery` | NOT RUN |

此次範圍內 FAIL 項目為 0。FULL PASS 不包含 NOT RUN 項目。
UART／實體電源待命由操作員確認；本封存不把未實際使用的緊急復原路徑記為測試 PASS。

## 證據封存與公開邊界

原始 51 檔共 229,250 bytes，全部重新讀取並核對下載時的 Z2 SHA256 清單；
完整集合未修改且留在 SWPC。`final-verification.json` 為後續唯讀核驗摘要，
另列為 supporting record，不混入原始 51 檔計數。

[evidence-manifest.json](evidence-manifest.json) 保存全部原始檔的相對識別與 SHA256、
supporting records 的 SHA256，以及公開衍生檔的來源／摘錄行號／去識別化規則。
公開檔的 digest 排除 manifest 本身，以避免循環 checksum。

原始 kernel、process、socket、service 與 full clock logs 不公開；其中含主機識別、
私有位址、操作員絕對路徑、程序與系統拓撲、UUID 等資訊。公開紀錄採技術結果 allowlist，
不包含 SSH keys、認證資料、tokens、私有主機識別、完整系統配置或 Bitstream/BIN。
Metadata 僅保留 hash 與比對結論，不公開 pickle 內容。

這次封存沒有連線或改變 Z2、重新載入 FPGA、讀寫 live registers、重啟服務、
重新建置 Vivado；使用的是已完成實機測試的原證據。
