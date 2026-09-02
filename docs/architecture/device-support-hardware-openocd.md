# Plasma Device Support / Hardware Execution / OpenOCD 架構決策

> 更新日期：2026-09-02  
> 狀態：Plan  
> 核心原則：IC support 的擴充速度優先；硬體 hot path 才下沉到 C / PL；OpenOCD 保留 target / flash algorithm 價值，不直接承擔 Plasma 的底層硬體 driver 責任。

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

## 6. OpenOCD 定位

OpenOCD 應被視為 Programmer Backend。其主要價值：

- target support
- CPU architecture support
- reset sequence
- flash algorithms
- target scripts
- transport / debug protocol knowledge

OpenOCD 不應被定位成 Plasma 的底層 hardware driver。

## 7. OpenOCD Production 架構

```text
Device Support / Programming Logic
Python
        ↓
Programmer Backend
   ├── OpenOCD
   ├── Plasma Native Backend
   └── Vendor Backend
        ↓
Plasma Hardware API
libplasma_hw.so
        ↓
UIO / MMIO / DMA / IRQ
        ↓
FPGA PL
```

OpenOCD 未來可透過 custom Plasma adapter driver 呼叫 Plasma HW API。

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

Adapter 應提供高階硬體語意，例如：

```text
plasma_swd_transfer(...)
plasma_jtag_scan(...)
plasma_reset(...)
plasma_set_clock(...)
```

不要把主要介面做成 raw `read_reg/write_reg`。

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
plasma_site_reset(site);
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
- Programming Logic
- Image handling
- Server / Gateway
- Job / Batch / Site
- Backend selection
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

Programming Logic
→ Python

Programmer Backend
→ OpenOCD / Custom / Vendor

Hardware API
→ C when productized

UIO
→ MMIO + IRQ boundary

DMA
→ Programming Image data plane

PL
→ deterministic protocol execution
```

> OpenOCD 保留 target 與 flash algorithm 的價值；Plasma HW API + PL 掌握真正的硬體執行能力。

> Plasma 的核心競爭力應是新 IC support 的導入速度，而不是讓 OpenOCD 或 Python 逐 bit 控制硬體。
