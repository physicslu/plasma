# Programming Hardware / Socket Design Input v1

Status: **Current engineering-input contract; not hardware qualification**

## 1. Purpose

This contract closes the gap between ADR-0002 Level 2 software programmability and a
hardware engineer's ability to design a real Programming Socket.

Catalog Level 2 means a versioned Programming Provider is software-qualified for an exact
ICPN. It does **not** imply that a Socket, Site, Adapter, power path, signal path, or PPU
configuration has been physically qualified.

The first vertical slice is:

```text
STM32F103C8T6
  -> L2 PROGRAMMABLE
  -> stm32f1-medium-density-flash-v0
  -> stm32f103c8-64k-v0
  -> stm32f103-lqfp48-programming-hardware-v1
  -> stm32f103c8t6-lqfp48-swd-socket-design-v1
```

## 2. Authority

The physical programming-hardware profile is derived from the already source-locked
STMicroelectronics `DS5319 Rev 20` manufacturer source.

The profile uses manufacturer evidence for:

- LQFP48 pinout and pin numbering;
- SWD signal ownership;
- VDD/VSS/VDDA/VSSA supply requirements;
- NRST electrical behavior;
- LQFP48 package dimensions and pitch;
- power-supply decoupling guidance.

Programming algorithm and Flash geometry remain separate authorities:

- `stm32f1-medium-density-flash-v0`
- `stm32f103c8-64k-v0`

OpenOCD software qualification remains the ADR-0002 Level 2 authority.

The Socket Design overlay is additive: it must not mutate, reseal, or supersede the frozen software-admission binding or its Level 2 qualification evidence chain.

## 3. Canonical minimum batteryless SWD fixture contact set

For the STM32F103 LQFP48 package the minimum evidence-backed SWD programming
contact set is:

| Package pin | Signal | Role |
|---:|---|---|
| 7 | NRST | reset/recovery |
| 8 | VSSA | required analog ground |
| 9 | VDDA | required analog supply tied to VDD |
| 23 | VSS_1 | main ground |
| 24 | VDD_1 | main supply / target reference |
| 34 | PA13 / SWDIO | bidirectional SWD data |
| 35 | VSS_2 | main ground |
| 36 | VDD_2 | main supply |
| 37 | PA14 / SWCLK | SWD clock |
| 47 | VSS_3 | main ground |
| 48 | VDD_3 | main supply / bulk decoupling node |

`BOOT0` (pin 44) remains a recommended optional fixture contact for boot-mode control/recovery.
`VBAT` (pin 1) is **mandatory in the batteryless programming fixture policy**: AN2586 Rev 8 recommends tying VBAT to VDD with 100 nF when no external battery is used. It is therefore part of the canonical Socket power/contact set, even though SWD signaling itself does not consume VBAT.

## 4. Mechanical and electrical design inputs

The canonical package-hardware profile carries the LQFP48 package geometry required to
start schematic, footprint and socket-interface design:

- 48 pins;
- 7.0 mm × 7.0 mm body;
- 9.0 mm × 9.0 mm lead span;
- 0.50 mm pitch;
- 1.60 mm maximum package height.

These package dimensions identify the IC envelope and support socket selection, but they do **not** define a vendor-specific programming-socket PCB footprint. The socket manufacturer/part number and its land pattern remain unresolved.

The profile also carries:

- programming/operating VDD range: 2.0–3.6 V;
- no external VPP requirement;
- all main VDD/VSS pins required;
- VDDA/VSSA required and tied to VDD/VSS;
- NRST package pin and internal pull-up range;
- manufacturer decoupling guidance.

These are design inputs, not a released Socket PCB.

## 5. Exact Socket Design Contract

`data/ic-support/socket-design/stm32f103c8t6-lqfp48-swd-v1.json` composes the
exact ICPN with the reusable technical profiles and the qualified OpenOCD route.

It intentionally records implementation decisions that remain open, including:

- actual LQFP48 programming-socket vendor/part number and vendor land pattern;
- batteryless VBAT-to-VDD tie and 100 nF placement;
- socket-to-Site connector pin assignment;
- target power switch/current-limit/discharge circuit;
- SWD driver/series-resistor implementation;
- insertion detection and mechanical keying;
- PCB stack-up and signal-integrity verification;
- production ESD/operator-safety implementation.

Those decisions belong to the Socket/Site implementation, not to the IC's Catalog Level.

## 6. Readiness model

The following states are deliberately independent:

```text
ADR-0002 L2 PROGRAMMABLE
        !=
Socket design input ready
        !=
Hardware runtime ready
        !=
Physical programming qualified
        !=
L3 PLASMA_VERIFIED
```

For the current STM32F103C8T6 vertical slice:

- OpenOCD programmer software development: **ready as L2 software input**
- Socket electrical-interface and schematic design input: **ready**
- specific socket mechanical selection / vendor PCB footprint: **not ready**
- complete Socket PCB layout: **not ready**
- native PL/FPGA SWD transport implementation: **not claimed**
- specific Socket/Site hardware runtime readiness: **false**
- physical programming qualification: **false**
- Socket HIL: **not run**
- execution authorization: **false**

## 7. Validation

CI must fail closed if the canonical profile loses or changes:

- SWDIO pin 34 / PA13;
- SWCLK pin 37 / PA14;
- NRST pin 7;
- any mandatory VDD/VSS/VDDA/VSSA contact;
- package pitch/body geometry;
- the fail-closed hardware qualification boundary.

The exact Socket Design Contract is also regression-checked against
`ResolvedICSupport`, the memory-geometry profile and the OpenOCD route so that a
contract cannot silently drift away from the current exact ICPN support model.
