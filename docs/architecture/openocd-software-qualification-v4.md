# OpenOCD Software Qualification v4 — STM32F103 medium-density T7 expansion

Status: **Current ADR-0002 Phase 2 software qualification authority**

## Scope

This revision keeps the v3 STM32F103 medium-density programming group and adds a bounded
temperature-code-7 cohort only where an exact commercial ICPN already exists in the locked
Production Catalog.

New direct manufacturer-applicability records:

- `STM32F103C8T7`
- `STM32F103CBT7`
- `STM32F103R8T7`
- `STM32F103RBT7`
- `STM32F103VBT7`

New packing-only ordering-equivalence records:

- `STM32F103C8T7TR`
- `STM32F103CBT7TR`
- `STM32F103R8T7TR`
- `STM32F103RBT7TR`
- `STM32F103VBT7TR`

Together with the 12 v3 records, v4 contains **22 exact ICPNs**.

## Why T7 is a direct applicability review

Temperature code `7` is not inherited from code `6`. ST DS5319 Rev 20 defines the
commercial temperature code and specifies the Flash programming/erase characteristics over
the relevant -40 to +105 °C ambient range. The qualification therefore admits each T7 exact
ICPN directly, while retaining the same medium-density programming semantics:

- OpenOCD 0.12.0 pinned to commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`;
- target `tcl/target/stm32f1x.cfg`;
- `stm32f1x` Flash driver and device-ID class `0x410`;
- Main Flash base `0x08000000`;
- 1-KiB erase page;
- 2-byte halfword programming;
- programming VDD 2.0–3.6 V;
- no external VPP.

Exact Flash size and page count still come from the selected Base Device's locked Memory
Geometry Profile; they are not inferred from another commercial order code.

## Packing-only inheritance

`TR` remains a separate commercial suffix and may inherit Phase 2 software qualification
only after its non-TR exact ICPN is directly qualified. The deterministic contract requires
equal Base Device, package, pin count, Flash size, temperature grade and target CFG. The only
permitted difference is the packing suffix.

This means T6 → T7 is **not** an equivalence relation. T7 direct qualification must exist
before T7TR can inherit.

## Deliberately still UNKNOWN

The following are outside this transaction:

- `STM32F103V8T7`: no locked Production exact identity exists, so ordering syntax is not
  allowed to synthesize the part;
- UFQFPN and BGA package variants, even when they share a Base Device;
- high-density / XL-density STM32F103 devices such as `STM32F103RCT6`;
- option-byte/security mutations.

The default for every unreviewed exact ICPN remains `UNKNOWN`.

## Phase boundary

v4 is still **software qualification only**:

- public Catalog eligibility/counts are unchanged;
- Job/Batch execution authorization is unchanged;
- installed-runtime attestation is unchanged;
- `hardware_runtime_ready=false`;
- `physical_programming_qualified=false`;
- PPU/Site/Socket/HIL remain Phase 3.

The IC Selector may project these 22 exact ICPNs as Software Qualification `SUPPORTED`,
but that status must not be presented as physical programming qualification.
