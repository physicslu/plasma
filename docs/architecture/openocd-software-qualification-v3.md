# OpenOCD Software Qualification v3 — STM32F103 medium-density R/V expansion

Status: **Current ADR-0002 Phase 2 software qualification authority**

## Scope

This revision extends the already-qualified STM32F103 medium-density cohort with
four additional direct T6 exact ICPNs and their four tape-and-reel variants.

Direct manufacturer-applicability additions:

- `STM32F103R8T6`
- `STM32F103RBT6`
- `STM32F103V8T6`
- `STM32F103VBT6`

Packing-only inherited additions:

- `STM32F103R8T6TR`
- `STM32F103RBT6TR`
- `STM32F103V8T6TR`
- `STM32F103VBT6TR`

The prior C8/CB direct references and C8TR/CBTR packing variants remain
qualified. The complete v3 cohort is therefore 12 exact ICPNs.

## Manufacturer applicability

ST DS5319 Rev 20 is the medium-density STM32F103 ordering authority for Flash
codes `8` and `B`. The repository's locked ordering authority records:

- R pin code = 64 pins;
- V pin code = 100 pins;
- package code T = LQFP;
- temperature code 6 = -40 to 85 °C;
- Flash code 8 = 64 KiB;
- Flash code B = 128 KiB;
- allowed commercial tails = empty or `TR`.

PM0075 Rev 2 supplies the common medium-density Flash programming semantics:

- Main Flash base 0x08000000;
- 1 KiB erase pages;
- halfword / 2-byte programming;
- standard erase/program/read/verify behavior;
- programming VDD 2.0–3.6 V;
- no external VPP.

The PLASMA-pinned OpenOCD 0.12.0 source continues to bind this group to device
ID 0x410 and the `stm32f1x` Flash driver.

## Exact geometry remains separate

| Exact ICPN | Base Device | Flash | Pages | Qualification basis |
|---|---|---:|---:|---|
| STM32F103C8T6 | STM32F103C8 | 64 KiB | 64 | direct reference |
| STM32F103CBT6 | STM32F103CB | 128 KiB | 128 | direct reference |
| STM32F103R8T6 | STM32F103R8 | 64 KiB | 64 | manufacturer applicability |
| STM32F103RBT6 | STM32F103RB | 128 KiB | 128 | manufacturer applicability |
| STM32F103V8T6 | STM32F103V8 | 64 KiB | 64 | manufacturer applicability |
| STM32F103VBT6 | STM32F103VB | 128 KiB | 128 | manufacturer applicability |

Each base device has an explicit Memory Geometry Profile. Geometry is not
inferred from package size or from another exact ICPN.

## Packing-only inheritance

For the six T6 direct references, `TR` may inherit qualification only when:

1. ST ordering authority still defines `TR` as tape-and-reel;
2. the Production Catalog contains both exact commercial ICPNs;
3. Base Device, package, pin count, Flash, temperature and Target CFG are equal;
4. the only allowed Catalog difference is `option_suffix: "" -> "TR"`;
5. Programming Profile, Memory Geometry, Flash size/page count and operation set
   remain identical to the already-reviewed direct reference.

This makes packing inheritance deterministic rather than a suffix heuristic.

## Deliberately still UNKNOWN

This transaction does not promote temperature/package variants. For example:

```text
STM32F103R8T6   SUPPORTED
STM32F103R8T6TR SUPPORTED
STM32F103R8T7   UNKNOWN
```

Likewise BGA/H-package variants remain outside this transaction even when they
share the same Base Device.

High-density devices such as `STM32F103RCT6` also remain outside this
medium-density qualification.

## Phase boundary

v3 remains Phase 2 software qualification only:

- public Catalog eligibility/counts are unchanged;
- Job/Batch execution is unchanged;
- installed runtime attestation is unchanged;
- `hardware_runtime_ready=false`;
- `physical_programming_qualified=false`;
- PPU/Site/Socket/HIL remain Phase 3.

The IC Selector may display these exact ICPNs as Software Qualification
`SUPPORTED`, but that must not be presented as physical programming
qualification.
