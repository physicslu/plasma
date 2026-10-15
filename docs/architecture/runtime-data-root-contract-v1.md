# Runtime Data Root Contract v1 — 已安裝 Python Runtime 的強制 CI 規範

**範圍**：PLASMA 的可安裝 Python 模組（`software/python/plasma_*`）對「不在 Python package 內」的 Catalog、IC Support、OpenOCD 研究／來源證據等資料的定位方式。

**回歸事故**：PR #827 建立 `PLASMA_IC_SUPPORT_ROOT`，但後續 NXP #844 仍重複從 `__file__` 推算 root，導致 Render wheel 搜尋失敗。PR #873 修復 NXP、#876 修復 H5/C5 Provider、#877 修復 KL25 executor lock。此規範防止同類錯誤重現，**不修改** Catalog、Programming、OpenOCD binary、PS/PL 或硬體 HIL 授權。

## 一、第一性原理與 Root Ownership

已安裝 Python package 的 `__file__` 只告訴我們**程式檔位於哪個安裝目錄**，並未提供資料部署在哪裡的保證。`site-packages`、wheel 路徑、Docker/Render checkout、APP bundle、Windows/MSI 與 ARMv7 PPU 的 runtime data layout 本質上無關。

**Root locator、evidence integrity、execution admission 是三個不同的控制面，不能互相替代。**

| Data Ownership | Authoritative Runtime Contract | 已有 Loader／驗收 |
|---|---|---|
| Production Device Catalog | `PLASMA_DEVICE_CATALOG_MANIFEST` | `plasma_web.device_catalog`；原始 Manifest／hash／exact 行數原本即檢查 |
| IC Support Profiles、Backend Lock | `PLASMA_IC_SUPPORT_ROOT` | `plasma_core.ic_support`、`plasma_interfaces.kl25_openocd_plan` |
| Full Render OpenOCD / H5/C5 Research Evidence | `PLASMA_RUNTIME_EVIDENCE_ROOT` | `plasma_web.runtime_evidence_root` 與三個 source-only provider/candidate loader |
| NXP Manufacturer evidence | 目前使用 Production Manifest 在 canonical layout 下的父層位置，#873 已修 | `plasma_web.nxp_manufacturer_device_evidence`；目前 canonical layout 之外需另做 explicit root 版本化，不能宣稱支援任意 Manifest 佈局 |
| Wheel 內的唯讀模板／內建資源 | `importlib.resources.files(package)` | 僅限真正隨 wheel 發布的程式資源，不得假冒 repo 外部 research data |

## 二、CI 的客觀涵蓋範圍

`scripts/ci/runtime-data-root-contract.py` 使用 Python AST（不是 grep 字串）掃描所有 `software/python/plasma_*` 目錄下的 `*.py`：

1. **新模組直接引用 `__file__` 一律拒絕**（包括 `Path(__file__).resolve().parents[3]`、`Path(__file__).parent`、`os.path.dirname(__file__)`）。若要定位 package-local assets，改用 `importlib.resources`。
2. **兩個歷史開發環境例外被精確鎖定**：`plasma_core/ic_support.py::_repository_root` 與 `plasma_web/device_catalog.py::_repository_root`。各最多一次直接引用 `__file__`，且只能回傳既有 `Path(__file__).resolve().parents[3]`。這是需日後縮減的技術債，不允許再增加第三個例外。
3. **保護已修正載入器**：NXP、OpenOCD Evidence Resolver、H5/C5 Candidate、OpenOCD Source Reference、Provider Registry 與 KL25 Backend Lock 必須繼續呼叫經審核的 root locator。
4. **CI 自我測試**：合成正向 fixture（明確 resolver、`importlib.resources`）、負向 fixture（新 `__file__` 派生、`os.path.dirname`、擴張／修改歷史例外）以檢查 checker 真正會擋下新回歸。
5. **沿用既有 `Python and PL source tests` → `test` job**，在 pip 安裝與 pytest 之前執行。當 runtime Python 路徑或本 checker 改動時，workflow 會觸發。這不再開另一個 ARMv7/QEMU Build 工作，避免 CI job 重複。

**重要限制**：AST 檢查能防止這次已知的 `__file__` 類型錯誤，但不構成任意路徑 API 的完整靜態證明。`os.getcwd()`／手寫硬編碼絕對路徑／反射與變數重新命名等形式需另外依 Code Review 規範審查。若要讓 GitHub 真正「阻止合併」，必須把既有 `test` check 設為 Repository Ruleset / Branch Protection 的 Required Status Check；僅加入 workflow 不代表能更改 GitHub 設定。本 PR **沒有**更動 Repository Ruleset。

## 三、CI / 手動重現

```bash
python scripts/ci/runtime-data-root-contract.py --self-test
python scripts/ci/runtime-data-root-contract.py
```

使用 CI 假資料把新的 `Path(__file__).resolve().parents[3]` 寫入 `software/python/plasma_web/my_new_loader.py` 應回傳非零狀態，且錯誤訊息含檔案與行號；使用 `default_runtime_evidence_root()`、`default_ic_support_root()` 與 `importlib.resources` 則不觸發本類型檢查。

另需保留前述 PR #873 / #876 / #877 中真實 **non-editable** `pip install software/python` 的執行期驗證；AST 通過不等於已在 wheel 中成功載入檔案。

## 四、Merge / Deployment Gate

- 所有被納入 CI 的 Python 程式碼必須通過 AST Contract Check、現有 pytest / product contract。
- Render 的 Full Runtime 不能將來源證據缺失默默呈現為 unsupported；Slim PPU 可以合法省略 optional research files，但不能影響 required Catalog/IC Support。
- 所有外部資料仍維持 immutable SHA/source 及 Programming Admission 分離；不會因資料可見而新增可燒錄資格。
- 此批次只實作 Repository 內可驗證的靜態 CI 規範，**不變更任何已經上線的 Runtime 讀取程式碼**，不合併 PR #875 或 #872，也不部署 Render、PPU、SWPC。
- PR 必須全數 CI PASS、確認最新 main 與 mergeability，再經 owner 明確批准後合併。任何部署都另行批准。
