# OpenOCD Software Qualification v1 — ADR-0002 Phase 2A

Status: **Current Phase 2 reference qualification contract**

## Purpose

ADR-0002 Phase 2 separates four concepts that previously looked similar:

```text
Production exact ICPN identity
        !=
OpenOCD target mapping
        !=
OpenOCD software programming qualification
        !=
Phase 3 physical compatibility / execution permission
```

This contract introduces the third layer.

The first bounded reference cohort is:

```text
STM32F103C8T6
STM32F103CBT6
```

Both exact ICPNs are explicitly reviewed against the PLASMA-pinned upstream
OpenOCD 0.12.0 source. No other STM32F1 device inherits this result merely by
family name, Cortex-M3 core, SWD/JTAG transport, or `stm32f1x.cfg` mapping.

## Pinned provider

```text
OpenOCD:       0.12.0
tag:           v0.12.0
commit:        9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c
runtime_id:    0.12.0-9ea7f3d647c8
target config: tcl/target/stm32f1x.cfg
flash driver:  src/flash/nor/stm32f1x.c / stm32f1x
```

The source lock also pins the Git object IDs of:

- `tcl/target/stm32f1x.cfg`
- `src/flash/nor/stm32f1x.c`
- `src/flash/nor/tcl.c`

The first file establishes the target/transport/Flash-bank composition. The
second establishes the STM32F1 device class and Flash-driver callbacks. The
third establishes generic Flash commands such as `erase_address`,
`write_image`, read paths and `verify_image`.

## Manufacturer side

The reference cohort reuses the already locked ST evidence:

- DS5319 Rev 20
- PM0075 Rev 2
- STM32F103C vendor-neutral admission review
- `stm32f1-medium-density-flash-v0`
- exact C8/CB Memory Geometry Profiles
- exact C8/CB bindings

The programming group establishes:

- SWD and JTAG;
- programming VDD 2.0–3.6 V;
- no external VPP;
- Main Flash base 0x08000000;
- 1 KiB erase pages;
- 16-bit/halfword programming;
- page/mass erase and standard program semantics.

## Software operation qualification

The reference group qualifies only these operations:

| Operation | Phase 2 software result | Important constraint |
|---|---|---|
| probe | SUPPORTED | STM32F10x medium-density device ID 0x410 |
| erase | SUPPORTED | resolved Main Flash; halted target |
| program | SUPPORTED | resolved Main Flash; halfword alignment; no implicit erase |
| read | SUPPORTED | Main Flash; debug/security state must permit read |
| verify | SUPPORTED | explicit readback/image verify; security state must permit read |

The following destructive/security mutations remain outside this qualification:

- Option-byte programming/erase
- RDP enable/disable
- write-protection changes

## Exact geometry

The shared Programming Profile does not collapse exact geometry:

| ICPN | Flash | Pages | State |
|---|---:|---:|---|
| STM32F103C8T6 | 64 KiB | 64 × 1 KiB | SUPPORTED |
| STM32F103CBT6 | 128 KiB | 128 × 1 KiB | SUPPORTED |

The historical Blue Pill 128-KiB override is explicitly not exact-ICPN authority.

## Meaning of SUPPORTED

For this Phase 2 contract, `SUPPORTED` means:

> The exact commercial ICPN has manufacturer-bounded programming applicability,
> exact geometry, and a version-locked OpenOCD Target/Flash Driver/framework
> source path that implements the declared probe/erase/program/read/verify
> operations under recorded constraints.

It does **not** mean:

- a real PPU has an attested installed binary;
- FPGA/SWD electrical signaling has passed;
- a Site/Socket/Adapter is compatible;
- a real IC erase/program/verify has passed;
- Job/Batch execution is authorized.

Those remain independent runtime and Phase 3 gates.

## Product visibility boundary

This Phase 2A PR does **not** change the public Catalog or IC Selector filter.
Issue #849 remains the product-visibility migration. The qualification registry
is the evidence authority that a later Phase 2C visibility transaction can
consume.

Therefore:

```text
Phase 2A SUPPORTED evidence exists
        ↓
public visibility unchanged for now
        ↓
Phase 2C explicitly migrates all API/UI/count surfaces to SUPPORTED-only
```

## Validation

From repository root:

```bash
PYTHONPATH=software/python \
python software/python/tests/test_openocd_software_qualification_v1.py
```

The validator fails closed on:

- packaged OpenOCD version/commit drift;
- source-lock identity drift;
- reviewed local evidence Git-blob drift;
- Production exact-ICPN route drift;
- geometry/applicability drift;
- operation-set expansion;
- unsafe hardware/runtime/public-Catalog claims;
- accidental family-wide qualification.
