# OpenOCD Software Qualification v6 — STM32F103 high-density V-pin LQFP expansion

Status: **Current ADR-0002 Phase 2 software qualification authority**

## Scope

v6 preserves the v4 medium-density authority and replaces the v5 high-density R-pin
cohort authority with a bounded R/V-pin LQFP authority. No Phase 1 identity is added.

The combined registry contains **41 exact ICPNs**:

- 22 medium-density exact ICPNs from v4;
- 9 previously qualified high-density R-pin LQFP exact ICPNs;
- 10 newly qualified high-density V-pin LQFP exact ICPNs.

The ST Phase 1 frozen denominator remains **4,629 exact ICPNs**. This transaction changes
only Phase 2 software qualification.

## New V-pin direct cohort

Direct manufacturer-applicability records:

- `STM32F103VCT6`
- `STM32F103VDT6`
- `STM32F103VDT7`
- `STM32F103VET6`
- `STM32F103VET7`

The cohort is bounded to pin code `V` (100 pins), package code `T` (LQFP), and
high-density C/D/E Flash codes. Only exact commercial identities already present in the
locked ST Production authority are admitted. In particular, `STM32F103VCT7` is not
synthesized from ordering grammar.

## V-pin packing-only inheritance

The following exact `TR` variants inherit Phase 2 semantics only from their directly
qualified non-TR exact ICPN:

- `STM32F103VCT6TR` ← `STM32F103VCT6`
- `STM32F103VDT6TR` ← `STM32F103VDT6`
- `STM32F103VDT7TR` ← `STM32F103VDT7`
- `STM32F103VET6TR` ← `STM32F103VET6`
- `STM32F103VET7TR` ← `STM32F103VET7`

The existing R-pin packing-only inheritance remains unchanged.

## Programming semantics

V-pin devices do not gain qualification merely from sharing an STM32F103 name. v6 binds
their exact Production identities to independent VC/VD/VE geometry profiles and the
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
| STM32F103VC | 256 KiB | 2 KiB | 128 |
| STM32F103VD | 384 KiB | 2 KiB | 192 |
| STM32F103VE | 512 KiB | 2 KiB | 256 |

The same high-density programming semantics remain separately bound to RC/RD/RE.

## Deliberately still UNKNOWN

This transaction does **not** qualify:

- high-density Z-pin LQFP variants;
- high-density LFBGA or WLCSP variants;
- syntactically plausible but non-admitted order codes such as
  `STM32F103VCT7`, `STM32F103RDT7` or `STM32F103RET7TR`;
- XL-density F/G devices;
- option-byte, RDP or write-protection mutation;
- any Phase 3 PPU/Site/Socket/Adapter/HIL configuration.

## Evidence boundary

DS5792 Rev 13 ordering/programming applicability is source-registered and the derived
repository authorities are content-addressed. The raw DS5792 manufacturer PDF bytes are
still not held as a canonical content-pinned evidence-vault object. v6 therefore does not
claim full raw-source custody for that document.

## Phase boundary

v6 remains **software qualification only**:

- Phase 1 ST remains frozen at 4,629 exact ICPNs;
- public Catalog migration is unchanged;
- Job/Batch execution authorization is unchanged;
- installed-runtime attestation is unchanged;
- `hardware_runtime_ready=false`;
- `physical_programming_qualified=false`;
- Phase 3 remains separate.

