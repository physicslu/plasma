# PLASMA Z2 HIL hardware inventory — 2026-10-15

> **Reference — operator-observed snapshot, NOT hardware acceptance.** This inventory is
> a reusable wiring/diagnostic reference, not a live preflight, permission to operate
> hardware, or evidence that PSPL-02/SWD-00 is qualified. New Z2 HIL remains
> **HARDWARE NO-GO / NOT RUN**. The authoritative procedure is the
> [PSPL-02 / SWD-00 HIL runbook](pspl02-swd00-hil-runbook.md).
>
> **Public repository privacy boundary:** do not put operator accounts, private hostnames,
> internal IPs, adapter MACs, unique USB serials, credentials, personally identifying host
> paths, raw privileged inventories or recovery binaries here. Store those in a separate
> access-controlled operator evidence vault. USB bus/device numbers are not stable IDs.

## 1. Wiring and equipment baseline

~~~text
Integration Linux host
  |-- Separate management network (do not confuse with Z2 test link)
  |
  +-- Transcend USB 3.x/2.x hub (VID:PID 8564:4100)
        |-- Physical Port 1: unused at observation
        |-- Physical Port 2: PYNQ-Z2 USB PROG/UART / reported 5V primary supply
        |     +-- Xilinx TUL FT2232 (0403:6010): JTAG and two serial interfaces
        |     +-- Z2 Linux + FPGA PL
        |-- Physical Port 3: ASIX AX88179 USB Ethernet (0b95:1790)
        |     +-- Ethernet cable to Z2 dedicated HIL test LAN
        +-- Physical Port 4: KINGST LA2016 (77a1:01a2), 16 inputs
              +-- FPGA SWCLK/SWDIO probe connections: NOT VERIFIED
~~~

The USB 3.x hub at **2-1** and USB 2.x companion at **1-1** are one physical
4-port hub. Power controls generally affect both companion interfaces. At the
observed moment:

| Physical hub port | Observed Linux connection | Device | Status |
| --- | --- | --- | --- |
| 1 | No enumeration | Spare | Unused |
| **2** | USB 2.x **1-1.2**; SuperSpeed companion port 2 | **Xilinx TUL 0403:6010** | FTDI re-enumerated after port ON; two serial nodes returned |
| **3** | USB 3.x **2-1.3**; USB2 companion port 3 | **ASIX AX88179 0b95:1790** | Port power cycle and Ethernet re-enumeration observed |
| **4** | USB 2.x **1-1.4**; USB3 companion port 4 | **KINGST LA2016 77a1:01a2** | USB recognized, KingstVIS Connected |

Do not hard-code USB Device Number, unstable UIO numbers, or ttyUSB enumeration
order in automation. The Z2 FTDI previously enumerated as two ttyUSB nodes,
and may be located using current /dev/serial/by-id/ links. Do not use the
sigrok ftdi-la match for the Xilinx TUL: it is the Z2 JTAG/UART interface.

## 2. Network, port power and recovery observations

The integration host has separate management networking and an AX88179-backed
dedicated Z2 test LAN. The exact interface names, IPs and management route are
deployment-private and must be rechecked before disruptive HIL actions.

- **Port 3 test:** uhubctl reported power OFF/ON on both companions; AX88179
  disappeared, re-enumerated, regained Linux networking and reported
  1000 Mb/s, full duplex, link detected. A subsequent host-to-Z2 check had
  5/5 ICMP replies, **0% loss**, average **0.476 ms** RTT.
- **Port 2 test:** uhubctl reported OFF for both 2-1 and 1-1 port 2.
  After re-enabling, Xilinx TUL 0403:6010 and both serial interfaces reappeared.
  This qualifies the observed **USB port switching/re-enumeration**, not by
  itself the entire board's power loss.
- The operator identifies Hub Port 2 as the Z2 board's **5V primary power**
  via its PROG/UART USB input. This statement has **not** been independently
  confirmed by VBUS/power-rail measurement, alternate-source isolation,
  J9 jumper inspection or hub per-port current-budget qualification.
- Z2 subsequently answered SSH and ICMP. A **Z2-local** Linux boot timestamp
  of **2026-10-15 20:16:42** was observed. The FTDI was seen re-enumerating
  about 20:19; this time discrepancy means the recorded events cannot on
  their own prove the boot resulted from the hub switching operation.
  Host-local uptime must never be confused with Z2 uptime.

**Recovery is NOT QUALIFIED.** USB Hub Port 2 also removes JTAG/UART; the hub
and host are themselves failure dependencies. The PR #937 runbook requires
current independent UART login, an on-site operator's **separate physical
power recovery** and known-good original SD/base image. No hardware GO may be
inferred from these hub experiments. Port 3 is not an allowed recovery power
target. Physical VBUS OFF voltage, board LEDs/rails, power headroom, full
power-failure/restart and emergency recovery remain unverified.

## 3. Z2 embedded-runtime read-only snapshot

| Property | Observed | Qualification limit |
| --- | --- | --- |
| Board / SoC | Operator-identified PYNQ-Z2 / Zynq-7020 | Independent machine board identity unresolved |
| OS / ISA | PYNQ Linux (Ubuntu 22.04), ARMv7 | Observed session |
| Kernel | 6.6.10-xilinx-v2024.1-g3c0eca68c652 | Observed session |
| FPGA Manager | operating | Does not indicate that the candidate firmware is loaded |
| FCLK0 | enabled, 100000000 Hz | Recheck during full preflight |
| Original UIO names | uio0 audio-codec-ctrl; uio1 fabric | Index ordering is not stable; full resource/owner audit pending |
| Runbook original device nodes | 40000000.fabric / 43c00000.audio-codec-ctrl | Driver links, DMA and retained users require independent audit |
| Services | jupyter, plasma-bootstrap, plasma-server, plasma-web, plasma-runtime-activation: all active | No service changes approved |
| UART | Historical console use; FTDI nodes detected | Current independent login/ownership must be verified at execution |
| Root | Interactive SSH sudo authentication followed by sudo -n id -u = 0 | Authorization was **session-specific**, not proof new Codex SSH sessions are root |

**Device Tree evidence, read directly from the running board:**

~~~text
/proc/device-tree -> /sys/firmware/devicetree/base
model: absent
compatible: xlnx,zynq-7000
~~~

The compatible value identifies a **Zynq-7000 family**, not the specific PYNQ-Z2.
At [PR #937](https://github.com/physicslu/plasma/pull/937),
pl/hil/swd04/collect.py and pl/hil/pspl02/runner.py both require a
Device Tree model attribute. Consequently the released inventory and live
runtime identity checks will fail on this image. Fixing the assumption must
**fail closed**, use independent board evidence, cover both call paths, and
must not fabricate a Device Tree model or weaken board-identity guarantees.
It requires the repository's normal Gate 1 review before code edits.

## 4. KINGST LA2016 instrumentation

| Property | Observation / limit |
| --- | --- |
| Model | KINGST LA2016, 16 digital inputs |
| USB | 77a1:01a2, physical Hub Port 4, 1-1.4 |
| Permissions | root:plugdev 0660, authenticated operator USB write test PASS; dedicated VID/PID udev rule |
| KingstVIS | Connected in GUI; **known-signal capture NOT RUN** |
| sigrok | CLI 0.7.2, libsigrok 0.5.2; installed build did not list a KINGST driver |
| Probes | CH-to-Z2 FPGA pin map / 3.3V electrical validation **NOT VERIFIED** |

The current three-aperture control_waveform_loopback BIT deliberately has no
external PL SWD pins. Internal FPGA loopback and simulated Hi-Z do **not**
qualify physical SWCLK, SWDIO, turnaround, input thresholds or DUT programming.

## 5. Acceptance matrix and next boundary

| Item | State (2026-10-15) |
| --- | --- |
| [HIL-PSPL-01 Identity-only](../evidence/hil-pspl-01/2026-10-14-pynq-z2/README.md) | **Historical real-Z2 PASS** |
| [PSPL-02 / SWD-00 offline suite](../evidence/hil-pspl-02/2026-10-15-offline/README.md) | **PASS (host only)**, PR #937 merged |
| [Pinned Vivado baseline](../../pl/projects/z2-control-waveform/baseline-host-2026-10-15.json) | **PASS (host only)**, not loaded/validated on Z2 |
| Hub Port 2 FTDI restart and Port 3 Ethernet restart | **Observed PASS** within limited USB scope |
| Whole-board 5V-off, independent emergency recovery | **NOT VERIFIED** |
| KINGST LA2016 USB and GUI connection | **PASS**; waveform acquisition NOT RUN |
| Unique PYNQ-Z2 board ID, full process/PL/DMA/UIO/clock audit, original metadata backup | **BLOCKED / NOT RUN** |
| PSPL-02 / SWD-00 live MMIO, candidate FPGA load and recovery | **HARDWARE NO-GO / NOT RUN** |

Next: fix the Device Tree missing-model compatibility issue using a separately
approved fail-closed board identity approach, then conduct the fresh root-level
inventory with documented live UART, separate physical recovery, actual
artifacts/metadata, mapping ownership, FPGA clocks and driver review.
Follow the [PSPL-02 / SWD-00 runbook](pspl02-swd00-hil-runbook.md).
**This inventory authorizes no FPGA programming, MMIO writes, driver unbind,
service restart, power operation, DUT connection or IC programming.**
