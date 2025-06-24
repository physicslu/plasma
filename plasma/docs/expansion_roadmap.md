# 🔧 Plasma 專案未來擴充項目清單

## 1️⃣ 錯誤處理與記錄改善
- [ ] 每次燒錄 log 建立獨立目錄（含 timestamp）
- [ ] 錯誤類型明確分類（verify_error / timeout / connection_failed）
- [ ] 支援 CLI `--verbose` 與 `--logfile` 自定

## 2️⃣ 模擬任務狀態與回傳格式設計
- [ ] 標準化 Server → Client 回應格式為 JSON
- [ ] 每階段燒錄進度可回傳詳細資訊（channel, step, result）

## 3️⃣ 單元測試與整合測試擴展
- [ ] `tests/` 中加入 section_handler 單元測試
- [ ] 模擬 interface，撰寫自動化測試流程
- [ ] CI 中覆蓋率（coverage）統計報告

## 4️⃣ 封裝成 Python 套件
- [ ] 製作 `setup.py` 或 `pyproject.toml`
- [ ] CLI 指令簡化為 `plasma-cli`、`plasma-server`
- [ ] 支援 pip 安裝部署

## 5️⃣ IC 模組與 handler 的版本管理
- [ ] 每個模組加入 `__version__`、`__chip__`
- [ ] CLI 增加 `--list-ic` 指令查詢支援清單

## 6️⃣ WinUSB 實作與跨平台測試
- [ ] 整合 `pyusb` 進行實際 USB 傳輸測試
- [ ] 提供 fake USB 模擬器供單元測試
- [ ] 檢查跨平台（Linux/Windows）支援

## 7️⃣ 文檔與教學
- [ ] 新增 `docs/quick_start.md` 快速上手指南
- [ ] 建立「新增一顆 IC」完整教學模板
- [ ] `README.md` 增加範例與圖示

## 8️⃣ 發佈與版本控管
- [ ] 整合 changelog 與版本發布（CHANGELOG.md）
- [ ] 每次 GitHub Release 打包對應版本
- [ ] CLI 查詢目前系統版本與模組清單

---

> 此清單將隨版本更新與需求調整。
