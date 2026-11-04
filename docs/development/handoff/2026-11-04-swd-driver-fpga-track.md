# 交接：SWD Driver / FPGA 這一路（2026-11-04）

狀態：工程交接文件。本文件不授予任何 Gate 1 範圍、硬體操作、部署或合併權限；
這些仍依 [AGENTS.md](../../../AGENTS.md) 的 Gate 1 / Gate 2 規則。

另一路（整合）的交接見
[2026-11-04-swd-integration-track.md](2026-11-04-swd-integration-track.md)。
兩路的**介面契約**在本文 §6，兩份文件內容一致。

## 1. 這一路的範圍

| 負責 | 不負責（屬於整合那一路） |
|---|---|
| PL SWD IP RTL（`pl/rtl/swd/`）、Vivado Image、Image 信任登記 | Runtime / Site Worker / Package / REST / Manager |
| `plasma_swd` OpenOCD adapter（`software/native/swd/`）與它的 ARMv7 CI build | `/etc/plasma/site-worker-engine.json` 的部署與切換 |
| 這兩者的 host 測試、cocotb、Z2 HIL（直接以 root 跑 OpenOCD） | Bootstrap / Runtime kit 的部署流程 |
| `scripts/z2/hil/abi5_openocd_*` 範本、runbook | `ppu_site_adapter_abi5.py` 的 argv（但要遵守 §6 的使用規則） |

## 2. 目前狀態（main `8ab369f9d`，2026-11-04 更新）

| 項目 | 值 |
|---|---|
| 現行 Image | `z2-independent-swd-v5-d0add58c`（Vivado run 41648270405）。BIN `0d99ecaf…`、HWH `0b0e32c2…`、Manifest `4e33fee5…` |
| 淘汰的 Image | `ab79b04e`、`bd976140`（已從 B2 contracts、Root devmem 表、releases、fixtures 移除） |
| 現行 adapter 原始碼 | pipeline 版（PR #1287）。ARMv7 CI build `b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861`（run 41674144305，source `9578dbbda`） |
| 前一版（逐筆） | `b916b9f3f9bd240699db83ac37c1f570cb0008876532bde0e2c97102f50db6ca`（run 41663509036，source `4f107b10d`） |
| Z2 上的 OpenOCD 目錄 | `0.12.0-5088db4c9154`（上游）、`0.12.0-9ea7f3d647c8`（Runtime kit）、`…-plasma-swd-b916b9f3f9bd`、`…-plasma-swd-b8a7db670649` |
| Z2 FPGA | `d0add58c`，Keep Loaded，Active Set gen 6 |
| Z2 Bootstrap / privileged tree / Runtime | main `3d0f911c7`（code manifest `c30404a3…`，Runtime `0.2.1-3d0f911c7385`）。本路自那之後**沒有**再部署或操作 Z2；#1286 的部署屬整合那一路，以其交接文件為準 |
| DUT | Blue Pill STM32F103C8T6 在 **Site 2（PMODB JB1/JB2）**，跑 CDC heartbeat 韌體 `8d3ffb02…`（SWPC `ttyACM0`，`cafe:4001`） |

## 3. 已完成（Z2 驗證與 host 驗證分開列）

### RTL（`pl/rtl/swd/plasma_swd_site_axi_lite.sv`）
- 每 Site 獨立 AXI4-Lite slave，16 筆 command FIFO + 16 筆 tagged response FIFO，engine 自動連續派送。
- `0x68 IDLE_CYCLES`（RW，8..255，reset 及 MODE OFF 時為 8），每筆 CMD_PUSH 時鎖定。
- `0x08 HALF_PERIOD`：SWCLK = 100 MHz / (2 × HALF)，最小 4（12.5 MHz）。
- PARITY / TIMEOUT / ABORT 會鎖住 `fault_q` 並停止派送；WAIT / FAULT / no-ACK 不會。

### Adapter（`software/native/swd/`）
完整契約見 [runbook §9/§10](../swd-abi5-openocd-dpidr-hil-runbook.md)。重點：
- 只做硬體職責：root、reload fence + Site lock、attach 時一次確認 PL 有載入 Image、Site ID、MMIO 白名單、恢復 OFF / SAFE_OFF。**不讀 admission record，不讀電氣確認紀錄，MMIO 熱路徑上不讀任何檔案。**
- `ap_delay_hint` → `IDLE_CYCLES`；queue 256，滿了自動送出；pipeline 最多 16 筆在 RTL 裡。
- WAIT：ABORT 後重送——**只在 target 未設 ORUNDETECT 時走得到**；OpenOCD 會設 ORUNDETECT，實際上整批失敗、由 OpenOCD 重連（見 §3 host 驗證）。FAULT / no-ACK：照實回報、Site 保持可用，由 OpenOCD 重連；latched 錯誤：`CONTROL=4` 後 RW1C `ERROR`。
- `adapter speed` → `HALF_PERIOD`，預設 500 kHz（`plasma_swd site N` 時若還沒設定）。

### HIL 結果（Site 2，`reset halt` 流程，LA2016 全程擷取 + sigrok 解碼）

| SWCLK | write 18,768 B | read | 解碼 ACK |
|---|---|---|---|
| 0.5 MHz（逐筆） | 755 ms，SWCLK 活動 77 % | 665 ms | 全 OK |
| 0.5 MHz（pipeline） | 686 ms，93 % | 530 ms，96 % | 14,146 全 OK |
| 1 / 2 MHz | 623 / 597 ms | 277 / 177 ms | 全 OK |
| 3.846 / 5.0 MHz | 596 / 597 ms | 177 / 177 ms | 全 OK（5 MHz 有 1 次 WAIT，之後恢復；恢復機制見 §3 host 驗證的 ORUNDETECT 發現，未證實是哪一層重試） |
| 7.143 MHz（要求 8） | **FAIL**：init 時 link 斷（NEED_RESET），未 erase | — | — |

- write 停在約 0.6 s：STM32 寫 Flash 本身的時間。read 在 2 MHz 以上停在 177 ms：PS 端瓶頸。
- STM32F103 官方文件沒有寫 SWD 上限；HCLK/6 的說法不成立（8 MHz HCLK 下 5 MHz 通過）。
- **建議工作頻率 2 MHz，已驗證上限 5 MHz。**

證據（SWPC 本機，不在 Git）：`.work/z2-bluepill-heartbeat-flash-20261103/`、`.work/z2-swd-pipeline-flash-20261104/`、`.work/z2-main-3d0f911c7-deploy-20261104/`。

### Host 驗證（2026-11-04，不是 Z2/HIL 結果）

**C adapter 跑在 RTL 模擬上**（PR #1290，`pl/AGENTS.md` §4A）
- `plasma_swd_fifo_core.c` 原封不動編成 `.so`，以 ctypes + `cocotb.external`／`cocotb.function` 把 `read32/write32/write_barrier` 接到 AXI BFM，驅動單 Site RTL（`pl/sim/swd_c_core_site_tb.sv`）。
- Target 用 `EdgePhaseTarget`（`pl/verification/cocotb/swd_c_core_bridge.py`）：原本的 `VirtualSWDTarget` ACK 晚一個 SWCLK 邊緣，不符合 ABI-v5 取樣時序，不能直接拿來接 ABI-v5 RTL。
- 11 個案例（`pl/verification/cocotb/test_swd_c_fifo_core.py`）全 PASS：admit / line reset / DPIDR / `recover_off`、pipeline（RTL FIFO 同時 ≥ 8 筆）、256 筆 queue 自動送出、`ap_delay_hint` → `IDLE_CYCLES`、中段 FAULT、中段 PARITY（RTL 停止派送，`CONTROL=4` 後 RW1C）、TIMEOUT、無 ACK（BAD_ACK → NEED_RESET）、無 ORUNDETECT 的 WAIT（回報、不重送）、錯誤 Site 位址。

**Site 規則 checker**（PR #1292，`pl/AGENTS.md` §3）
- `pl/verification/sva/plasma_swd_site_checks.sv` 以階層參照掛在 `swd_two_site_axi_tb` 與 `swd_c_core_site_tb`，所有 Site 回歸（8 + 11 個案例）每個 FCLK 都檢查。
- Icarus 11 不支援 `bind` 與 concurrent `assert property`：全部是 immediate assertion + 歷史暫存 + shadow 佇列，不宣稱 temporal SVA 語意。
- 規則：FIFO 深度上限；`IDLE_CYCLES` 範圍與 MODE OFF 預設 8；非 NORMAL+enable 時 pad 釋放；MODE 只在靜止時切換；`fault_q` 只由 PARITY/TIMEOUT/ABORT 鎖住、鎖住時不派送、清空後才解鎖；discard 只在 fault 時且清空 FIFO；派送與 completion 依 push 順序；retained response 不變；`IDLE_CYCLES`／`HALF_PERIOD` 在 PUSH 時鎖定；idle 相位 SWDIO 拉低且 clock 數 = 鎖定值；SWCLK HIGH = 半週期；engine 回應穩定、有界完成。
- 非空轉證明：`test_site_checker_reports_mutated_rule` 對 RTL **暫存副本**做 6 個突變，各自被對應規則名稱抓到。只證明測試走過的路徑；形式驗證（SymbiYosys）未做。

**發現與觀察（都未修）**
1. **ORUNDETECT 資料相位缺失（影響實機）**：OpenOCD 的 `dap_dp_init` 會設 ORUNDETECT；ADIv5 規定此時 WAIT/FAULT 後 host 仍須送 33 clock 資料相位，但 engine 把 `cmd_error_data_phase` 固定為 0。模擬中 target 把後續 idle + 下一個 request 當成寫入資料吃掉（WDATAERR），下一筆 BAD_ACK、其餘 NEED_RESET；C 的 WAIT → ABORT → 重送路徑走不到。整批失敗但不亂序、不重送，重連可恢復。現況由 `wait_with_orundetect_has_no_data_phase_and_desynchronises` 記錄，RTL 修好後要改這個測試。
2. **`fault_q` 跨 MODE OFF 保留**：只有 `ERROR` RW1C（且 MODE NORMAL、engine 不忙、命令 FIFO 空、無未收回應）或 AXI reset 能解鎖；產品路徑上只有 adapter（`take_one()`、`recover_off()`）會寫。但 MODE OFF 不清 `fault_q`，`recover_off()` 在 MODE 已是 0 時直接返回，`admit()` 也不檢查 STATUS bit3。若有程式沒清 `ERROR` 就關 MODE，下一個 owner 派送被鎖、輪詢逾時回報 BAD_RESPONSE。
3. TIMEOUT 若發生在讀取資料相位中途，target 仍在驅動 SWDIO，下一個 line reset 會短暫對打。預設預算 1,000,000 FCLK（10 ms）且 SWCLK 由 RTL 自己產生，正常不會發生。

## 4. 待辦

**Owner 2026-11-04 指示延後**（之後再排）：
- **分辨 7.1 MHz 失敗是 DUT 還是接線**：7.143 與 10 MHz 各做兩種只讀測試，(a) `halt`（HCLK 72 MHz）(b) `reset halt`（HCLK 8 MHz）。只有 (b) 失敗 → 跟 DUT HCLK 有關；兩者都失敗 → 偏向 I/O 時序。不寫 Flash；結束後用 2 MHz `reset run` 恢復。需 Gate 1。
- **TIMING-18**：依上一項結果決定補外部 I/O 約束或在 runbook 固定上限。

**可接著做**（每項都需 Gate 1）：
1. **RTL 的 ORUNDETECT 資料相位**（§3 發現 1）：WAIT/FAULT 後依 CTRL/STAT.ORUNDETECT 送 33 clock 資料相位，或讓 WAIT / FAULT 也停止派送；需要新 Image、信任登記、HIL。替代方案：adapter 不設 ORUNDETECT（但 OpenOCD 在 `dap_dp_init` 設定，需確認能否不改 OpenOCD 本體）。
2. **`fault_q` 縫隙**（§3 發現 2）：選項有 RTL 在 MODE OFF 清 `fault_q`（新 Image），或 `admit()`／`recover_off()` 處理 MODE 0 + fault。需 owner 決定；注意不可新增阻擋性檢查。
3. **Site 1（PMODA）實機**：目前只有 Site 2 有 DUT；兩個 Site 同時運作也沒測過（需 owner 接線）。
4. （選擇性）IRQ（RTL 已有完成中斷，PS7 GIC 未接，adapter 目前輪詢）。
5. （選擇性）形式驗證：SymbiYosys 未安裝，安裝前需 owner 同意。

## 5. 怎麼做（流程與工具）

| 工作 | 方法 |
|---|---|
| RTL 模擬 | `PYTHONPATH=software/python pytest pl/verification/test_swd_independent_axi_rtl.py`（需 iverilog 11、gcc、cocotb 1.9.2、cocotb-test 0.2.6、pytest 8.4.2）。內含雙 Site 測試、C core 測試（自動編 `.so`）、checker 突變測試，約 2 分鐘 |
| 只跑 C core 單一案例 | `COCOTB_TESTCASE=<案例名> pytest … -k c_fifo_core`；cocotb 輸出要加 `-o log_cli=true -o log_cli_level=INFO` 才看得到 |
| 新增 Site 規則 | 加在 `plasma_swd_site_checks.sv`（失敗訊息格式 `PLASMA_SVA <rule>`），並在 `CHECKER_MUTATIONS` 加一個會觸發它的 RTL 暫存副本突變；突變必須選一個真的會走到該路徑的測試案例 |
| C host 測試 | `software/python/tests/test_swd_native_c_compilation.py`；直接編：`gcc -std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined plasma_swd_fifo_core.c tests/test_plasma_swd_fifo_core.c`（fake bus 已模擬 RTL FIFO、fault latch、DP overrun） |
| OpenOCD ARMv7 build | PR 觸發 `swd-openocd5088-armv7-candidate.yml`，artifact `plasma-openocd5088-armv7-candidate`；`candidate-evidence.json` 的 `plasma_source_sha` 要等於 PR HEAD |
| Vivado Image | Issue #981 `/plasma-dispatch work-order 981`（`capability: vivado-host-build`、`project: pl/projects/z2-swd-independent`、`board_repo_sha e02d6a38…`）；BIT→BIN 為 bootgen 等效 word-swap + `0x20000000` NOP（`pl/hil/swd04/staging.py` 的 `verify_bin`） |
| 新 Image 信任登記 | `pl/hil/releases/<id>/plasma-image-manifest.json`、`scripts/ppu-fpga-image-contracts.json`、`pl/hil/fpga_image_admission.py` 的 `DEVMEM_INDEPENDENT_IMAGES`、fixtures；照 Replace-by-Default 淘汰舊的 |
| 部署到 Z2（HIL 用） | OpenOCD：`scripts/z2/hil/abi5_openocd_dpidr/deploy_tpl.py`（SSH 並排安裝）。Image：Bootstrap kit + privileged tree（SSH root 腳本，自動 rollback）後走 B1→B2→B3 `fpga_load=true` |
| HIL 燒錄 | `scripts/z2/hil/abi5_openocd_flash/flow_tpl.py`（單一 session 完整流程，**`reset halt`**）＋ `la_full.py`（LA2016 全程擷取、依 300 ms 空白分段）；`act_tpl.py` 為每動作一個 session 的版本 |
| LA2016 | `/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage`（SHA `b551cb26…`），CH0 = SWCLK、CH1 = SWDIO、CH2 = 3.3 V 參考；> 5 MHz 用 200 MHz 取樣 |
| heartbeat | `docs/evidence/bluepill-z2-flash-2026-10-27/scripts/cdc_heartbeat.py after_reset`（輸出檔已存在時會拒絕，換目錄） |
| 失敗後恢復 | MCU 停在 halt：2 MHz 跑 `reset halt; flash verify_image …; reset run`；Flash 被擦：2 MHz 重跑完整流程 |

## 6. 兩路之間的介面契約

**這一路提供：**
1. 每個 adapter 版本 = 一個 ARMv7 CI artifact，記錄 CI run、PR source SHA、`openocd` SHA256、`plasma_swd_site_admission.py` SHA256。安裝目錄名固定為 `/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154-plasma-swd-<openocd SHA256 前 12 碼>`。
2. Adapter 的 OpenOCD 使用規則：
   - `adapter driver plasma_swd`、`plasma_swd site <1|2>`、`transport select swd`。
   - 在 `-f target/stm32f1x.cfg` **之後**設定 `adapter speed <kHz>`（該 cfg 會強制 1000）。建議 2000，已驗證上限 5000。
   - **任何 Flash 操作之前必須 `reset halt`，不能只 `halt`。**
   - 不需要 admission record 或電氣確認紀錄。adapter 需要 root、PL 已載入 Image（Root journal `IMAGE` + 同一個 boot）、Site lock 可取得。
3. 現行 Image ID 與它的信任登記（§2）。

**這一路需要整合那一路配合：**
- 新 adapter build 要成為 Runtime 使用的版本時，由整合那一路更新 `/etc/plasma/site-worker-engine.json` 並在 Runtime quiesce 下重啟 Site Worker。
- 不要修改 `software/native/swd/`、`pl/rtl/swd/`、`scripts/z2/plasma_swd_site_admission.py` 的行為；有需求請開 issue 或在交接文件留言，由這一路處理。

## 7. 規則提醒

- Gate 1：新的實作或硬體操作前要有 owner 核准的計畫；Gate 2：每個 PR 合併前要 owner 核准指定 HEAD。
- 不新增任何阻擋性檢查、fail-closed 前置條件或核准步驟，除非 owner 要求（owner 2026-11-03 的明確指示）。
- PASS / FAIL / NOT_RUN 必須對應實際觀察；host 測試、CI、mock 不等於 Z2 或 DUT 結果。
- 只停止確定的 PID，不用 `pkill`/`killall`；刪除前先看目標並備份（例：`/var/backups/plasma-openocd-retired-20261104T063801.tar.gz`）。
