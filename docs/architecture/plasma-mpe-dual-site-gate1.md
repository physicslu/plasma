# PLASMA MPE — independent two-Site SWD architecture (Gate 1, clean-sheet v1)

**Status:** Gate 1 architecture plus an **unverified synthesizable two-engine RTL slice**, without AXI/FIFO/IRQ integration or a physical top-level Image. Cocotb/Icarus tests are authored but not yet executed. No BIT/HWH/BIN, actual OpenOCD MPE adapter, FPGA reconfiguration, Z2 MMIO or physical DPIDR qualification exists from this document. **SOURCE_ONLY / NOT_DEPLOYED / NOT_HIL_QUALIFIED**.

**Owner intent (2026-10-27):** replace, rather than preserve, the single-Site PS-driven remote-bitbang PoC. First product-facing prototype implements **two truly independent Sites** on PYNQ-Z2 PMODA/PMODB; final architecture scales to eight without one global SWD bit engine. Neither the previous Site 1=PMODB assignment nor the retired synthetic internal DPIDR route is an ABI requirement. This is a new Image family: do not alter or remove current protected Image/Golden recovery.

## 1. Non-negotiable principles

1. **Parallel physical engines:** each Site has its own SWCLK generator/divider, SWD state machine, SWDIO IOBUF/turnaround, command/completion storage, status/fault/abort and IRQ source. Shared PS7 AXI-Lite register access does not serialize a whole physical SWD transaction.
2. **Transaction-level PS API:** PS-local OpenOCD queues SWD DP/AP register operations and SWJ/line-reset sequences. FPGA clocks the entire operation autonomously. No per-edge UNIX socket, Python toggles, or Linux scheduling in the clock path.
3. **One local MMIO owner:** single PS-side Hardware Broker maps one verified FPGA Image and dispatches commands to independent per-Site leases. No two unsynchronized users opening /dev/mem for the same region. Global mapping/image maintenance lock is short; it must not hold across transaction waits.
4. **Exact truth and fail-closed:** report raw ACK OK/WAIT/FAULT/invalid, parity, timeout, attempt count and transaction tag; never synthesize DPIDR, fake physical signals or blindly replay uncertain writes. One Site failure must not cancel the other unless a genuine common voltage/image/bus fault exists.
5. **Fixed prototype voltage:** PYNQ-Z2 Pmod I/O uses LVCMOS33, only compatible 3.3 V targets; GND mandatory. Pmod pin 6/12 is power, NOT programmable VPP/VTref sensing. Do not connect a 1.8 V or 5 V target directly. Production adjustable VDD/VIO/current limit/level translation are separate protected board-level work, not features proven by this prototype.
6. **Safe outputs:** reset/disabled Site must be SWDIO=Hi-Z, SWCLK=0 when explicitly driven, no target power or reset authority. All reserved pins remain inputs/Hi-Z. Hardware must guard idle->active transitions and bus RESET/FAULT. Electrical safe-state during FPGA configuration requires physical board review, not only RTL.
7. **Protocol independence:** Site numbering is 1-based throughout. Programmable SWD engine now; SPI/JTAG and 8-site deployment are separate capabilities, not claimed by extra placeholder registers.

## 2. Board mapping: new identity, no old Site pin compatibility

| Site | Dedicated connector | SWCLK (Pmod pin 1) | SWDIO (pin 2) | Common GND (5/11) | Other I/O |
|---|---|---|---|---|---|
| **1** | **Pmod A / JA** | **Y18** | **Y19** | required | remain Hi-Z |
| **2** | **Pmod B / JB** | **W14** | **Y14** | required | remain Hi-Z |

**Physical caveat:** Pmod A Y18/Y19 and other JA I/O are *electrically shared* with the Raspberry Pi 40-pin header on the stock PYNQ-Z2. “Dedicated to PLASMA” means this project reserves those nets and explicitly forbids an attached RPi HAT/driver; it cannot remove the PCB connection. Pin 1 physical orientation must be independently verified on the actual Pmod BB breakout before powered HIL. Blue Pill is currently connected to PMODA by owner report; physical contact and routing are not independently attested.

For the minimum SWD PoC, connect only Site SWCLK -> Blue Pill PA14, SWDIO -> PA13 and shared GND. Blue Pill 3.3 V is independently qualified; do not back-feed Pmod 3.3 V without a reviewed power topology. External nRESET, SWO, Vtarget sensing and power-switch control are **not** implemented or connected by this design.

## 3. Logical hardware architecture

```text
SWPC: Web/Controller/BFF -- Ethernet --> Z2 PS Linux / Plasma Gateway
                                               |
                                local Hardware Broker / leases
                                  |                     |
                     OpenOCD adapter Site 1   OpenOCD adapter Site 2
                                  \__________ __________/
                                             |
                            AXI GP0 + one mapped MPE aperture
                                             |
                  +-------------- MPE fabric (100 MHz) --------------+
                  |                                                  |
             per-Site 1 bank                                    per-Site 2 bank
             cmd/resp FIFO                                      cmd/resp FIFO
             hardware SWD FSM                                   hardware SWD FSM
             clock divider #1                                   clock divider #2
             SWDIO IOBUF #1                                     SWDIO IOBUF #2
                  |                                                  |
            PMODA Y18/Y19                                      PMODB W14/Y14
                  |                                                  |
           DUT/Blue Pill 1                                     DUT/Blue Pill 2
```

One AXI-Lite control plane is allowed. It arbitrates *register accesses only*; site engines continue concurrently. Each SWD engine has its own programmable half-period, independent timeout, transaction tag, completion and fault. Separate FIFO depth and scheduling must be verified under concurrent Site 1/Site 2 workload; a global in-flight/clock lock is forbidden.

## 4. ABI proposal: new, intentionally incompatible

- Image family: `plasma.mpe.swd.v1`; **proposed** 100 MHz PS7 FCLK and 32-bit AXI4-Lite.
- **Candidate** MPE aperture: `0x43C00000`, span `0x10000` (64 KiB). Validate Vivado PS7 GP0 Address Editor, actual HWH, reserved regions and deployed UIO/Kernel mapping before binding this candidate to an Image Manifest.
- Global identity/status at offsets `0x0000..0x0FFF`; Site `n` bank at `0x1000 * n`, `n=1..N`. Thus Site 1 = `0x43C01000`, Site 2 = `0x43C02000`. This geometry allows up to eight Site windows within 64 KiB.
- Per-site registers use independent tag, command doorbell and completion pop. **Never** use the previous `0x40008000` per-edge SWCLK/SWDIO/OE mapping.
- `MAGIC`, ABI version, `SITE_PRESENT_BITMAP`, `SITE_CAPABILITIES` and explicit Image Manifest are separate: a register signature is not proof of physical FPGA provenance.
- Reads/writes are aligned 32-bit words. Invalid addresses, unimplemented Sites, reserved bits and incorrect strobe must return SLVERR rather than accidentally acting on another Site.

### Register contract — implementation target (offset relative to bank)

| Offset | Register | Direction | Semantics |
|---|---|---|---|
| `0x00` | SITE_ID / CAP | R | Exact one-based identity and SWD feature |
| `0x04` | STATUS | R | IDLE / BUSY / DONE / FAULT, FIFO state |
| `0x08` | CLK_HALF_PERIOD | RW (idle only) | 100 MHz cycles per half-SWCLK, integer >=2 |
| `0x0C` | TIMEOUT_CYCLES | RW (idle only) | Bounded hardware transaction deadline |
| `0x10` | TX_DATA | W | Staging 32-bit SWD write data |
| `0x14` | CMD_PUSH | W | Atomic enqueue of opcode, arguments and sequence/tag; captures staged TX_DATA |
| `0x18` | COMPLETION_META | R | Oldest completion tag, status, raw ACK, parity/result-valid |
| `0x1C` | COMPLETION_DATA | R | Oldest matching completion data |
| `0x20` | COMPLETION_POP | W | Consume exactly the matching tag; no fault auto-clear |
| `0x24` | FIFO_LEVELS | R | Command and completion counts, reject overflow |
| `0x28` | CONTROL | W | Site-local enable/abort; never silently retry writes |
| `0x2C` | ERROR_LATCH | R | Sticky timeout/PHY/invalid ACK; explicit separately qualified recovery |
| `0x30` | IRQ_ENABLE | RW | Independent Site event enable |
| `0x34` | IRQ_STATUS | RW1C | Site event; clearing IRQ never clears fault |

The table is an engineering **interface candidate**, not a synthesized or production-frozen register implementation. Commit of CMD_PUSH must validate all staged data, command FIFO capacity, unique nonzero tag and precise SWD operation. Per-Site FIFO depth target is 16, subject to LUT/BRAM and back-pressure tests; never advertise non-implemented capacity. An ACK WAIT is returned with truthful status and bounded hardware processing; the OpenOCD adapter owns retry policy with explicit deadlines and no blind replay after uncertain writes.

### SWD engine commands

`LINE_RESET` (at least 50 SWCLK cycles with SWDIO high), `SWJ_SEQUENCE` (LSB-first bounded bit payload for switch sequence), `DP_READ`, `DP_WRITE`, `AP_READ`, `AP_WRITE`, `IDLE_CYCLES`. Include request bit/parity, turnaround/Hi-Z, raw ACK, 32-bit data + parity and correctly timed return to driving. Do not program Flash in MPE core; target Flash algorithms remain separate OpenOCD provider logic. SWD AP posted-read semantics remain managed by OpenOCD, not guessed by the fabric.

The SWCLK divider shall be independent per Site. With FCLK=100 MHz, `half_period=500` corresponds to nominal 100 kHz, and `half_period=50` to nominal 1 MHz (equation `f_swd = 100 MHz / (2 * half_period)`); **physical edges must be verified with LA2016** before any performance/DPIDR PASS.

## 5. Z2 PS / OpenOCD architecture

Two concurrent **PS-local** OpenOCD instances, each with a distinct Site 1/2 adapter context and ownership lease. Prefer a native OpenOCD SWD adapter using its queueable `read_reg/write_reg/run/switch_seq` interface to translate transfers into tagged MPE commands. This preserves OpenOCD's DP/AP, target programming and qualification model while moving clock edges entirely to PL. The existing UNIX `remote_bitbang` PoC remains archival/diagnostic and is **not** the production MPE transport. No per-bit traffic traverses Ethernet.

For Gate 1 implementation, first establish a testable injected WordPort / emulated MMIO and exact native adapter contract. Use a common private Broker/parent Image owner and independent per-Site command leases. One uncertain PS MMIO owner/image fault closes *all* Site admission; a definitive Site-local SWD parity/ACK fault closes only that Site. Do not grant unknown OS privileges or bypass Root Guard.

## 6. Verification and hardware acceptance

**Host-only Gate 1 engineering:** the initial `pl/rtl/mpe/plasma_mpe_dual_swd_core.sv` instantiates two independently controlled transaction FSMs with separate output buffers and SWDIO IOBUF, using the existing `swd_transaction_master.sv` as a previously exercised reference primitive. This is **not a new MMIO-controlled full IP**: command FIFO, register fabric and hardened electrical pad admission remain to be implemented, and the accompanying Cocotb test has **NOT_RUN** status. Design reviews against root `AGENTS.md`, `pl/AGENTS.md`, current Board XDC and existing SWD semantics references (not retired deployed engines); write new RTL and a separate Cocotb reference model. Exercise: two simultaneously active engines with intentionally different dividers; independent ACK OK/WAIT/FAULT; bad ACK and parity; SWDIO turnaround contention-free; ordered 16-deep FIFO and overflow; precise tag matching and abort races; per-Site timeout/fault confinement; AXI AW/W independent arrival, WSTRB, SLVERR and backpressure; output Hi-Z and no unrequested drive.

**SWPC Vivado build:** verify both JA and JB pin assignments, IOSTANDARD LVCMOS33, timing and DRC/methodology, HWH two-site address map, BIT/HWH/BIN hashes and paired Manifest; no unreviewed retired project source. Synthesis and timing are **NOT_RUN** at this architecture-only baseline.

**Actual Z2 HIL, separately covered within approved Gate 1:** current Boot ID, Root Guard, owner locks, exact Image and Golden recovery verified before loading; keep loaded only when safe. Passive LA2016 CH0/CH1 measure Site 1 SWCLK/SWDIO; CH2/CH3 measure Site 2 SWCLK/SWDIO. Pin contact/GND and capture timestamp must be checked. First static/known-pattern external SWCLK then real Blue Pill DPIDR. A real **two-Site concurrency PASS requires two electrically qualified DUTs simultaneously**; one attached Blue Pill is insufficient. No Flash erase/program until separate target qualification.

**Release gates:** a green host-only CI, virtual DPIDR, or `FPGA Manager=operating` is not physical PASS. Do not merge without Gate 2. Do not deploy/replace the existing FPGA Image under this source-only architecture change.

## 7. Implementation sequence under this direction

1. New machine-readable board/ABI schema and validation; separate from prior PoC.
2. Initial independent two-engine RTL + SWD pad wrapper and authored Cocotb tests (**source exists, simulation NOT_RUN**); complete review, run Cocotb against known golden vectors, harden reset/abort/output isolation and add independent site command buffering.
3. One AXI4-Lite register/FIFO fabric with two truly concurrent site instances, independent completion and fault.
4. Vivado XDC/PS7/HWH/implementation and image-descriptor acceptance; check resource/timing scaling with N=2 then N=8.
5. PS Hardware Broker and native OpenOCD SWD adapter with protected Image admission.
6. After explicit hardware safety admission, LA2016 and real DPIDR on Site 1, then Site 2, then simultaneous real DUT tests.

**Historical source boundary:** PR #1142 is still open Draft and follows a single-Site remote-bitbang PoC; do not merge #1142 as though it implements MPE. Existing `swd_transaction_master.sv`, `swd_waveform_engine.sv`, and fixed-image SWD broker drafts can inform reference vectors, but may not be labeled tested dual-Site external hardware without a new implementation and evidence.
