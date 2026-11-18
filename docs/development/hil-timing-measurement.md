# HIL 兩 Site 並行時間量測（`plasma_hil_timing.py`）

**狀態：Reference。** 本文件說明如何重現 2026-11-18 Z2 兩 Site 並行 Erase/Program/Verify 的時間分析。工具只做觀察：不驅動硬體、不寫入 PPU 狀態，也不決定 Job 結果。燒錄本身仍走既有 Path 2 Work Order 與 `scripts/plasma_programming_load.py`；LA2016 的使用限制以 [KINGST LA2016 工具操作手冊](la2016-tool-operations.md) 為準。

## 1. 量到什麼

| 來源 | 內容 | 子命令 |
| --- | --- | --- |
| LA2016 外部波形 | 每個 Site 的 SWCLK 頻率、SWD 開始／結束、兩 Site 同時活動時間 | `la-capture`、`la-analyze` |
| PPU Job log `stage_timing` | Job 建立的各小步驟、排隊、預檢、Engine／Bundle 驗證、Site 工作階段、Site Worker admission／OpenOCD／revoke、Root admission 分段、快取命中 | `summarize` |
| Path 2 loading report | Batch／Job／Receipt、Readback、SAFE_OFF、CPU／RAM 分階段、OpenOCD PID 重疊 | `summarize` |
| PPU `/proc` 取樣（選用） | admission／OpenOCD 程序起訖、kernel 等待點（lock／flock）、Runtime 主執行緒 CPU | `proc-trace`、`proc-analyze` |
| PPU 上單獨計時（選用） | `read_active`、`preflight_runtime_flash`、`load_engine` 耗時 | `preadmission-profile` |

`stage_timing` 事件由 Runtime 寫入 `/var/log/plasma/<UTC 日期>/SITE<n>/<job_id>.jsonl`，每筆含 `phase`、`t_ms`（從 `job_started` 起算）與 `duration_ms`。`site_worker` 這一筆帶有 `admission_ms`、`openocd_ms`、`revoke_ms`、`admission_start_unix_ms`、`openocd_start_unix_ms`，以及 `admission_root_*`（Root admission 自己回報的分段）。`load_engine_cache`／`qualify_reference_cache` 的 `hit` 表示該 Job 是否沿用已驗證結果。

## 2. 接線與預設通道

| Site | SWCLK | SWDIO |
| --- | --- | --- |
| 1 | CH3 | CH4 |
| 2 | CH0 | CH1 |

接線不同時，`la-analyze` 用 `--site 1=CHx:CHy --site 2=CHx:CHy` 指定。

## 3. 重現步驟

1. **開始錄波**（SWPC，Path 2 派工前；長度涵蓋 Dispatcher 排隊、baseline、Batch 與 recovery，約 190 秒）：

   ```bash
   python3 scripts/plasma_hil_timing.py la-capture --output la.sr --seconds 190 \
     --conn "$LA_CONN"          # 依 LA2016 手冊動態取得；--sigrok 可指定 sigrok-cli
   ```

   `la.sr.capture.json` 記錄實際 sigrok 命令與開始時間。

2. **派送 Path 2 Work Order**：用既有 `scripts/plasma_programming_load.py measure ... --run-batch`。設定檔的 `deployed_sha` 必須等於 Z2 目前的 Runtime git SHA，否則會在建立 Batch 前以 `DEPLOYED_IDENTITY_MISMATCH` 停止，這是正確行為。Work Order 只能使用允許欄位（不要加 `verification`）。

3. **取回 Job log**（Z2，需 root 讀取）：從 loading report 的 `site_results[].job_id` 找 `/var/log/plasma/<日期>/SITE<n>/<job_id>.jsonl`。

4. **分析與彙整**：

   ```bash
   python3 scripts/plasma_hil_timing.py la-analyze la.sr --output la-analysis.json
   python3 scripts/plasma_hil_timing.py summarize --report report.json \
     --job-log site1.jsonl --job-log site2.jsonl --la la-analysis.json --output SUMMARY.txt
   ```

   分析只用標準函式庫；20 MHz × 125 秒的擷取約 50 秒完成。原始 `.sr` 在分析後可刪除，保留 `la-analysis.json` 與摘要即可。

5. **選用：`/proc` 取樣**（Z2，以 root 執行；Z2 系統 Python 即可）：

   ```bash
   python3 plasma_hil_timing.py proc-trace --seconds 200 --interval 0.02 --output run.jsonl.gz
   python3 scripts/plasma_hil_timing.py proc-analyze run.jsonl.gz --output proc-analysis.json
   ```

   取樣本身會占用 CPU（2026-11-18 量到閒置 CPU 由約 51% 升到 93%），只用來判斷先後順序與是否有 lock 等待，不要拿它的絕對時間比較效能。

6. **選用：單獨計時預檢步驟**（Z2，以 Runtime Python 執行；只讀）：

   ```bash
   /opt/plasma/python/3.12.13/bin/python3 -I plasma_hil_timing.py preadmission-profile \
     --job-binding job-binding.json --repeat 3
   ```

## 4. 判讀

- **兩 Site 是否真的並行：** 看 LA `both-active` 與 `start gap`，以及 `openocd start gap`。
- **等待在哪裡：** 比較各 Site 的 `t_ms`。若先開始的 Site 在某一階段停住、等另一個 Site 趕上，就是串行點。`proc-analyze` 的 `lock_or_uninterruptible_waits` 可以排除或確認 lock。
- **時間花在哪裡：** `site_worker.admission_ms`、`openocd_ms` 與各 `duration_ms`。Z2 只有 2 核心，兩 Site 同時跑時 CPU 會滿載，移到背景執行緒只消除排隊，不會減少計算量。

## 5. 2026-11-18 基準

| | 修改前（`a343a6bfa`） | 背景執行緒＋時間戳（`c9e48e9c9`） |
| --- | --- | --- |
| Job 開始時間差 | 2.45 s | 0.875 s |
| LA SWD 開始時間差 | 0.059 s（被拉齊） | 1.118 s（依 Job 順序） |
| 每個 Site 時間 | 14.47 / 12.04 s | 13.82 / 13.82 s |
| Batch／吞吐 | 23.75 s／5288 B/s | 23.50 s／5345 B/s |

同一次 `c9e48e9c9` 量測的主要成本：admission 4.3–4.5 s、OpenOCD 4.7–5.1 s、`qualify_reference` 1.0–1.15 s、`load_engine` 0.7 s。
