# STM32F103RBT6 / LQFP64 — Explicit Hardware Reuse with Exact 128-KiB Geometry

Status: **design input only**. It is not physical Socket/HIL/PPU/runtime qualification.

## Decision and evidence

- **Exact ICPN:** `STM32F103RBT6`, Base Device `STM32F103RB`, 128 KiB, LQFP64, T6.
- **Manufacturer authority:** ST DS5319 Rev 20 (x8 and xB medium-density ordering, Table 5 and
  Figure 6 LQFP64 pinout), https://www.st.com/resource/en/datasheet/stm32f103rb.pdf.
- **Software authority:** `release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json`.
  The record is `SUPPORTED`, exactly bound to `stm32f1-medium-density-flash-v0`.
- **Applicability:** `release/openocd-qualification/stm32f103-medium-density-lqfp-t6-t7-applicability-v2.json`;
  an explicit `STM32F103RBT6` target binds **LQFP64** and
  `stm32f103rb-128k-v0`. Do not synthesize applicability from order-code prefixes.
- **Flash geometry:** `stm32f103rb-128k-v0`, 128 KiB / 128 × 1024-byte pages /
  2-byte programming granularity. R8 has *different* 64 KiB / 64-page geometry.

## Reuse decision

The existing ST DS5319-sourced `stm32f103-lqfp64-programming-hardware-v1`
has a 64-contact physical map common to the explicitly reviewed **R8** and **RB**
Base Devices. Its applicability is extended to these two exact base devices
**only**. The new `stm32f103rbt6-lqfp64-swd-socket-v1` is a separate exact
ICPN record that consumes the shared **package** profile and independently
binds the **128-KiB** software geometry.

The package-level mandatory contacts remain the same as the reviewed R8 profile:

| Signal or rail | LQFP64 package pins |
|---|---|
| PA13 / SWDIO | 46 |
| PA14 / SWCLK | 49 |
| NRST | 7 |
| BOOT0 (optional SWD contact) | 60 |
| Four VDD | 32, 48, 64, 19 |
| Four VSS | 31, 47, 63, 18 |
| VDDA / VSSA | 13 / 12 |
| VBAT (optional programmer contact; **bias circuit is still mandatory design work**) | 1 |

- Required contacts: 13; optional programmer contacts: 2.
- LQFP64 nominal body 10 × 10 mm, lead span 12 × 12 mm, pitch 0.5 mm.
- Supply policy: 2.0–3.6 V, no external programming VPP.

## Non-claims and safeguards

- Reuse is limited to *manufacturer-evidenced identical physical package facts*.
  It is **not** an inference of identical memory geometry, device identity,
  physical contact qualification or HIL.
- No implicit extension to T7, TR, V-package devices, or every STM32F103.
- `design_input_ready` = enough input for schematic/pin assignment, **not** Socket
  vendor qualification, contact resistance, production current/signal margin, HIL, L3
  or Job execution authorization.
- No SWPC/Z2/real DUT, physical power, FPGA, deployment or L2/L3 policy changes.

## Host-only CI

```sh
python data/ic-support/validate.py
python data/ic-support/test_stm32f103r8t6_lqfp64_socket_profile.py
python data/ic-support/test_stm32f103rbt6_lqfp64_socket_profile.py
```

The original R8 contract must remain valid. The new test checks all 64 package
contacts, distinct 128-KiB geometry, exact L2/applicability and 18 fail-closed
mutations (wrong exact order code, package, memory geometry, missing rails and
false physical validation claims).
