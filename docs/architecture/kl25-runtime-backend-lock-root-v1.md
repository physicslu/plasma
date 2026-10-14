# KL25 Programming Backend Lock — Installed-runtime Data Root v1

**批次 B，根據 Runtime Data Root 架構稽核 #875；前置批次 A：#876 已合併。**

## 目標與既有問題

`software/python/plasma_interfaces/kl25_openocd_plan.py` 原本以 `Path(__file__).resolve().parents[3]` 推算 repo root，再讀取 `data/ic-support/benchmarks/nxp-kl25/backend-implementation-lock.json`。在 `pip install software/python`（非 editable）後，Python 模組改位於 `site-packages`，無法可靠定位 repository-owned lock。路徑錯誤將造成 KL25 Plan Compiler 的配置異常，但**目前預設 Compiler Registry 並沒有 KL25 Production Operation Admission**，所以不能宣稱已造成正式實機燒錄事故。

## 實作契約

1. **重用已上線的 `PLASMA_IC_SUPPORT_ROOT`**（#827），不用新增 KL25-specific 路徑環境變數。`load_backend_lock()` 透過 `plasma_core.ic_support.default_ic_support_root()` 取得原始碼 checkout 或部署明確指向的 IC Support 根。
2. 將相對路徑固定為 `benchmarks/nxp-kl25/backend-implementation-lock.json`；不存在、不可讀、JSON 壞檔時，以 **`PlasmaError(CONFIG_INVALID)`** fail-closed，不從 CWD、wheel 安裝目錄或任何其他位置 fallback。
3. 驗證完整 canonical JSON SHA-256 與**事先核准的 implementation content lock digest** `877b3fd9c0b9f8dc3191eb53393e5670efb93b9952ac1747bded155ebcaef4d1`，避免修改後重新計算 JSON 自含 `lock_digest` 就可通過。維持 `trust_boundary.production_admission=false`、`hardware_behavior_validated=false`、`destructive_security_operation_admission=false` 及原設定 target。
4. **不要混同兩個獨立的雜湊**：上述 `877b...` 是 `backend-implementation-lock.json` 的原始證據內容鎖；Compiler Registry 的 `KL25_BACKEND_LOCK_DIGEST=7628554b...` 是另一個 Operation Admission/Compiler Binding 參照。兩者不同且原始設定**沒有被修改**。
5. 繼續使用既有 Profile / Compiler Registry / OpenOCD 程式路徑，**不加入任何 KL25 Operation Admission**，不開啟 OpenOCD runtime、真實 Silicon/PPU/FPGA/SWD、FCF 危險操作或 Runtime Ready。

## CI/驗收

使用非 editable `pip install software/python`，並確認 `plasma_interfaces.kl25_openocd_plan.__file__` 確實位於 `site-packages`：

- 正常載入原有 lock，證實 `__file__` 被模擬搬入虛擬環境仍使用明確 IC Support root。
- 缺檔、無效 JSON、型別異常、修改後自動重算 lock digest、未設定 root 等負測試均必須 fail-closed。
- 四類 KL25 Operation（PROGRAM／ERASE／READ／VERIFY）預設仍由 Compiler Registry 拒絕。
- 原有 `test_kl25_openocd_plan.py`、`test_kl25_openocd_executor.py` 的模擬程序僅證明 software-only；不做實機寫入、Erase 或電子驗證。
- 新增專用 Regression Guard，保護剛修復的 KL25、NXP、H5/C5 OpenOCD loader 不回退為 `Path(__file__).resolve().parents[3]`。
- 持續驗證 `test_compiler_registry.py` 與 `test_ic_support_resolver.py`，避免破壞 ST 正式 admission 及 Render 路徑契約。

## 可重現指令

```bash
python -m pip install software/python
export PLASMA_IC_SUPPORT_ROOT="$PWD/data/ic-support"
export PLASMA_DEVICE_CATALOG_MANIFEST="$PWD/data/device-catalog/production/icpn-v1-manifest.json"
python -m unittest discover -s software/python/tests -p 'test_kl25_runtime_root_contract_v1.py' -v
python -m unittest discover -s software/python/tests -p 'test_kl25_openocd_plan.py' -v
python -m unittest discover -s software/python/tests -p 'test_kl25_openocd_executor.py' -v
python -m unittest discover -s software/python/tests -p 'test_compiler_registry.py' -v
python -m unittest discover -s software/python/tests -p 'test_ic_support_resolver.py' -v
```

## 授權與部署邊界

這是 KL25 **路徑及鎖定驗證** 的功能，不修改 `data/ic-support` 內容、Operation Admission Projection、Compiler Binding、REST API、NXP 224 個可查 ICPN、正式 Catalog 4,853 件或任何 PPU/HIL readiness。**PR 合併與 Render/PPU 部署需各自明確批准**。

若未來部署環境不含原始碼 checkout，需明確配置 `PLASMA_IC_SUPPORT_ROOT`，並依 Product packaging 策略保留 KL25 implementation lock（只有在 Compiler 路徑真的需要時才應納入 release payload）。「能載入 lock」永遠不等於「授權執行」。
