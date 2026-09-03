# ADR-0001: PYNQ System Python 與 Plasma PPU Runtime 分離

- **Status:** Accepted
- **Date:** 2026-09-03
- **Scope:** PPU / PYNQ-Z2 deployment runtime ownership
- **Related:** `docs/deployment/ppu-runtime-packaging.md`, `docs/deployment/product-deployment-foundation.md`

## Context

目前 Plasma 的 PPU 硬體開發平台是 PYNQ-Z2。實際使用中的 Z2 PYNQ Linux image 暴露的 System Python 為 Python 3.10，而 Plasma Python package / PPU runtime baseline 要求 Python >= 3.11。

這形成兩個不同的 runtime ownership domain：

```text
PYNQ System Runtime
└── Python 3.10
    ├── PYNQ framework
    ├── Jupyter
    ├── board support
    └── OS-integrated tooling

Plasma PPU Runtime
└── Python >= 3.11
    ├── Plasma Server
    ├── Plasma Gateway
    └── PPU control logic
```

若 Plasma 直接依賴 `/usr/bin/python3`，Z2 deployment 會被 PYNQ image 的 Python 版本綁定；若反過來直接升級或取代 PYNQ System Python，則可能破壞 PYNQ、Jupyter、board libraries 或其他 image-integrated software 的相容性邊界。

目前 `ppu-runtime` packaging 仍以 target 上既有的 Python >= 3.11 執行 `ppu.pyz`，readiness audit 也將 Python < 3.11 視為 deployment blocker。因此本 ADR 接受的是產品架構方向，現有 deployment implementation 仍有 migration gap。

## Decision

Plasma 正式採用以下 runtime ownership rule：

> **Plasma PPU must not depend on or replace the PYNQ System Python. The Plasma runtime must use an isolated, Plasma-qualified Python runtime.**

中文定義：

> **Plasma PPU 不依賴、也不取代 PYNQ 的 System Python。Plasma 必須使用獨立、經 Plasma 驗證且可版本化的 Python Runtime。**

具體規則：

1. `/usr/bin/python3` 與 PYNQ image 內建 Python 屬於 **PYNQ / OS ownership domain**。
2. Plasma Server、Plasma Gateway 與其他 PPU product processes 不應以修改 System Python 作為部署前提。
3. Plasma PPU runtime 必須使用獨立 Python 3.11+ runtime；其路徑、版本與生命週期由 Plasma deployment layer 管理。
4. 過渡期可使用平行安裝，例如：

   ```text
   /usr/bin/python3                 -> PYNQ System Python 3.10
   /opt/plasma/runtime/python/...   -> Plasma-qualified Python 3.11+
   ```

5. systemd unit 必須顯式綁定 Plasma runtime interpreter，不可依賴互動 shell 的 `PATH` 或 `/usr/bin/python3` 隱含解析。
6. 長期 packaging 方向優先採用 **bundled Python runtime**：PPU release artifact 應攜帶經 Plasma qualification 的 ARMv7 Python runtime，使 Z2 不需要在部署時執行 `apt install`、`pip install`、`git clone` 或 source build。
7. Bundled runtime 在正式成為 Current deployment capability 前，必須完成 PYNQ-Z2 ARMv7 / glibc / shared-library 實機 qualification；本 ADR 不把尚未完成的 bundling 寫成已實作能力。

## Rationale

### 1. 降低平台耦合

PYNQ image 的 System Python 是 board/software image 的一部分，不應成為 Plasma application compatibility contract。將 Plasma runtime 獨立後，PYNQ image 與 Plasma product version 可以各自演進。

### 2. 避免破壞 PYNQ baseline

直接替換 System Python 會擴大 fault domain。即使 Plasma 能啟動，也可能造成 Jupyter、PYNQ overlays、board support 或 OS-integrated tools regression。這種風險對量產燒錄設備不可接受。

### 3. 可重現部署

產品部署應從 immutable release artifact 決定 runtime，而不是由 target 當下的 package repository、pip resolver 或系統 Python 狀態決定。相同 release 應對應相同 Plasma Python runtime 與相同相容性證據。

### 4. Upgrade / rollback 可控

獨立 runtime 可以跟 release side-by-side versioning：

```text
/opt/plasma/releases/
├── 0.1.0/
│   └── runtime/python/...
├── 0.2.0/
│   └── runtime/python/...
└── current -> 0.2.0
```

升級失敗時，可以回到上一個 release，而不需要復原 OS-level Python package mutation。

### 5. 符合 PPU appliance model

PPU 應被部署成 embedded appliance runtime，而不是一般-purpose development host。Target-side Git、pip、source build 與 Internet dependency 都會降低可重現性與現場維護能力。

## Consequences

### Positive

- PYNQ System Python 可保持原 image baseline。
- Plasma 可獨立選擇與升級 Python 版本。
- Deployment reproducibility 提升。
- 可以建立 release-level runtime compatibility evidence。
- Upgrade / rollback 不需要修改 OS Python。
- 未來其他 Embedded Linux PPU 也可沿用相同 ownership model。

### Cost / complexity

- Release artifact 會變大，尤其採 bundled Python runtime 後。
- CI 必須建立與驗證 ARMv7 runtime artifact。
- 需要處理 glibc、OpenSSL、libffi、zlib、sqlite、dynamic loader 等 native dependency 相容性。
- Security update ownership 由 Plasma 承擔：bundled Python / OpenSSL 等 runtime component 必須有版本與更新策略。
- Installer / deployment adapter 需要明確管理 runtime path、filesystem ownership、systemd 與 rollback。

### Current implementation gap

目前 PPU runtime packaging 仍假設 target 已有 Python >= 3.11，readiness audit 也據此 fail closed。因此在 bundled runtime 完成前，Z2 deployment 必須：

```text
保留 PYNQ System Python 3.10
        ↓
平行 provision Plasma-qualified Python 3.11+
        ↓
以絕對路徑啟動 Plasma Server / Gateway
        ↓
完成 Z2 runtime qualification
```

不得為了讓 audit PASS 而修改需求宣稱，或把未驗證的 Python 3.10 執行結果視為正式 PPU support。

## Alternatives Considered

### Alternative A — 將 Plasma 降回 Python 3.10

**Rejected as the default architecture.**

這會讓 Plasma product runtime 被目前 PYNQ image 綁定，而且只是把 platform mismatch 轉移到 application source/dependency policy。若未來有明確產品成本或支援需求，可另開 ADR 評估 Python 3.10 compatibility profile，但不能作為臨時 deployment workaround。

### Alternative B — 升級或替換 `/usr/bin/python3`

**Rejected.**

會跨越 PYNQ / OS ownership boundary，可能破壞既有 image integration，且 rollback 複雜。

### Alternative C — Z2 現場透過 apt/pip 安裝 Plasma Python 與 dependencies

**Accepted only as a temporary engineering bootstrap, not the target product model.**

它可用於早期 qualification，但依賴 package repository、network availability 與 target state，不能作為最終 production deployment contract。

### Alternative D — Release bundled Plasma-qualified Python runtime

**Preferred target direction.**

它提供最高的 reproducibility 與 ownership clarity，但必須先完成 ARMv7/PYNQ native qualification、runtime security maintenance 與 artifact size 評估。

## Validation Gates

在宣告 PYNQ-Z2 支援 isolated / bundled Python runtime 前，至少完成以下 Gate。

### Gate 1 — Z2 platform baseline

記錄並保存：

```bash
uname -m
cat /etc/os-release
ldd --version
python3 --version
which python3
```

至少確認 architecture、OS、glibc 與 System Python baseline。

### Gate 2 — Isolated Python 3.11+ runtime

在不修改 System Python 的前提下，驗證 Plasma interpreter 的：

- startup；
- standard library；
- dynamic library resolution；
- filesystem；
- networking；
- threading / process behavior。

### Gate 3 — Packaged PPU runtime

使用 isolated interpreter 執行 packaged `ppu.pyz`，確認：

- Plasma Server startup；
- Plasma Gateway startup；
- configuration load；
- production Device Catalog load。

### Gate 4 — Managed network path

驗證：

```text
Mac Control Station
    ↓ Ethernet
Z2 Plasma Gateway :18080
    ↓
Plasma Server :9900
    ↓
PS diagnostic / Managed PS Loopback
```

至少 `/api/health/ready` 與 Managed PS Loopback 必須 PASS。

### Gate 5 — PYNQ regression

部署 Plasma runtime 後確認原 PYNQ environment 仍正常，包括：

- PYNQ System Python 3.10；
- Jupyter；
- PYNQ package import；
- Overlay / MMIO 基本 regression；
- board support 相關必要功能。

隔離成功的定義不是只有「Plasma 能跑」，而是「Plasma 能跑且 PYNQ baseline 未被破壞」。

## Deployment Implications

Z2 deployment adapter 應逐步收斂到：

```text
validated PPU release artifact
        ↓
SSH / local commissioning transport
        ↓
platform audit
        ↓
runtime compatibility check
        ↓
side-by-side release installation
        ↓
explicit Plasma Python binding
        ↓
systemd reconciliation
        ↓
health check
        ↓
Managed PS Loopback
        ↓
activate current release
        ↓
rollback on failure
```

最終 operator experience 應為 one-command / one-action deployment，而不是要求使用者手動管理 Python、pip、Git 或 systemd internals。

## Follow-up Work

1. 實測目前 PYNQ-Z2 image 的 OS / glibc / Python baseline。
2. 建立 ARMv7 Python 3.11+ isolated runtime PoC。
3. 執行 Gate 1–5 並保存 evidence。
4. 修改 PPU release packaging，使 interpreter ownership 從 target prerequisite 逐步移到 Plasma release。
5. 實作 PPU Z2 installer / deployment adapter。
6. 更新 `product-deploy audit ppu`，讓 audit 檢查 **effective Plasma runtime**，而不是永久假設 `/usr/bin/python3 >= 3.11`。
7. 建立 bundled runtime 的 CVE / component update ownership policy。

## Decision Summary

```text
PYNQ owns System Python.
Plasma owns Plasma Runtime.

PYNQ Python 3.10
        ≠
Plasma Python 3.11+

parallel
isolated
versioned
independently upgradeable
```

這是 PYNQ-Z2 deployment 的正式 runtime ownership 原則，也應作為未來其他 Embedded Linux PPU 平台的預設架構方向。
