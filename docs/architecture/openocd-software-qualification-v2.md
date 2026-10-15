# OpenOCD Software Qualification v2 — ST ordering-equivalent expansion

Status: **Current ADR-0002 Phase 2 software qualification authority**

## Scope

This revision keeps the Phase 2A reference qualification for:

- `STM32F103C8T6`
- `STM32F103CBT6`

and admits exactly two additional ST commercial ordering variants:

- `STM32F103C8T6TR`
- `STM32F103CBT6TR`

No other STM32F1 exact ICPN is promoted by this transaction.

## Why the TR variants may inherit qualification

ST DS5319 Rev 20 defines the medium-density STM32F103 ordering suffix
`TR` as **tape-and-reel**. Official ST product/eStore evidence separately
lists the four exact commercial ICPNs used by this transaction.

The promotion validator therefore requires both:

1. manufacturer evidence that `TR` is a commercial packing suffix; and
2. exact Production Catalog equality between each variant and its already
   qualified reference for Base Device, package, pin count, Flash size,
   temperature grade, and OpenOCD target CFG.

The only allowed Catalog difference is:

```text
reference option_suffix = ""
variant   option_suffix = "TR"
meaning                 = tape-and-reel
```

Programming semantics are inherited only after those checks pass.

## Exact promotion

```text
STM32F103C8T6
  SUPPORTED
      |
      +-- official packing-only equivalence --> STM32F103C8T6TR
                                                 SUPPORTED

STM32F103CBT6
  SUPPORTED
      |
      +-- official packing-only equivalence --> STM32F103CBT6TR
                                                 SUPPORTED
```

The inherited Phase 2 contract includes:

- Programming Profile identity
- exact Memory Geometry Profile
- exact Main Flash size
- page count
- probe / erase / program / read / verify operation qualification

It does not infer silicon revision, temperature-grade equivalence, package-code
equivalence, or family-wide equivalence.

## Result

| Exact ICPN | Qualification basis | Flash | Pages | Software state |
|---|---|---:|---:|---|
| STM32F103C8T6 | direct reference | 64 KiB | 64 | SUPPORTED |
| STM32F103C8T6TR | packing-only equivalence to C8T6 | 64 KiB | 64 | SUPPORTED |
| STM32F103CBT6 | direct reference | 128 KiB | 128 | SUPPORTED |
| STM32F103CBT6TR | packing-only equivalence to CBT6 | 128 KiB | 128 | SUPPORTED |

A mapped part such as `STM32F103R8T6` remains `UNKNOWN`.

## Evidence boundary

The SW/PPU-owned authority remains under:

`release/openocd-qualification/`

The ordering-equivalence authority is:

`release/openocd-qualification/stm32f103c-tr-ordering-equivalence-v1.json`

It locks the existing manufacturer research evidence by Git blob SHA-1 and
requires the expected exact-ICPN and tape-and-reel markers to remain present.

This remains Phase 2 software qualification only:

- public Catalog visibility is unchanged;
- Job/Batch execution is unchanged;
- installed-runtime attestation is unchanged;
- `hardware_runtime_ready=false`;
- `physical_programming_qualified=false`;
- Phase 3 PPU/Site/Socket/HIL qualification remains separate.
