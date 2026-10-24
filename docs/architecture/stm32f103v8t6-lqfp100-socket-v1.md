# STM32F103V8T6 / LQFP100 — Programming Hardware & Socket Design Input

Status: **exact-ICPN design-input contract only**. No physical qualification is claimed.

## Identity, manufacturer authority, and software boundary

- Target exactly `STM32F103V8T6` / LQFP100 / 64 KiB Flash / T6.
- Source: **STMicroelectronics DS5319 Rev 20**:
  [official datasheet](https://www.st.com/resource/en/datasheet/stm32f103vb.pdf).
  Use Figure 4 (100-pin pinout), Table 5 (pin descriptions),
  section 2.3.9 (power), Figures 39–40 (analog reference decoupling),
  and Table 56 (LQFP100 mechanics).
- Existing software Phase 2 `SUPPORTED` record in
  `release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json`;
  shares programming semantics `stm32f1-medium-density-flash-v0`,
  with distinct exact Flash geometry `stm32f103v8-64k-v0`.
- `st_ds5319_rev20` is declared in the research evidence source registry.
  Do not invent a PDF content SHA from the source registry (marked unpinned).

## Independent LQFP100 package contacts

| SWD / supply / configuration | Physical pin |
|---|---|
| PA13 / SWDIO | 72 |
| PA14 / SWCLK | 76 |
| NRST | 14 |
| BOOT0 (optional SWD recovery contact) | 94 |
| VDD_1..5 | 50, 75, 100, 28, 11 |
| VSS_1..5 | 49, 74, 99, 27, 10 |
| VDDA / VSSA | 22 / 19 |
| VREF+ / VREF− | 21 / 20 |
| VBAT (optional external SWD contact; electrical bias must be designed) | 6 |
| NC, must not connect | 73 |

All 100 pin identities are recorded in the hardware profile, including `NC`.
The resulting *development fixture profile* makes 17 contacts mandatory:
SWDIO, SWCLK, NRST, five VDD, five VSS, VDDA, VSSA, VREF+, VREF−.
BOOT0 and VBAT are optional **dedicated programmer contacts**, not permission
to float VBAT or omit its electrical bias/decoupling design.

## Analog reference is a distinct engineering contract

LQFP100 provides separate analog reference pins. The fixture design-input
selects the manufacturer's **Figure 40** scheme: `VREF+ -> VDDA` and
`VREF- -> VSSA` with reference decoupling subject to subsequent schematic
and placement review. This does not claim ST requires the same exact reference
configuration for every application; the selection is a deterministic
PLASMA development-fixture policy. A designer choosing an external reference
must create a separately reviewed circuit/profile rather than mutating pinouts.

`VDDA`/`VSSA` follow the manufacturer supply instructions. Before any
physical work, separately close VBAT bias, source sequencing, decoupling
placement and current limitation. No power circuit has been built or measured.

## Mechanical and readiness boundary

- Nominal LQFP100 **14 × 14 mm body**, **16 × 16 mm lead span**,
  **0.50 mm pitch**, **1.60 mm maximum height**.
- Pin-1 orientation and reverse insertion prevention are required.
- `design_input_ready` means only that pin assignment and schematic work
  may begin; **not** fixture vendor/part, PCB, SI, thermal/current, production,
  physical socket qualification, HIL, runtime readiness or execution authority.
- This exact Socket Profile applies **only** to `STM32F103V8T6`. The separately
  reviewed `STM32F103VBT6` profile reuses the DS5319 LQFP100 physical map but
  binds **independent 128-KiB Flash geometry** and its own exact L2 record.
  Neither profile automatically covers T7/TR or another package/density.
- No ADR-0002 level change. No SWPC/Z2/DUT operations or deployment.

## Host-only gate

```sh
python data/ic-support/validate.py
python data/ic-support/test_stm32f103v8t6_lqfp100_socket_profile.py
```

The test independently checks every numbered package pin, all seventeen
mandatory/optional contacts, L2/Flash geometry, reference supply policy,
NC isolation, physical readiness false states and twelve fail-closed mutations.
