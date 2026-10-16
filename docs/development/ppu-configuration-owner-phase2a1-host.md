# Phase 2A.1 — PPU Configuration Owner（Host-only Control Model）

> **Status: Host-only implementation candidate. M1 Architecture Freeze = NO-GO.**
>
> 本文件與 `software/python/plasma_interfaces/configuration_owner.py` 僅適用
> 合成環境；程式沒有可用的 FPGA Manager、UIO Character Device、Driver
> Unbind、AXI Bridge、DUT 或 Bitstream 載入操作。Host 測試通過不等於
> PYNQ-Z2／MYIR Zynq-7010 安全切換驗證。
>
> 基準：[Phase 2A UIOBackend](uio-runtime-backend-host-v1.md)、
> [Zynq 隔離與所有權審查](../architecture/zynq-fpga-manager-isolation-ownership-review.md)、
> [ADR-0003 Proposed](../adr/0003-runtime-fpga-driver-reconfiguration-boundary.md)。
> 本工作**不修改 PR #972**。

## 交付範圍

Phase 2A.1 建立一個 PPU 級別的**協作式 Configuration Owner**，負責合成
UIOBackend 的 Admission Gate、Site Lease、批次 IC 一致性、
Quiesce、Ownership Audit、安全狀態模擬、映射釋放及 Mapping Generation。
它是未來正式 Configuration Owner 的 Host 模型，**不是**硬體安全邊界。

| 元件 | Host-only 契約 |
|---|---|
| `ConfigurationOwner` | 單一 PPU 協作式控制者；專屬 `flock` 防止已遵循協議的另一個 Owner 同時啟動。與 `LinuxMMIO/UIOBackend` 的 MMIO Lock **分離**。 |
| `ManagedSite` | Site 1–8 的受管 `read32/write32` 介面；只有 `READY/QUIESCE` 的在途 Job 可執行，封鎖新的 Admission。 |
| Batch IC | 同一批執行中的 Sites 必須使用**相同完整 IC/profile 身分**；所有 Site 結束後，下一批才可切換。 |
| `HostAudit` | 比對固定 synthetic `boot/resource/source` 身分，及 `/proc`、Retained VMA、Kernel Consumer、DMA 確認旗標；任何 False／None／型別錯誤進入 `FAULT`。旗標是**測試輸入**，不能當現場調查或物理證據。 |
| `HostSafety` | 只對合成安全／AXI 隔離條件做狀態轉移測試；此類資料**不能**授權真實 FPGA Reload。 |
| `HostVerification` | 合成 candidate/boot/ABI/Resource/Kernel/SSH/Gateway/Recovery 條件驗證；有不符即 `FAULT`。 |
| `generation + epoch` | Generation 由 Configuration Owner 控制，舊 Backend Retire 後才遞增；UUID epoch 區分 Owner 實例。新 Backend 必須以**新 generation** 建立。未提供跨重啟持久化／Kernel 發放 token。 |

### Model-only 狀態轉換

```text
IDLE -- attach regular-file UIOBackend --> READY
READY -- begin_quiesce --> QUIESCE  (seals new Job admission first)
QUIESCE -- all managed Sites released --> OWNERSHIP_AUDIT
OWNERSHIP_AUDIT -- verified SYNTHETIC fixture --> SAFE_IO
SAFE_IO -- verified SYNTHETIC fixture --> RELEASE
RELEASE -- Host-only UIOBackend.quiesce_for_reload() --> MODEL_LOAD
MODEL_LOAD -- record string label in RAM; NO BITSTREAM --> VERIFY
VERIFY -- SYNTHETIC candidate/health checks --> NEW_MAPPING_GENERATION
NEW_MAPPING_GENERATION -- retire old mapping + increment generation --> IDLE
IDLE -- attach new-generation regular-file backend --> READY

Any unknown/failed synthetic evidence, mapping/resource drift, unsafe
access, or release error -> FAULT
Unknown AXI completion / independent hardware uncertainty ->
EXTERNAL_RECOVERY_REQUIRED (terminal in this owner model)
```

**特別注意：** 本模型中的 `READY` 代表**合成 Host Fixture** 可接受工作，
`MODEL_LOAD` 只記錄候選字串，沒有任何載入行為。
實機認證不能直接呼叫此流程宣稱 `FPGA_LOAD`／`READY` 成功。

`begin_quiesce()` 在確認所有 Site 結束以前，就先封鎖新工作。
目前已被承認的在途 Site 在 `QUIESCE` 可以正常結束；若未結束，
`confirm_sites_idle()` 不會晉升。新的 Site 無法搶在查核之後加入。
合成 MMIO 映射由 Owner 受管的 Lease 執行，不允許在前一個
Generation 直接重新啟用。

### 跨程序及其他邊界

專屬 Configuration Lock 與 MMIO Lock 都是**協作式檔案鎖**。
這個實作沒有跨程序 Job Registry，也沒有硬體排他授權：
擁有權限的第三方可以略過 Python Owner 直接開啟映射。
`UIOBackend` 本身仍禁止 Character Device，只映射**一般檔案**；
本階段的單進程 Admission 門禁不能隔離 Kernel DMA 或 PL Master。

Owner `epoch` 是用於辨識控制者實例的合成標記，不是受 Kernel
保護的能力憑證，也不是硬體 image receipt。
`HostAudit/HostSafety/HostVerification` 中的欄位皆為合成測試注入；
**不能**把現場 `/proc` 快照填入後就將實機 FPGA Reload 視為安全。

### Fault 與外部復原

任何不可信 MMIO 後果令 Owner 進入 `FAULT`，不再 Admission，
也無自動 Restore、Retry、Rebind 或 FPGA Load。
若 AXI 有可能 Hung／未完成，進入
`EXTERNAL_RECOVERY_REQUIRED`，拒絕所有 Job。
`close()` 僅退休 Host 合成 Backend 與受管租約。

既有 PR #972 的 B1 與 FPGA 隔離資格仍 **BLOCKED**。
未來實機進入條件仍至少包括：Kernel Source/DT Provenance、
已驗證的 AXI Drain／Reset／隔離、獨立外部復原、Kernel/DMA
Consumer 排除能力、真實 FPGA ABI Identity，以及
不可被競態繞過的全 PPU Ownership 交接協議。

## 驗證

```bash
python3 -m pytest -q \
  software/python/tests/test_configuration_owner_host.py \
  software/python/tests/test_uio_backend_host.py \
  software/python/tests/test_linux_mmio.py
```

新 CI 為 **PLASMA PPU Configuration Owner Phase 2A.1 Host-only**。
驗證包含：雙 Site／八 Site 合成並行、同一 Exact IC 批次、
Admission vs Quiesce Race、可釋放的 Site Lease、映射淘汰、
Owner Generation 遞增、跨程序協作 Lock、Fork Token 無效、
Source/DT 資源差異、Retained VMA／Kernel/DMA Unknown、
安全隔離標記缺失、Gateway／SSH／Image 身分異常、
B1 未授權旁路以及 Fail-Closed／External Recovery Required。

**Gate 邊界：** 此次僅涵蓋 Host-only 程式、測試、文件與 CI。
沒有 Z2 執行、FPGA 映像更換、服務部署、HIL-B/C、變更 PR #972
或授權在正式 Gateway 啟用 Configuration Owner。
完成 PR 後仍須分別經 Gate 2 明確批准才可合併。
