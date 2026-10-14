# Installed Python / OpenOCD Source-Only Runtime Evidence Root v1

**範圍：** 稽核 PR #875 中的 A 批次；只修正 ST H5/C5 source-only 候選、Versioned Provider 與 upstream OpenOCD source reference 的部署路徑。**不修改** Production Manifest、NXP 224 ICPNs、OpenOCD executable/runtime attestation、KL25 execution compiler、PPU／Socket／HIL 或控制站 Job/Batch admission。

## 原因及修正

舊版三個資料載入器各自使用 `Path(__file__).resolve().parents[3]` 尋找 `release/openocd.json` 與 `data/device-catalog/research/*`。在非 editable `pip install software/python` 後，`__file__` 位於 `site-packages`，與 repo checkout 無關；UI 查詢 H5/C5 時，optional-by-design 的缺檔路徑可讓候選資料靜默回傳 `None`／空陣列。

本批次新增 `plasma_web/runtime_evidence_root.py`：

1. **Full Render / 明確根目錄**：`PLASMA_RUNTIME_EVIDENCE_ROOT=/abs/path/to/checkout`；在啟動前完成受鎖定的 H5+C5 362 件 Candidate Registry、Provider Registry（OpenOCD upstream 4176、H5 190、C5 172）及 Upstream source-reference 校驗；缺任何必要檔案直接 fail-closed，不可自動回傳空陣列。
2. **標準 Source checkout**：沒有環境設定時，只在 `PLASMA_DEVICE_CATALOG_MANIFEST` 對應的 canonical `data/device-catalog/production/icpn-v1-manifest.json` 確實存在時定位 checkout；沒有使用 site-packages `__file__`。任意移動 manifest 不會再猜測相對第幾層。
3. **Slim PPU**：如未宣告 `PLASMA_RUNTIME_EVIDENCE_ROOT` 且完全缺少一組可選研究來源，保持既有無候選 metadata 行為；**但部分來源存在／來源內容不符 SHA 驗證時一律 fail-closed**。僅允許合法省略，不會自行製造後端或宣稱支援燒錄。
4. **Render Startup Smoke**：保留原有 ST `STM32F103C8T6`、NXP `NXP`／`MCXA132VFM` 的檢查；新增 `STM32H503CBT6` 與 `STM32C531CBT6` 的 Source Candidate／Source Reference／Provider metadata 分離驗證，並要求這兩筆的 `mapping_status=no_mapping`、`executable=false` 等安全條件。
5. **非 editable CI**：`python -m pip install software/python`，確認套件確實由 `site-packages` 執行，回歸驗證 H5/C5 共 362 個候選、NXP 224 顆查詢維持正常、Provider 不具 executable/HIL 權限；另涵蓋 explicit missing、partial missing、slim no-evidence 的負測試。

## 稽核門檻

| 資料領域 | Full Render | Slim PPU |
|---|---|---|
| Production ICPN Manifest | 明確指定、SHA/row 檢查；不在本 PR 更動 | 使用既有部署契約 |
| IC Support | `PLASMA_IC_SUPPORT_ROOT`；不在本 PR 更動 | 使用既有部署契約 |
| OpenOCD source evidence | `PLASMA_RUNTIME_EVIDENCE_ROOT` 必填且全部必要證據檔存在 | 可省略全部 research-only 檔案；缺失時 metadata 不可偽造 |
| ST H5/C5 source-only graph | 190 H5 + 172 C5 retained immutable | 缺少 source-only 文件時不得將其視為實機 supported |
| OpenOCD providers | upstream 4176 / H5 190 / C5 172 source-only | 不得宣稱 installed binary、physical operation 或 qualification |

既有校驗包含 Git blob SHA、官方 Source commit 以及 H5 offline build artifact fingerprint；此改動不降低任何原有驗證門檻。

## 驗證指令

```bash
python -m pip install software/python
export PLASMA_DEVICE_CATALOG_MANIFEST="$PWD/data/device-catalog/production/icpn-v1-manifest.json"
export PLASMA_IC_SUPPORT_ROOT="$PWD/data/ic-support"
export PLASMA_RUNTIME_EVIDENCE_ROOT="$PWD"
python -m unittest discover -s software/python/tests -p 'test_runtime_openocd_evidence_root_v1.py' -v
python -m unittest discover -s software/python/tests -p 'test_icpn_backend_candidate_registry_v1.py' -v
python -m unittest discover -s software/python/tests -p 'test_openocd_versioned_provider_registry_v1.py' -v
python -m unittest discover -s software/python/tests -p 'test_icpn_backend_source_reference_v1.py' -v
python -m unittest discover -s software/python/tests -p 'test_nxp_render_evidence_root_v1.py' -v
bash -n scripts/render-start.sh
```

**合併門檻：** 主線無衝突、相關 CI 全部通過、使用者明確合併批准；Render 生產部署仍須獨立核准。KL25 execution lock 與更廣泛的 Data Root 標準化屬後續 B/C 批次，不應混入。
