# STM32F103VBT6 / LQFP100 — Exact Socket and Shared Hardware Contract

Status: **design-input only**. Not physical Socket, PPU, HIL, L3 or execution qualification.

## Exact target and evidence

- Exact order code: `STM32F103VBT6`, Base Device `STM32F103VB`, **128 KiB Flash**, LQFP100, T6.
- Official authority: **ST DS5319 Rev 20**, [manufacturer datasheet](https://www.st.com/resource/en/datasheet/stm32f103vb.pdf),
  **Table 1** (`STM32F103x8`/`STM32F103xB` device summary),
  **Figure 4** (common medium-density LQFP100 pinout),
  **Table 5** (pin definitions), power-supply schemes and reference-decoupling figures.
- Qualified software binding: `release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json`,
  `STM32F103VBT6` → `SUPPORTED`, `stm32f1-medium-density-flash-v0`.
- Independent exact-part applicability authority:
  `release/openocd-qualification/stm32f103-medium-density-lqfp-t6-t7-applicability-v2.json`
  (exact `STM32F103VBT6` entry, 100-pin LQFP).
- Flash geometry is **not** inherited from V8: `stm32f103vb-128k-v0`,
  131072 bytes / 128 pages × 1024 bytes / 2-byte programming granularity.
  The original `STM32F103V8T6` remains distinct (`stm32f103v8-64k-v0`,
  65536 bytes / 64 pages).
- Datasheet is publicly referenced and versioned by `st_ds5319_rev20`;
  do **not** imply an immutable PDF byte hash has been verified.

## Package-level reuse boundary

ST DS5319 Rev 20 defines a common LQFP100 pinout for x8 and xB medium-density
variants. The existing `stm32f103-lqfp100-programming-hardware-v1`
package-level profile explicitly admits **only** base devices
`STM32F103V8` and `STM32F103VB`; this change does not grant
all-family or all-package inheritance.

The new `stm32f103vbt6-lqfp100-swd-socket-v1` is a **separate exact-ICPN**
design-input contract which references the same package pin map but binds the
VB software qualification and Flash geometry separately.

| Contact | LQFP100 pins |
|---|---|
| SWDIO / PA13 | 72 |
| SWCLK / PA14 | 76 |
| NRST | 14 |
| BOOT0 (optional programmer contact) | 94 |
| VDD_1–5 | 50, 75, 100, 28, 11 |
| VSS_1–5 | 49, 74, 99, 27, 10 |
| VDDA / VSSA | 22 / 19 |
| VREF+ / VREF− | 21 / 20 |
| VBAT (optional *programmer contact*, **requires separate bias design**) | 6 |
| NC (**do not connect**) | 73 |

There are **17 mandatory contacts**, and BOOT0/VBAT are optional dedicated
programmer contacts. VBAT bias, power sequencing and decoupling must be
designed and reviewed before any physical release.

For this development-fixture profile, the chosen manufacturer's reference
scheme is `VREF+ → VDDA` and `VREF− → VSSA` (DS5319 Figures 39–40).
This is a **PLASMA fixture policy**, not a claim that all applications must
use one reference scheme; any alternative requires its own reviewed contract.

Mechanical design input: nominal body 14 × 14 mm, 16 × 16 mm lead span,
0.5 mm pitch, keyed pin-1 orientation and reverse-insertion prevention.

## Gate 1 test and constraints

- V8 exact socket regression must continue to PASS after the shared package
  profile explicitly adds `STM32F103VB`.
- The new Host-only test validates all 100 numbered pins, 17 required contacts,
  NC pin 73, analog reference policy, both exact L2 records, and the distinct
  128-KiB and 64-KiB Flash geometries.
- **27 negative mutations** must reject wrong ICPN/package, T7/TR
  inheritance, V8 capacity leakage, absent VDD/VSS/VREF/NRST, NC leakage,
  missing VBAT-bias policy, and false HIL/physical-readiness claims.
- `design_input_ready` means schematic/pin assignment may proceed;
  it is **not** Socket vendor qualification, current/thermal margin,
  actual fixture/power validation, software deployment or execution grant.
- No change to ADR-0002, no additional L2 count, no L3 or runtime entitlement.
  No SWPC, Z2, DUT, deployment, physical programming or other PR merge.

```sh
python data/ic-support/validate.py
python data/ic-support/test_stm32f103v8t6_lqfp100_socket_profile.py
python data/ic-support/test_stm32f103vbt6_lqfp100_socket_profile.py
```
