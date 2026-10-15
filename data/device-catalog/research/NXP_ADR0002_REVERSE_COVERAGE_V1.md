# NXP — OpenOCD v0.12.0 有界反向覆蓋檢查 v1

**執行決策：** User explicitly approved a bounded OpenOCD source → NXP exact-ICPN reverse check. This is a **read-only Phase 1 research prioritization check**, NOT reopening ADR-0002 Phase 2 Programming qualification. No new Production Catalog mapping, UI change, Programming Profile, ROM IAP, real OpenOCD invocation, hardware/HIL, or PPU/Render deployment.

## 結論

> **已確認的 NXP P0 仍為 27 顆；對現有 501 顆有界樣本，本次反向檢查新增 P0 = 0 顆。**
> **不能宣稱 NXP 所有已上市／Active 料號皆已被涵蓋，或未來不可能有其他 P0。**

本次鎖定：

- PLASMA OpenOCD **v0.12.0** pinned upstream commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`；
- 已合併的 NXP v10 **501 顆精確研究料號**，含 P0=27、P1=38、P2=436；
- 已保存的 NXP 官方 **23 個有界產品頁／353 顆 Active** 觀測集合，**不是 NXP 全產品清單**；
- upstream `tcl/target/` 此 commit 的 309 個根目錄項目中，使用固定 NXP 家族檔名規則選出的 **48 個 Target／共用設定來源項目**，並鎖定每一個 Git blob SHA；另鎖定既有 `kinetis.c` 與 `lpc2000.c` Flash Driver SHA。

| 驗證集合 | 數量 | 結果 |
| --- | ---: | --- |
| 既有 v10 NXP exact ICPN | 501 | P0 27 / P1 38 / P2 436 |
| 有界官方 Active snapshot | 353 | **全部 353 都已包含在 501 內**，新增 SKU 0 |
| Active 353 的現有優先級 | 353 | P0 12 / P1 20 / P2 321 |
| 501 中未見於該次 Active snapshot | 148 | P0 15 / P1 18 / P2 115；**不是**非 Active/EOL 宣告 |
| 受限 NXP filename-based upstream Target/Helper | 48 | 5 已研究鏈路、26 舊系列線索、16 i.MX 應用處理器線索、1 RT600 DSP 定義 |
| 501 內與新增舊系列 Config family prefix 交集 | **0** | 未找到新的精確料號 P0 候選 |
| 本次新增 `openocd_software_support=SUPPORTED` | **0** | 沒有執行任何燒錄資格評估 |

## P0 定義與範圍

| 既有 NXP cohort | ICPN | 已鎖定的 Target → Driver 來源線索 | 本次處置 |
| --- | ---: | --- | --- |
| KL25 | 12 | `kl25.cfg → klx.cfg → kinetis.c` | 保留 P0；需要 exact SDID、Flash geometry、安全約束／operation 證據 |
| LPC844 | 7 | `lpc84x.cfg → lpc1xxx.cfg → lpc2000.c` | 保留 P0；缺 exact 商業碼→Part ID／ROM IAP 證據 |
| LPC845 | 8 | 同 LPC84x | 保留 P0；同上 |
| LPC802/804 | 18 | `lpc8xx.cfg` 泛用來源，缺 explicit exact IDs | P1，不因 CFG 存在自動晉升 |
| K32L2 | 20 | `kinetis.c` 家族 Driver 線索，缺已證明的 exact Target／bank | P1，不推論新 P0 |
| MCX/LPC55/KW45/MIMXRT | 436 | 現有指定來源未建立確切有界燒錄路徑 | P2 UNKNOWN，不將 UNKNOWN 誤稱永久 UNSUPPORTED |

### 反向查找到的額外 Target 線索

從官方 pinned `tcl/target/` 原始碼見到 `k40.cfg`、`k60.cfg`、`kl46.cfg`、`lpc11xx.cfg`、`lpc17xx.cfg`、`lpc40xx.cfg` 等早期 NXP／Freescale Target Config。**這些來源入口確實存在，但目前 501 顆精確樣本沒有相應系列的 exact ICPN**，因此 **不能對任何新精確商業料號授予 P0**。例如：

- `k40.cfg` → `target/kx.cfg`、`k60.cfg` → `target/kx.cfg`；
- `kl46.cfg` → `target/klx.cfg`；
- `lpc11xx.cfg`／`lpc17xx.cfg`／`lpc40xx.cfg` → `target/lpc1xxx.cfg`。

這些是**未納入本次 501 ICPN 樣本的其他產品系列**的潛在日後 Source-first 線索；在取得官方 exact ICPN、適用 Target／Driver／Flash 操作適用性之前，不能將它們列為新 P0 或寫入產品 Catalog。

**必須禁止的錯誤類比：**

- `imx6.cfg` 等 16 個 `imx*` 目標主要描述 i.MX 應用處理器，**不是** 501 顆中的 `MIMXRT` 跨界 MCU。
- `xtensa-core-nxp_rt600.cfg` 是 RT600 的 **Xtensa HiFi DSP debug/core 設定**，不是本次 501 顆 MIMXRT 商業料號的 Flash programming 支援證據。
- 根目錄 Config 命中、`source [find ...]`、`kinetis`／`lpc2000` 的 symbol 都**不能**替代 exact silicon identity、Flash geometry、erase/write/verify 軟體資格，亦非實機合格。

## 審核方式與已知限制

來源鎖為 [`nxp-openocd-reverse-target-lock-v1.json`](nxp-openocd-reverse-target-lock-v1.json)：48 個 pinned `tcl/target/*.cfg` 原始 Git blob SHA、來源類型、2 個 Flash Driver SHA。這份 Target 索引是**檔名規則選取**、僅檢查 upstream `tcl/target/` root-level 的一次有界盤點，**不是 OpenOCD 內所有能支援 NXP 的設定、Target/Flash plugin、額外 script/fork 的全量證明**。

- 現有 501 與 353 檔案、舊版 v9 證據及 PLASMA pinned release 使用固定 Git blob SHA 做離線完整性檢查。
- `nxp_adr0002_reverse_coverage_v1.py` 重新讀取 501/353，核對 set 包含關係、P0/P1/P2 分母、舊 family 無交集、48 個 Git blob 鎖及安全界線，對照 [`nxp-openocd-reverse-coverage-v1.json`](nxp-openocd-reverse-coverage-v1.json) 的已核對結論。
- 額外可提供 **真正 checkout pinned commit 的 OpenOCD 原始碼**，執行 `--upstream-root` 逐檔對比全部 48 個 Target 與兩個 Flash Driver 的 Git blob；正常 CI 的離線模式僅驗證鎖定索引及既有來源 SHA，**不能冒充已在 CI 重新下載上游所有 48 個檔案**。
- 負測試會拒絕改寫 P0 分類、憑空增加 Active ICPN、竄改來源 SHA、把 i.MX／DSP 偽裝為 MCU Flash、直接宣稱 software `SUPPORTED`。
- 未完成的 NXP 官方全集母體維持 **UNKNOWN/null**；不因本次差集零值推估全 NXP 的覆蓋率。

```bash
python data/device-catalog/research/nxp_adr0002_reverse_coverage_v1.py --check
python -m unittest data/device-catalog/research/test_nxp_adr0002_reverse_coverage_v1.py -v

# Optional: local checkout of the exact pinned OpenOCD commit
python data/device-catalog/research/nxp_adr0002_reverse_coverage_v1.py \
  --upstream-root /path/to/pinned-openocd-checkout --check
```

## 結案條件與後續

**可關閉的項目：**「原本 501 顆＋另一次官方 353 顆 Active 觀測」的 P0 發現／重複集核對：兩批無新 SKU，既有 P0 維持 27，新增 P0 0。P1 的一次有界檢查 v12 已完成。

**不應關閉的項目：**「整個 NXP 製造商所有 Active MCU、以及所有可能 OpenOCD／Vendor Fork/未來版本」的 P0 全球覆蓋，缺乏完整母體與 runtime/operation 證據。

若未來發現新的 OpenOCD Source/Driver commit、可靠的官方 Exact-SKU 集合、客戶需求，應建立**獨立、受限**重新開案，而不是在這次研究 PR 中隱含擴充整個供應商母體。

**無 Production/Job/Batch/Render/PPU/HIL 變更；任何 PR 合併仍需獨立批准。**
