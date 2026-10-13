# Plasma Device Support / Hardware Execution / OpenOCD 架構決策

> 更新日期：2026-10-13
> 狀態：Plan
> 核心原則：IC support 的擴充速度優先；硬體 hot path 才下沉到 C / PL；OpenOCD 保留 target / flash algorithm 價值並作為 Programming Engine；Python 是 Orchestrator / System Supervisor；Plasma HW API + PL 掌握 board-management 與 recovery authority。

## 1. 三層責任分離

```text
Device Support / Programming Logic
→ Python

Programmer Backend
→ OpenOCD / Custom Backend / Vendor Backend

Hardware Execution
→ Plasma HW API → UIO/MMIO/DMA/IRQ → PL
```

## 2. PoC 階段

```text
Programming Image
      ↓
Plasma Server / Python
      ↓
Device Support / Programming Plan
      ↓
Programmer Backend
      ↓
PYNQ / Overlay / MMIO
      ↓
PL
```

PoC 優先快速驗證 `PS → PL → Site → Real IC`。此階段使用 PYNQ + Python，不急著導入 UIO、C ABI 或 kernel driver。

## 3. Device Support 留在 Python

Device Support 處理 Vendor、Series、Part、JEDEC ID、Flash geometry、Page/Sector layout、Timing、Voltage、Protection、Reset、Programming Algorithm、OpenOCD metadata、Vendor XML/JSON/YAML、Image formats 與 Programming Plan。

本質是資料模型、parser、規則與 orchestration，適合 Python。長期目標是讓新增 IC 優先變成新增 Device Profile / data，而不是修改 executable code。

## 4. Declarative Device Profile

```yaml
vendor: Winbond
part: W25Q128JV
protocol: spi
identification:
  jedec_id: EF4018
geometry:
  page_size: 256
  sector_size: 4096
erase:
  command: 0x20
program:
  command: 0x02
read:
  command: 0x03
```

理想流程：

```text
Datasheet
→ AI-assisted Parser
→ Device Profile Draft
→ Schema Validation
→ Programming Plan
→ Programmer Backend
```

## 5. Programming Plan

```text
Device Profile
→ Programming Plan Compiler
→ Programming Plan
→ Programmer Backend
```

Programming Plan 可包含 `power_on`、`reset`、`identify`、`erase`、`program`、`verify`、`power_off`。上層描述「要做什麼」，不直接知道 register 怎麼寫。

Programming Plan 是 semantic plan，不代表所有 operation 都交給同一個 backend。Production dispatch 原則：

- SWD/JTAG target/flash operation → OpenOCD Programming Plane。
- POWER、BOOT/strap、Site mux、socket enable、voltage select、presence/status 與 recovery reset → Plasma Hardware Control Plane。
- normal target reset 可由 OpenOCD 執行；physical recovery reset 必須保留不依賴 OpenOCD process 的獨立控制路徑。

## 5.1 Programming Execution Strategy：Direct Register 與 Target RAM Loader

Programming semantics 與 execution strategy 必須分離。

Manufacturer documentation 定義的是 **device programming semantics**：哪些 register、bit、key、address、alignment、erase/program sequence、status/error condition 與 terminal observation 才能構成正確燒錄流程。這一層是 device truth，不應由 OpenOCD implementation、特定 adapter、RAM loader 或效能最佳化反向決定。

對 STM32F103C8T6，目前 manufacturer-derived reference programmer 的核心模型是 direct register execution：

```text
Manufacturer Specification
        ↓
Canonical Programming Knowledge
        ↓
Programming Profile
        ↓
Programming Execution IR
        ↓
Generated Direct Programmer
        ↓
RegisterMemoryIO
        ↓
SWD/JTAG memory access
        ↓
FLASH_KEYR / FLASH_CR / FLASH_SR / FLASH_AR / Flash memory
```

例如 16-bit Flash programming 的核心語意仍是：

```text
unlock Flash
→ wait BSY clear
→ clear relevant status
→ set PG
→ write halfword to target Flash address
→ wait BSY clear
→ inspect PGERR / WRPRTERR / EOP
→ leave PG mode
→ read-back verify
```

這個 sequence 是 device programming semantics。它不要求一定由 host 每個 halfword 逐筆透過 SWD 執行，也不要求一定先載入 target RAM algorithm。

因此 Production architecture 必須允許同一份 validated Execution IR 編譯成不同 execution strategy：

```text
                    Manufacturer-derived
                     Programming Semantics
                             |
                             v
                       Execution IR
                     /              \
                    /                \
         Direct Register Engine   Target RAM Loader Engine
                  |                       |
          SWD/JTAG memory I/O      generated target code
                  |                       |
                  |                 target SRAM + CPU
                  |                       |
                  +-----------+-----------+
                              |
                              v
                        Target Flash
```

### 5.1.1 Direct Register Engine

Direct execution 由 programmer backend 透過 debug transport 直接執行 register / memory operation：

```text
PPU / Host
   ↓
SWD/JTAG
   ↓
target register / memory access
   ↓
Flash controller
```

優點：

- execution path 最直接；
- 最容易逐步對照 manufacturer documentation；
- 適合 bring-up、semantic validation、fault localization 與第一版 HIL；
- 不依賴 target SRAM working area；
- 可作為 RAM Loader implementation 的 independent behavioral reference。

缺點是大量 programming data 若逐 halfword 經 debug transport round-trip，throughput 可能很差。

因此第一個 real-device qualification 應優先以 Direct Engine 驗證：

```text
identify
→ unlock
→ erase
→ direct program
→ read-back verify
→ lock / reset
```

在這條最小鏈未通過 HIL 前，不應以 RAM Loader 的速度最佳化掩蓋基本 Flash semantics 或 transport 問題。

### 5.1.2 Target RAM Loader Engine

Target RAM Loader 是 **execution optimization**，不是 manufacturer programming truth，也不是 bootloader。

其典型流程：

```text
debugger controls halted target
        ↓
allocate target SRAM working area
        ↓
load small Flash programming algorithm into SRAM
        ↓
load / stream programming data into SRAM buffer or FIFO
        ↓
set target CPU registers / PC
        ↓
run target CPU from SRAM
        ↓
target CPU performs local Flash writes and status polling
        ↓
BKPT / terminal status
        ↓
debugger regains control
```

它與 device ROM/system bootloader 不同：

- 不要求 target reset 後從此 code 開機；
- 不把 loader 永久寫入 Flash；
- loader 只在 debug session 中暫存在 SRAM；
- debugger 仍掌握 CPU halt/run/register state；
- programming 完成後 working area 可被回收。

它的效能優勢來自把高頻迴圈移到 target CPU 本地執行，而不是讓 host 為每個 halfword 往返 SWD/JTAG。

### 5.1.3 OpenOCD STM32F1 的實際策略

Pinned OpenOCD STM32F1 implementation 採混合策略：

| Operation | OpenOCD STM32F1 strategy |
|---|---|
| Flash unlock | direct target register write |
| Page erase | direct target register write + status polling |
| Mass erase | direct target register write + status polling |
| Flash program | preferential target RAM Flash loader |
| Program fallback | direct halfword memory access |
| Device ID / Flash size / status | direct target memory/register access |

也就是 OpenOCD 的 programming control semantics 與 manufacturer sequence 高度重疊，但其大量 write path 會優先使用 SRAM working area 與 target algorithm，以降低 debug-transport round-trip overhead。

若 target SRAM working area 不足，OpenOCD 可 fallback 到 direct halfword memory access。這再次證明 RAM loader 是 backend execution optimization，而不是 STM32F1 Flash programming 的必要語意。

### 5.1.4 PLASMA Compiler / Backend 原則

PLASMA 長期不應把 RAM Loader implementation 細節寫進 manufacturer canonical model。正確分層是：

```text
Manufacturer Evidence
        ↓
Canonical Programming Semantics
        ↓
Programming Profile
        ↓
Execution IR
        ↓
Execution Compiler / Backend Policy
   ┌───────────────┴────────────────┐
   ↓                                ↓
Direct Register Backend      Target RAM Loader Backend
   ↓                                ↓
OpenOCD / Plasma Native      generated target algorithm
   ↓                                ↓
debug transport              target SRAM / CPU
```

核心 invariants：

1. **Manufacturer semantics 是 truth。** OpenOCD、Direct SWD、RAM Loader 都只能是 execution implementation。
2. **RAM Loader 不得反向污染 canonical device model。** Working-area size、FIFO layout、CPU register convention、OpenOCD timeout 等都屬 backend policy。
3. **Direct Engine 保留為 reference path。** 即使 production 最終主要使用 RAM Loader，也應保留可驗證的 direct path 作 bring-up、diagnostics 與 differential reference。
4. **RAM Loader 應由同一份 validated IR 派生。** 不應維護一份手寫 direct algorithm 與另一份彼此獨立的 loader semantics。
5. **Performance optimization 在 correctness 之後。** HIL 先證明 direct erase/program/verify；再 qualification RAM Loader throughput。
6. **Fallback 必須 fail-closed。** RAM Loader allocation/execute 失敗時，只有在 direct execution 已 qualification 且 operation state 可判定時，才允許 fallback；不得在 uncertain Flash state 中盲目重試。
7. **Bootloader 與 RAM Loader 必須分開建模。** ROM bootloader／user bootloader 是另一種 transport/protocol backend，不等同 debug-controlled SRAM target algorithm。

### 5.1.5 Differential Qualification Ladder

建議 qualification 順序：

```text
Manufacturer-derived Execution IR
        ↓
Generated Direct Programmer
        ↓
Fake-controller behavioral tests
        ↓
Independent OpenOCD semantic differential
        ↓
Real OpenOCD binary/config/backend registration
        ↓
Real Direct SWD HIL
  erase → program → verify
        ↓
Generated RAM Loader
        ↓
Real RAM Loader HIL
        ↓
Direct vs Generated RAM Loader differential
        ↓
Generated RAM Loader vs OpenOCD RAM Loader differential
```

最終應追求三條 implementation 對同一 image / target geometry 得到相同結果：

```text
Manufacturer-derived Direct Programmer
                  |
Manufacturer-derived RAM Loader
                  |
OpenOCD RAM Loader
                  |
                  v
          equivalent Flash result
```

這種三方 differential 的目的不是證明 OpenOCD 為真理，而是利用 implementation diversity 降低共同錯誤的風險。

## 6. OpenOCD 定位

OpenOCD 應被視為 **Programming Engine / Programmer Backend**，不是 Plasma 的 System Supervisor。其主要價值：

- target support
- CPU architecture support
- target-level reset / halt / run sequence
- flash erase / program / verify algorithms
- target scripts
- transport / debug protocol knowledge

OpenOCD 不應成為下列 board-management 能力的唯一 owner：

- Site POWER ON/OFF
- BOOT / strap pin
- Site / socket mux
- socket enable
- target voltage selection
- presence / voltage / current detect
- emergency / recovery reset
- process recovery、retry、job timeout、progress aggregation

Python service 應透過 OpenOCD 的 **Tcl RPC machine interface** 呼叫 programming command，而不是解析混雜 human log 的 stdout。OpenOCD 的預設 Tcl RPC port 是 `6666`；預設 `4444` 是供人操作的 Telnet interface，不應作為 production machine API。

Production requirement：

- Tcl RPC 只 bind loopback / local namespace，不直接暴露到 PPU LAN。
- port 必須由 runtime 配置與 Site worker lifecycle 管理，不把 `6666` 寫死成多 Site 唯一 port。
- Tcl RPC 是 request/response command boundary；command 尚未完成時 caller 仍會等待，因此 timeout、cancel、worker restart 必須由 Python supervisor 管理。
- 若需要 command log，可使用 OpenOCD Tcl 的回傳值或 `capture` 等既有機制；不得以 stdout text scraping 作 canonical machine contract。

### 6.1 OpenOCD Runtime Artifact Identity

OpenOCD runtime 必須區分兩種不同 identity：

```text
runtime_id
= OpenOCD version + pinned source commit
= source/build intent identity

payload_sha256
= staged file path + mode + content tree digest
= compiled/runtime payload identity

artifact_sha256
= exact distributed .tar.gz bytes
= deployment / promotion identity
```

三者不可混為一談。相同 `runtime_id` 不代表兩次獨立編譯必定產生相同 binary；compiler、system library 或 build dependency 若改變，`payload_sha256` 與 artifact SHA 合理地應該改變。Production deployment 不應在 target 或 deployment 階段重新編譯來「重現」artifact，而應 **build once，連同 detached SHA-256 一起 promotion，並由 kit/install path 驗證 exact bytes**。

Packaging 本身必須消除與 payload 無關的 nondeterminism。Canonical OpenOCD artifact 因此正規化 tar/gzip 的 timestamp、uid/gid、user/group name 等 archive metadata；對完全相同的 staged payload bytes，重複 package 必須產生相同 artifact SHA。這只保證 packaging reproducibility，不宣稱未 pin 的 toolchain/dependency 會產生相同 compiled payload。

Installer 的 fail-closed 原則不變：若相同 logical `runtime_id` 的既有安裝內容與新驗證 artifact 不一致，不得 silent overwrite。Exact artifact lineage 以 sidecar 與安裝 evidence 的 `artifact_sha256` 為準。

## 7. OpenOCD Production 架構

Production 應明確分成 Programming Plane 與 independent Hardware / Recovery Plane：

```text
Control Station / PPU Console
            |
            v
      Plasma Gateway
            |
            v
   Python Job / Site Orchestrator
        /                 \
       /                   \
Programming Plane       Hardware / Recovery Plane
       |                         |
    Tcl RPC                 Plasma HW API
       |                         |
    OpenOCD                     |
       |                         |
Plasma Adapter                  |
       \                       /
        \                     /
         +---- Plasma HW API --+
                    |
             UIO/MMIO/DMA/IRQ
                    |
                 FPGA PL
             /             \
      SWD/JTAG Engine    Board Control
                         POWER/RESET/
                         BOOT/MUX/etc.
```

OpenOCD 未來可透過 custom Plasma adapter driver 呼叫 Plasma HW API，重用既有 target / flash algorithm。Python supervisor 同時持有不經 OpenOCD 的 board-management 路徑，因此即使 OpenOCD command deadlock 或 process crash，仍能 power-cycle / reset Site 並回收 worker。

多 Site implementation 必須提供 failure containment。具體可採一個 OpenOCD process per active Site，或其他具等價隔離能力的 topology；不論 implementation 細節，單一 Site 的 OpenOCD failure 不得阻塞其他 Site 的 recovery/control path。

概念：

```text
adapter driver plasma
transport select swd
```

## 8. Plasma OpenOCD Adapter

```text
OpenOCD
  ↓
plasma adapter
  ↓
libplasma_hw.so
```

Adapter 應提供 programming transport 所需的高階硬體語意，例如：

```text
plasma_swd_transfer(...)
plasma_jtag_scan(...)
plasma_target_reset(...)
plasma_set_clock(...)
```

不要把主要介面做成 raw `read_reg/write_reg`。

Adapter 可以在正常 programming sequence 中驅動 target reset，但不得成為 physical reset pin 的唯一控制入口。Python Hardware / Recovery Plane 必須能在 OpenOCD process 不可用時直接 assert/deassert Site reset。

### 8.1 Board-management pin ownership

Production responsibility boundary：

| Capability | Canonical owner |
|---|---|
| SWD/JTAG transaction | OpenOCD → Plasma Adapter |
| Flash erase / program / verify | OpenOCD |
| Target halt / run / normal reset | OpenOCD |
| Site POWER ON/OFF | Python → Plasma HW API |
| BOOT / strap mode | Python → Plasma HW API |
| Site / socket mux | Python → Plasma HW API |
| Socket enable | Python → Plasma HW API |
| Voltage selection | Python → Plasma HW API |
| Presence / current / voltage status | Python → Plasma HW API |
| Emergency / recovery reset | Python → Plasma HW API |
| Timeout / retry / worker restart | Python supervisor |

Python application 不應直接依賴 GPIO number 或 MMIO register address，例如不得把 `gpio_set(27, 1)` 變成上層產品 API。上層應使用 stable semantic API：

```python
site.power.off()
site.reset.assert_()
site.boot_mode.set("swd")
site.mux.select(socket_id)
```

底層再由 Plasma HW API 對應 UIO/MMIO register 與 PL implementation。

### 8.2 Failure containment / recovery authority

Recovery path 必須獨立於 OpenOCD：

```text
OpenOCD command timeout / crash
          |
          v
Python Site Supervisor
   |              |
   |              +--> kill / restart OpenOCD worker
   |
   +--> Plasma HW API
             |
             +--> RESET assert
             +--> POWER off
             +--> POWER on
             +--> RESET release
```

核心 invariant：

> OpenOCD failure 不得剝奪 Python 對 Site POWER / RESET 的控制能力。

因此不把 `plasma power off`、`plasma socket enable`、`plasma boot0 ...` 等 board-management command 設計成只能經過 OpenOCD Tcl command 才能執行。即使未來為工程診斷提供相似 OpenOCD command，也只能是 secondary convenience path，不是 recovery authority。

### 8.3 Programming progress 與 chunk transaction

不要為了 UI progress 優先修改 OpenOCD C core，也不要解析 stdout 推導 canonical progress。

Tcl RPC command 是 blocking request/response boundary，因此 production progress 可由 Python 把 programming workflow 拆成可驗證的 transaction：

```text
PROBING
  ↓
ERASING
  ↓
PROGRAMMING chunk 1/N
  ↓
PROGRAMMING chunk 2/N
  ↓
...
  ↓
VERIFYING
  ↓
RESETTING
  ↓
PASS / FAIL
```

這是 **transactional progress**，不是 OpenOCD realtime byte callback。

Chunking rules：

- 不得 hard-code `4 KiB` 為所有 IC 的 chunk size。
- chunk size 必須由 Device Profile / backend capability / measured performance 決定。
- 必須尊重 erase-sector、program-page、alignment、flash-driver 限制與 image hole semantics。
- erase 通常先針對 required sectors 執行一次，再進行多個 write transaction；不得在每個 chunk 無條件重複 erase 前面已完成的資料。
- binary bank programming 可在適合的 backend 使用 OpenOCD `flash write_bank <bank> <filename> <offset>`；是否使用此命令由 compiled plan/backend 決定，不是所有 target 的固定策略。
- verify 仍是獨立正式 phase；chunk write 成功不等於 final programming PASS。
- chunk granularity 必須 benchmark；transaction 太小會增加 Tcl/OpenOCD/file/backend overhead，太大則降低 progress resolution 與 fault localization。

建議 Device Profile / backend policy 可逐步包含：

```text
erase_block_size
program_page_size
recommended_chunk_size
erase_timeout
program_timeout
verify_timeout
retry_policy
```

UI-facing progress event 應由 Python state machine 產生，例如：

```json
{
  "site_id": 3,
  "state": "PROGRAMMING",
  "bytes_done": 131072,
  "bytes_total": 524288,
  "progress": 25.0
}
```

Control Station 不應直接依賴 OpenOCD log grammar。

### 8.4 OpenOCD source modification policy

對已被 OpenOCD 支援的 target / flash controller：

> 優先完整重用既有 target / flash logic，不為 Plasma 重寫燒錄演算法。

Plasma 對 OpenOCD source 的客製應縮到最小：

1. 若 FPGA SWD/JTAG engine 無法用既有 OpenOCD adapter protocol 表達，可實作薄的 `plasma` adapter driver。
2. adapter 只負責把 OpenOCD 的 SWD/JTAG/target-reset transaction 映射到 Plasma HW API。
3. POWER、BOOT、MUX、socket enable、voltage、recovery、job progress、retry 不應因此塞進 OpenOCD core。
4. 若某顆 IC 的 target / flash controller 本身尚未被 OpenOCD 支援，才可能需要新增或擴充 OpenOCD target/flash driver；這與 Plasma board-control integration 是不同問題。
5. 優先維持 upstream-compatible、可 upstream 的小 patch；避免建立大幅分叉且難以升級的 OpenOCD fork。

若未來 Plasma FPGA adapter 能以既有高效率 OpenOCD adapter interface 直接整合，可進一步降低或消除 Plasma-specific OpenOCD patch；是否採用必須以 throughput、latency、determinism 與多 Site isolation 實測決定，而不是以「零修改 OpenOCD」本身作 KPI。

## 9. 避免 OpenOCD 逐 bit bit-banging

不推薦：

```text
OpenOCD
→ 每一個 SWD clock
→ 一次 MMIO write
→ PL GPIO
```

這會造成 CPU overhead、高 latency、非 deterministic timing，且不利多 Site。

較佳架構：

```text
OpenOCD
→ High-level SWD/JTAG transaction
→ Plasma Adapter
→ Plasma HW API
→ PL Protocol Engine
```

例如 SWD transaction 將 APnDP、RnW、Address、Data 等一次交給 PL，由 PL 完成 clock、turnaround、ACK、data、parity。

## 10. PL 責任

PL 適合：

- deterministic bit timing
- SWD/JTAG waveform
- SPI/I2C engine
- reset pulse
- protocol state machine
- parallel Site execution
- CRC / data movement
- DMA engine
- timeout / hardware watchdog

原則：CPU 負責 orchestration，PL 負責 deterministic execution。

## 11. Plasma Hardware API

Production 可建立 stable Plasma HW API，例如：

```c
plasma_hw_init();
plasma_site_power_on(site);
plasma_site_power_off(site);
plasma_site_reset_assert(site);
plasma_site_reset_deassert(site);
plasma_site_set_boot_mode(site, mode);
plasma_site_set_mux(site, socket);
plasma_site_set_voltage(site, millivolts);
plasma_swd_transfer(site, request, response);
plasma_jtag_scan(site, ...);
plasma_program_begin(site, image_desc);
plasma_program_cancel(site);
plasma_site_get_status(site, &status);
```

Python 可透過 `ctypes`、`cffi` 或 extension 呼叫 `libplasma_hw.so`。

上層不應知道 `/dev/uio0`、register address、bit field、IRQ number、DMA descriptor。

## 12. UIO / MMIO / DMA

```text
Plasma Hardware Service / API
        ├── UIO
        │    ├── mmap → MMIO register access
        │    └── IRQ event handling
        └── DMA
             └── Programming Image / bulk data
```

定義：

- UIO = user-space hardware resource boundary
- MMIO = register access mechanism
- DMA = bulk data plane
- IRQ = event plane

不是 UIO 與 MMIO 二選一；而是透過 UIO 暴露硬體資源，再用 MMIO 操作 register。

## 13. Programming Image Data Path

大量 Programming Image 不應逐筆 MMIO：

```text
Programming Image
→ DDR / Buffer
→ DMA
→ PL Protocol Engine
→ Target IC
```

MMIO 只負責 START、STOP、SITE、SIZE、ADDRESS、STATUS、ERROR。

因此：

```text
Control Plane = MMIO
Data Plane    = DMA
Event Plane   = IRQ
```

## 14. PYNQ 的階段性定位

PoC 使用 PYNQ + Python，因為 Overlay、MMIO、bring-up 快，且不需先完成 UIO/C/Device Tree。

Production 若轉成：

```text
Plasma Python
→ Plasma HW API
→ UIO/MMIO/DMA
→ PL
```

則 `pynq` package 不再是必要依賴，Plasma 可自行管理 Python 3.12+ runtime。

## 15. Python / C / PL 分工

Python：

- Device Support
- Parser
- Device Profile
- Programming Plan
- Programming Logic / orchestration
- Image handling
- Server / Gateway
- Job / Batch / Site
- Backend selection
- OpenOCD Tcl RPC lifecycle
- board-management semantic control
- timeout / retry / recovery
- programming state / progress aggregation
- AI-assisted Device Support

C：

- UIO
- MMIO
- IRQ
- DMA control
- buffer management
- stable ABI
- measured hot path

PL：

- deterministic timing
- protocol engine
- parallel execution
- precise waveform
- hardware acceleration

## 16. 可替換 Programmer Backend

```text
                    ┌─ OpenOCD
Device Support ─────┼─ Plasma Native Backend
                    └─ Vendor Backend
                           ↓
                    Plasma HW API
                           ↓
                          PL
```

OpenOCD 是 replaceable backend。Device Support 與 Hardware Layer 不應綁死在 OpenOCD。

## 17. 長期 IC Support KPI

真正應優化的是：

```text
一顆新 IC 從 datasheet 到 production-ready support 需要多久？
```

長期目標：

```text
Datasheet
→ AI-assisted extraction
→ Device Profile
→ Validation
→ Programming Plan
→ Existing Backend
→ Plasma HW API
→ PL
```

把 IC support 從「寫程式」轉成「知識建模 + 驗證」。

## 18. 架構原則總結

```text
Device Knowledge
→ Python

Programming Orchestration / System Supervision
→ Python

Programming Engine
→ OpenOCD / Custom / Vendor

OpenOCD machine control
→ Tcl RPC on local-only interface

Board Management / Recovery
→ Python → Plasma HW API

Hardware API
→ C when productized

UIO
→ MMIO + IRQ boundary

DMA
→ Programming Image data plane

PL
→ deterministic protocol execution + board-level hardware execution
```

正式責任邊界：

> **OpenOCD = Programming Engine，不是 System Supervisor。**

> **Python = Orchestrator / System Supervisor，負責 Site lifecycle、POWER/BOOT/MUX、timeout、retry、recovery 與 progress。**

> **Plasma HW API + PL = deterministic execution 與 independent recovery authority。**

> **對 OpenOCD 已支援的 IC，優先重用既有 target / flash algorithm；Plasma-specific source modification 原則上只保留必要的 adapter integration。**

> Plasma 的核心競爭力應是新 IC support 的導入速度、可驗證的 failure containment 與多 Site throughput，而不是讓 OpenOCD 或 Python 逐 bit 控制硬體。
