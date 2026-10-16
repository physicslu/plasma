# OpenOCD Software Qualification v7 — STM32F103 high-density Z-pin LQFP expansion

Status: **Current ADR-0002 Programming Qualification authority for Catalog Level 2 derivation**

## Scope

v7 preserves the v4 medium-density authority and replaces the v6 high-density R/V-pin
cohort authority with a bounded R/V/Z-pin LQFP authority. No Catalog Level 1 identity is added.

The combined registry contains **49 exact ICPNs**:

- 22 medium-density exact ICPNs from v4;
- 19 previously qualified high-density R/V-pin LQFP exact ICPNs;
- 8 newly qualified high-density Z-pin LQFP exact ICPNs.

The ST Catalog Level 1 frozen denominator remains **4,629 exact ICPNs** in the Device Registry. This transaction changes
only Programming Qualification; `SUPPORTED` rows derive Catalog Level 2 `PROGRAMMABLE`.

## New Z-pin direct cohort

Direct manufacturer-applicability records:

- `STM32F103ZCT6`
- `STM32F103ZCT7`
- `STM32F103ZDT6`
- `STM32F103ZET6`
- `STM32F103ZET7`

The cohort is bounded to pin code `Z` (144 pins), package code `T` (LQFP), and
high-density C/D/E Flash codes. Only exact commercial identities already present in the
locked ST Production authority are admitted.

The following syntactically plausible codes are **not** admitted because they are absent
from the locked exact-identity authority:

- `STM32F103ZDT6TR`
- `STM32F103ZDT7`
- `STM32F103ZDT7TR`
- `STM32F103ZET7TR`

Ordering grammar alone is not Programming Qualification evidence.

## Z-pin packing-only inheritance

The following exact `TR` variants inherit Programming Qualification semantics only from their directly
qualified non-TR exact ICPN:

- `STM32F103ZCT6TR` ← `STM32F103ZCT6`
- `STM32F103ZCT7TR` ← `STM32F103ZCT7`
- `STM32F103ZET6TR` ← `STM32F103ZET6`

Existing R/V-pin packing-only inheritance remains unchanged.

## Programming semantics

Z-pin devices do not gain qualification merely from sharing STM32F103 naming. v7 binds
their exact Production identities to independent ZC/ZD/ZE geometry profiles and the
reviewed high-density programming profile:

- OpenOCD 0.12.0 commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`;
- target `tcl/target/stm32f1x.cfg`;
- Flash driver `stm32f1x`;
- high-density OpenOCD device-ID class `0x414`;
- Main Flash base `0x08000000`;
- 2-KiB page erase geometry;
- 2-byte halfword programming;
- programming VDD 2.0–3.6 V;
- no external VPP.

Exact geometry:

| Base Device | Main Flash | Page size | Page count |
|---|---:|---:|---:|
| STM32F103ZC | 256 KiB | 2 KiB | 128 |
| STM32F103ZD | 384 KiB | 2 KiB | 192 |
| STM32F103ZE | 512 KiB | 2 KiB | 256 |

The same high-density programming semantics remain separately bound to RC/RD/RE and
VC/VD/VE.

## Deliberately still UNKNOWN

This transaction does **not** qualify:

- high-density LFBGA or WLCSP variants;
- syntactically plausible but non-admitted Z-pin order codes listed above;
- XL-density F/G devices;
- option-byte, RDP or write-protection mutation;
- any Catalog Level 3 PPU/Site/Socket/Adapter/HIL verified configuration.

## Evidence boundary

DS5792 Rev 13 ordering/programming applicability is source-registered and the derived
repository authorities are content-addressed. The raw DS5792 manufacturer PDF bytes are
still not held as a canonical content-pinned evidence-vault object. v7 therefore does not
claim full raw-source custody for that document.

## Catalog Level boundary

v7 remains **provider-specific Programming Qualification evidence only**:

- Catalog Level 1 ST remains frozen at 4,629 exact ICPNs and is the Device Registry identity authority;
- the canonical runtime API is `programming_qualification`, not an OpenOCD-specific UI contract;
- these 49 reviewed exact ICPNs have `ProgrammingQualification.state == SUPPORTED` and therefore derive Catalog Level 2 `PROGRAMMABLE`; all other Level 1 exact ICPNs remain `UNKNOWN` until independently reviewed;
- Job/Batch execution authorization is unchanged and remains fail-closed outside the qualification projection;
- installed-runtime attestation is unchanged;
- `hardware_runtime_ready=false`;
- `physical_programming_qualified=false`;
- Catalog Level 3 `PLASMA_VERIFIED` remains separate.
