# STM32F103R8T6 / LQFP64 — Programming Hardware & Socket Design Input

Status: **exact-ICPN design-input contract only**. No physical qualification is claimed.

## Exact target and authority

- Exact ICPN: `STM32F103R8T6`; 64 KiB medium-density Flash, LQFP64, T6.
- Existing ADR-0002 Phase 2 OpenOCD software-qualification record:
  `release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json`
  uses `stm32f1-medium-density-flash-v0` and exact
  `stm32f103r8-64k-v0` geometry (64 pages of 1 KiB).
- Package authority: **ST DS5319 Rev 20**,
  [official manufacturer datasheet](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf);
  Figure 6 LQFP64 pinout, Table 5 pin definitions, and Table 59 mechanical data.
- The source catalog `data/ic-support/evidence/sources.json` identifies
  `st_ds5319_rev20`; manufacturer PDF content is not pinned in that catalog.

## Distinct hardware facts (not copied LQFP48 pin numbers)

| Interface / power | LQFP64 package contact |
|---|---|
| PA13 / SWDIO | 46 |
| PA14 / SWCLK | 49 |
| NRST | 7 |
| BOOT0 (optional recovery) | 60 |
| Main VDD | 19, 32, 48, 64 |
| Main VSS | 18, 31, 47, 63 |
| VDDA, VSSA | 13, 12 |
| VBAT (optional SWD contact; fixture bias design required) | 1 |

- 64/64 package pins recorded; LQFP64 10 × 10 mm nominal body,
  12 × 12 mm lead span, 0.50 mm pitch, 1.60 mm maximum height.
- Nominal programming supply 2.0–3.6 V; external programming VPP not required.
- 13 fixture contacts are mandatory (SWDIO, SWCLK, NRST, all
  VDD/VSS, VDDA/VSSA); BOOT0 and VBAT are optional **signal contact
  selections**, not permission to omit VBAT supply design.
- The fixture schematic must document VBAT bias/decoupling before physical release.
  The exact socket/carrier circuit remains outside this data-only scope.

## Trust boundaries

- `design_input_ready` means only sufficient pin/electrical/geometry
  information for socket schematic and contact assignment.
- This is exactly `STM32F103R8T6`, **not** `STM32F103RBT6`, any T7/TR
  variant, or all LQFP64 devices.
- Same OpenOCD target / same family does not authorize pin inheritance.
- No FPGA, PPU, Site, DUT, runtime, HIL, PCB, socket-vendor approval,
  power-switch qualification, current-limit or signal-integrity validation.
- L2 software qualification is unchanged; physical programming qualification,
  production release and L3 remain false.

## Validation

```bash
python data/ic-support/validate.py
python data/ic-support/test_stm32f103r8t6_lqfp64_socket_profile.py
```

The second test checks 64 physical pin identities, exact L2/geometry authority,
13 mandatory contacts and negative tests for unsafe pin, power, scope and HIL drift.
