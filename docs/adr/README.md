# Plasma Architecture Decision Records

本目錄保存 Plasma 已核准的 Architecture Decision Records（ADR）。ADR 用於記錄會長期影響產品架構、runtime ownership、部署、相容性或安全邊界的決策；一般設計說明仍放在 `docs/architecture/`，部署實作與驗收說明仍放在 `docs/deployment/`。

## Status

- **Proposed** — 尚在評估，不能視為產品契約。
- **Accepted** — 已核准，後續實作與文件應遵循；若現況尚未完全符合，必須明確記錄 migration gap。
- **Superseded** — 已由後續 ADR 取代，保留作決策歷史。
- **Deprecated** — 不應再用於新設計，但尚未由單一 ADR 完整取代。

## Records

| ADR | Status | Decision |
|---|---|---|
| [ADR-0001](0001-pynq-system-python-plasma-runtime-separation.md) | Accepted | PYNQ System Python 與 Plasma PPU Python Runtime 分離；Plasma 不依賴或取代 PYNQ System Python。 |
| [ADR-0002](0002-openocd-software-qualified-catalog-visibility.md) | Accepted | 統一 Catalog Level：L0 `DISCOVERED` → L1 `PROGRAMMING_CANDIDATE` → L2 `PROGRAMMABLE` → L3 `PLASMA_VERIFIED`；L0 internal-only，Customer IC Selector 顯示 L1–L3，Job Picker 僅 L2/L3。Catalog visibility、Job selection 與 execution entitlement 分離。 |
| [ADR-0003](0003-runtime-fpga-driver-reconfiguration-boundary.md) | **Proposed** | Runtime FPGA Driver／UIO 選型候選、PPU Configuration Owner、Bitstream 不重啟 Linux 的安全交接；待現場 Kernel／UIO／Bridge 與 Hardware ABI 審核，不是 Accepted Driver。 |
| [ADR-0004](0004-ppu-local-trust-root-deployment-security.md) | Accepted architecture, implementation pending | 每台 PPU 本地信任根、離線 Master／Publisher 雙信任鏈及受保護 Factory Recovery；正式 TLS、憑證與持久化仍待實作。 |

## Maintenance rule

新增或取代架構決策時：

1. 新增一份不可變更決策歷史意義的 ADR；重大方向改變應以新 ADR supersede 舊 ADR，而不是改寫歷史。
2. 更新本 index 的狀態與關聯。
3. 更新 `docs/README.md`，確保 documentation integrity guard 可以追蹤所有 `docs/**/*.md`。
4. 若 ADR 與現有 Current contract 或程式實作存在 gap，必須在 ADR 的 Consequences / Migration 中明確列出，不能把規劃誤寫成已完成能力。
