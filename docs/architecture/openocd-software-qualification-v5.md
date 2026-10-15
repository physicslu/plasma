# OpenOCD Software Qualification v5 — STM32F103 bounded multi-density authority

Status: **Historical ADR-0002 Phase 2 software qualification authority; superseded by v6**

## Scope

v5 converts the STM32F103 qualification from one hard-coded density cohort into a
content-addressed umbrella manifest. The existing v4 medium-density authority remains
unchanged and a new, independently reviewed high-density cohort is added.

The combined registry contains **31 exact ICPNs**:

- 22 existing medium-density exact ICPNs from v4;
- 5 directly reviewed high-density R-pin LQFP exact ICPNs;
- 4 high-density tape-and-reel variants that inherit only from an already directly
  qualified exact source ICPN.

This is deliberately not a family-wide qualification.

## New high-density direct cohort

Direct manufacturer-applicability records:

- `STM32F103RCT6`
- `STM32F103RCT7`
- `STM32F103RDT6`
- `STM32F103RET6`
- `STM32F103RET7`

The cohort is bounded to pin code `R` (64 pins), package code `T` (LQFP), density
codes `C/D/E`, and exact Production identities already admitted from ST evidence.

No commercial order code is synthesized from the ordering grammar.

## High-density programming semantics

High-density devices are not allowed to inherit the medium-density Flash geometry.

The new programming group is independently locked to:

- OpenOCD 0.12.0 commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`;
- target `tcl/target/stm32f1x.cfg`;
- `stm32f1x` Flash driver;
- OpenOCD high-density device ID class `0x414`;
- Main Flash base `0x08000000`;
- **2-KiB page erase geometry**;
- 2-byte halfword programming;
- programming VDD 2.0–3.6 V;
- no external VPP.

Exact geometry remains per Base Device:

| Base Device | Main Flash | Page size | Page count |
|---|---:|---:|---:|
| STM32F103RC | 256 KiB | 2 KiB | 128 |
| STM32F103RD | 384 KiB | 2 KiB | 192 |
| STM32F103RE | 512 KiB | 2 KiB | 256 |

A separate OpenOCD differential-evidence artifact locks the `0x414` device branch,
2048-byte page size, 512-KiB upper bound and 2-byte programming alignment. This prevents
a future source change from silently collapsing high-density behavior into the
medium-density 1-KiB model.

## Packing-only inheritance

The following exact `TR` variants inherit Phase 2 semantics only from their already
qualified non-TR source:

- `STM32F103RCT6TR` ← `STM32F103RCT6`
- `STM32F103RCT7TR` ← `STM32F103RCT7`
- `STM32F103RDT6TR` ← `STM32F103RDT6`
- `STM32F103RET6TR` ← `STM32F103RET6`

The deterministic equivalence contract requires equal Base Device, package, pin count,
Flash size, temperature grade and target configuration. Only the commercial packing
suffix may differ.

## Deliberately still UNKNOWN

This transaction does not qualify:

- high-density WLCSP64 variants such as `STM32F103RCY6TR`,
  `STM32F103RDY6TR` or `STM32F103REY6TR`;
- high-density V/Z pin/package variants;
- syntactically plausible but non-admitted `STM32F103RDT7`;
- syntactically plausible but non-admitted `STM32F103RET7TR`;
- XL-density F/G devices;
- option-byte, read-protection or write-protection mutation.

Every unreviewed exact ICPN remains `UNKNOWN`.

## Scalable qualification architecture

The v5 manifest is intentionally an umbrella over bounded cohort authorities rather
than a monolithic family declaration. This is the required direction for PLASMA:
different density, package, voltage, security or backend semantics can be reviewed as
separate cohorts while the public registry exposes one deterministic exact-ICPN view.

A future cohort therefore does not gain support merely because it shares
`stm32f1x.cfg` or an STM32F103 family name.

## Phase boundary

v5 remains **software qualification only**:

- public Catalog eligibility/counts are unchanged;
- Job/Batch execution authorization is unchanged;
- installed-runtime attestation is unchanged;
- `hardware_runtime_ready=false`;
- `physical_programming_qualified=false`;
- PPU/Site/Socket/HIL remain Phase 3.

The IC Selector may display these 31 exact ICPNs as Software Qualification
`SUPPORTED`, but must not imply physical programming qualification.
