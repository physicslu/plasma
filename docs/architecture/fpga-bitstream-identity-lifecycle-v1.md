# FPGA Bitstream Identity / Compatibility / Lifecycle v1

> **Status:** Plan（已核准的設計標準；尚未實作或經實體 Z2 驗證）  
> **Date:** 2026-10-14  
> **Decision authority:** [ADR-0003](../adr/0003-fpga-bitstream-identity-preflight.md)  
> **Applies to:** 首個正式 PYNQ-Z2 EMIO GPIO Bitstream 及其後的 PLASMA Production/PoC PL 配置。既有 `pl/projects/btled` 是歷史 bring-up 範例，不代表符合本標準。

## 1. 第一原則與責任邊界

Bitstream 是一個可替換的**硬體能力實作**，不是 IC 料號本身、也不是 PS Runtime 軟體版本。

- **Programming Profile** 宣告目標 IC 的介面、電壓、Reset、安全條件、所需 FPGA 能力與 Hardware ABI。
- **PPU FPGA Configuration Manager（規劃中）** 判斷目前已載入的 PL 是否相容，必要時進入安全的重配置程序。
- **Plasma Server / Job Admission** 擁有 Job 排程與安全互斥；Manager/Console 只提交需求、呈現狀態，不直接寫 PL 配置埠。
- **PS Platform Deployment** 維護 Python、PPU、OpenOCD 等 Linux Runtime；已驗證的 Bitstream 可作為 artifact 配送，但「安裝/快取」與「實際載入 FPGA」為不同交易。
- 現有 Z2 Bootstrap 宣告 `fpga_update=false`。本標準**不更改**這項部署邊界，不新增 Console Bitstream 更新按鈕或現有 FPGA loading API。

長期應盡量使用可支援多 IC 家族的通用 Bitstream；若能力與 ABI 已相容，切換 ICPN 不需載入 Bitstream。

## 2. Bitstream 版本與可追溯身分

每一份**正式** Bitstream artifact 必須具備下列欄位：

| 欄位 | 格式 / 範例 | 判斷依據 |
|---|---|---|
| `bitstream_version` | 獨立 SemVer，例如 `0.1.0` | 硬體功能/修訂版本；**不能**單憑版本高低認定相容 |
| `hardware_abi_version` | 非負整數，例如 `1` | PS↔PL Register/Protocol 契約；不相容須拒絕 |
| `build_id` | 完整 Git SHA 前 128 bit 的 32 hex chars | PL Identity 可讀的精簡建置識別；不是安全雜湊保證 |
| `source_git_sha` | 完整 40 hex chars | RTL、XDC、Tcl 等來源追溯 |
| `bitstream_sha256` | 64 個小寫 hex chars | Bitstream **檔案**完整性；不是出版者身分或簽章 |
| `target_board` | 例如 `pynq-z2` | 確認板型 |
| `target_board_revision` | 明確 Revision 或受控相容清單 | 避免 I/O pinout、供電或板修訂不符 |
| `fpga_part` | 例如 `xc7z020clg400-1` | 不得跨不相容 FPGA 型號部署 |
| `capabilities` | 穩定 ID 列表 | 需以實際邏輯提供，而非推定 |
| `toolchain` | Vivado 版本及建置配置識別 | 建置重現與差異調查 |
| `identity_schema_version` | `1` | Manifest / Identity 讀取解碼器版本 |

**SemVer 原則：** Bitstream Version 與 PLASMA Software Version 完全獨立。Hardware ABI 改變時必須同步調整 ABI Version；單純更新 Bitstream SemVer 不可暗示 ABI 改變，也不可用較新 SemVer 跳過 ABI / 能力檢查。若版本含 prerelease/build metadata，完整字串保存在 Manifest；硬體暫存器只回報 `major.minor.patch` 數值。

## 3. PL Identity Register Block（候選 ABI v1）

所有正式 Bitstream 必須提供 PS 可讀的 PL Identity。初期以 AXI-Lite 唯讀暫存器區塊實作，與 EMIO GPIO / SWD 週邊分開；其**絕對 AXI Base Address** 由具體 Vivado Address Map 定義，本文件不猜測地址。下表是 **ABI v1 設計基線**，需由首個 RTL + 驗證測試落實才成為可執行契約。

| Offset | 32-bit register | 內容 |
|---|---|---|
| `0x00` | `MAGIC` | `0x504C534D` = ASCII `PLSM`（32-bit 數值） |
| `0x04` | `BITSTREAM_VERSION` | `[23:16] major; [15:8] minor; [7:0] patch; [31:24] = 0` |
| `0x08` | `HARDWARE_ABI_VERSION` | `uint32`，v1 預設值 1 |
| `0x0C` | `CAPABILITY_FLAGS` | 32-bit bitmask，依 versioned capability registry 解碼 |
| `0x10` | `BUILD_ID_0` | Git SHA 十六進位字串第 0–7 位轉成 `uint32` |
| `0x14` | `BUILD_ID_1` | Git SHA 第 8–15 位轉成 `uint32` |
| `0x18` | `BUILD_ID_2` | Git SHA 第 16–23 位轉成 `uint32` |
| `0x1C` | `BUILD_ID_3` | Git SHA 第 24–31 位轉成 `uint32` |

- 以上均為 32-bit AXI-Lite 可讀數值。PS 端讀出值須與 Manifest 的對應欄位完全相同；記憶體傳輸位元組序以 AXI-Lite/CPU 實際實作與測試確認，不得以字串比較取代數值比較。
- 暫存器在載入完成且 PL 已穩定後才允許被視為有效；重配置中不可將舊的 Cache 視為目前 Hardware Identity。
- `BUILD_ID` 是 SHA-1/Git commit 的**截短來源識別**，不能證明目前 FPGA 組態的全部位元等於 Manifest；完整 Bitstream SHA-256 在載入**前**由 PPU 驗證，載入後再回讀 PL Identity 並做能力/ABI/功能驗收。
- 真正需要端到端證明 FPGA 已載入的每一個 configuration bit 時，僅有上述 Identity 不足，必須另外設計可信回讀/量測機制，不得誇大其保證。
- Identity 規格若調整布局、語意或編碼，需變更 ABI / schema，不能偷偷重用既有寄存器。

### 3.1 Capability Registry v1（規劃初始分配）

| Flag bit | ID | 語意 |
|---|---|---|
| 0 | `swd_gpio` | 提供可被 PS 控制的 SWCLK、雙向 SWDIO、可選 NRST GPIO；**不代表 SWD Master** |
| 1 | `swd_master` | FPGA 中實作的 SWD protocol engine；必須另外驗證功能 |
| 2 | `spi_master` | FPGA SPI protocol engine |
| 3 | `i2c_master` | FPGA I²C protocol engine |
| 4–31 | reserved | 保留，未定義位元不能推定任何能力 |

每項能力還需檢查 **Site routing / 電壓 / 輸出保護 / 實機資格**；PPU-wide Flag 不是所有 Site 均有該能力的證明。新增或修改 Flag 語意需要版本化審核，不能重用既有 bit。未知位元不得被用作相容性判斷。

## 4. Manifest v1（示意 Schema）

下列為設計範例，**不是現存 Release Artifact**；校驗器/簽章/Schema 尚待實作。

```json
{
  "identity_schema_version": 1,
  "bitstream_version": "0.1.0",
  "hardware_abi_version": 1,
  "build_id": "0123456789abcdef0123456789abcdef",
  "source_git_sha": "0123456789abcdef0123456789abcdef01234567",
  "bitstream_file": "plasma-z2-swd-gpio-0.1.0.bit",
  "bitstream_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "target_board": "pynq-z2",
  "target_board_revision": "requires-explicit-board-revision-validation",
  "fpga_part": "xc7z020clg400-1",
  "capabilities": ["swd_gpio"],
  "capability_flags": 1,
  "toolchain": {"name": "Vivado", "version": "to-be-captured"},
  "hardware_runtime_ready": false,
  "physical_programming_qualified": false
}
```

範例中的 commit、digest、board revision 與工具版號皆非真實硬體證據，**不得複製作為有效部署資料**。

Manifest 與 Bitstream 必須以同一個版本化產製程序組成不可變、可校驗的 artifact；SHA-256 驗證需對實際 `.bit` bytes 進行。Manifest 至少要做 Schema、必要欄位、合法值、板型、FPGA Part、版本/能力映射及完整性驗證。SHA-256 僅能證明完整性，不能證明 artifact 發行者真實性；生產環境的信任與簽章仍須獨立設計。

## 5. 選擇 ICPN 後的 Programming Preparation

```text
Control Station 選擇 exact ICPN
  -> Device Support / Programming Profile
  -> 決定 required FPGA ABI + Capabilities + Site routing + electrical policy
  -> PPU 查詢已載入 PL 的 Identity（不可只看上次載入紀錄）
     ├─ 版本/ABI/能力/板型/實機資格全符合 → 沿用現有 Bitstream
     └─ 不符合
         -> 是否有受信任、已校驗、支援目前板型的候選 Bitstream？
         -> 是否全部 Site idle，且可進入安全硬體狀態？
         -> 完整 Bitstream 載入（PPU-wide critical section）
         -> 重新讀取 PL Identity + 執行必要 preflight
  -> 通過所有安全/相容 gate
  -> 才允許 OpenOCD / Programmer Backend 連接、擦除、寫入、驗證
```

精確決策規則：

1. **不可按料號無條件 reload。** 優先沿用相容且已通過當前驗收的 PL；不同 ICPN 若需要相同能力，可以共用同一 Bitstream。
2. **Version 是身分，不是單調相容關係。** 必須看實際 ABI、Capability、板型、Site 路由、Hardware Safety 與 Profile 已核准的版本條件。
3. **無可接受證據即阻擋。** 未找到 Manifest、SHA-256 失配、讀取 Magic/Build ID 不符、ABI 不符、未知硬體狀態、Site 電氣條件不足或未通過硬體 HIL，拒絕 Programming；不得 fallback 到 Mock。
4. **載入後再驗證。** 切換成功不能僅憑 Linux/PYNQ loader 回傳成功；需要重新確認 PL Identity，並在連接 IC 前驗證 SWDIO 三態、方向控制和實際 Site I/O 等適用的安全 gate。
5. **Bitstream 是 PPU-wide 配置。** 單 Site Profile 不得獨立更改整顆 PL 的組態。未來若導入 Partial Reconfiguration，必須先另立隔離/安全/能力相容性設計。

## 6. 重配置的並行安全與失敗策略

- 在開始下載 Bitstream 前，由 **PPU 具權威性的 Job/資源管理者** 原子性取得全域 FPGA Configuration Lock，並確認所有 Site 無活動中的燒錄、Reset、Power transition、排隊但已獲 admission 的硬體操作；新 Job 在切換期間不得進入執行。
- 進入 board-defined 安全狀態：禁止對 DUT 意外供電/注入電流、關閉或保護介面輸出、必要 Reset 隔離、SWDIO 高阻抗；必須由硬體電路和測試確保安全，**不可假設僅靠 PL bitstream 能保證重配置時的輸出狀態**。
- 載入失敗、Timeout、Identity 不符、回復不完整：PPU 轉入不可執行狀態並通報具體錯誤；不能盲目重新執行 Erase/Program、不能把未知狀態當 idle/ready。
- 候選 Bitstream 必須先驗證完整性與適用性；同一版本不可被悄悄改寫檔案內容。安全 rollback 要求候選/已知良好版本及外部 I/O 條件都已被證明，否則維持 fail closed。
- Site 1 正在燒錄時，Site 2 即使要求另一份 Bitstream，也只能等待或被拒絕，**不能重配置正在運行的 PL**。
- 完整重配置不能被單 Site `cancel` 當成一般可中斷 I/O 操作；需保留安全且可追溯的配置交易與故障狀態。

## 7. Z2 HIL-M1 範圍與可驗收證據

首個正式 Z2 PoC 為 **EMIO GPIO SWD bit-bang bring-up**，不是 FPGA 硬體 SWD Master：

1. 建立可重現 Vivado Project/Tcl、PL Identity AXI-Lite Block、EMIO GPIO 到 PMODB SWCLK/SWDIO/NRST（SWDIO 必須支援 Input / Output / High-Z turnaround）。
2. 依 PYNQ-Z2 板卡原理圖及原廠 XDC 校驗 PMODB pinout、電壓域與邊界條件；未完成校驗前不得接上目標 IC。
3. 產生 Bitstream + Manifest；檢查 Vivado synth/impl/timing、`.bit` SHA-256、32-bit Identity register 值及 Base Address。
4. 使用受控 Z2 開發路徑載入，讀取真實 PL Identity，確認 Linux GPIO 可用、輸入/輸出/Hi-Z、安全電壓與 Reset。
5. OpenOCD ARMv7 支援所需 GPIO adapter，先獨立驗證 Binary/Adapter 列表，再執行 Blue Pill SWD identify、Erase、Program、Verify 的**實機**階段；PS-only/Mock PASS 不得替代實機驗收。
6. 保留實際 board identity、source commit、Bitstream SHA-256、Vivado 版本、OpenOCD 版本、DUT 型號、實測結果與錯誤紀錄。

**目前狀態：** 以上為標準與驗收要求，尚未宣稱完成 Identity RTL、Vivado bitstream、Z2 PL loading、SWD HIL 或實際 IC Programming。

## 8. 變更與版本治理

- 新正式 Bitstream 必須遵守本標準；既有示範範例可以繼續存在但不得冒充 Production Programming Capability。
- 調整 PL Interface 的 register layout、bitfield、命令語意時必須審核 Hardware ABI migration，更新 Manifest、PS reader、硬體驗證與版本文件。
- 不能以某份 Bitstream 的 `swd_master` Flag 自動宣稱 OpenOCD Adapter 已相容；OpenOCD bridge/transport 與 target programming qualification 是另外的 Gate。
- PS Runtime Deployment 與 FPGA Runtime Selection 的權限、日誌、審計及回復責任分離，所有變更須遵守 `AGENTS.md` 的 Gate 1 / Gate 2。
