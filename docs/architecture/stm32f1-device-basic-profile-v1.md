# STM32F1 Manufacturer Device Basic Profile v1

Status: Current read-only manufacturer metadata profile
Scope: 280 Production STM32F1 exact ICPNs
Programming authority: none
Hardware authority: none

## Purpose

This profile supplies the basic information required by the IC Selector **IC Information**
section without coupling basic product metadata to programming-algorithm maturity.

The v1 operator contract is exactly:

```text
ICPN
Base Device
Package
Pin Count
Flash
RAM
Operating VDD
Operating Temperature
```

Memory Map, I/O supply, VDDA, Flash-controller registers, erase/program geometry and
programming sequences are deliberately outside this Basic Profile.

## Composition

The profile is stored in:

```text
data/ic-support/device-basic/stm32f1-device-basic-v1.json
```

It contains:

- 34 reusable STM32F1 series + Flash-density groups for RAM and Operating VDD;
- 280 explicit exact-ICPN bindings;
- catalog constraints for Base Device, Package, Pin Count, Flash and Operating Temperature;
- official ST product-metadata provenance for each reusable group.

The runtime resolver is:

```text
software/python/plasma_core/manufacturer_device_basic.py
```

Resolution is fail-closed. An exact binding must exist and every constrained Production
Catalog field must still match. Family-name similarity or a shared OpenOCD target never
creates an implicit binding.

## Source policy

This Basic Profile intentionally uses official ST **Product Selector / eStore**
metadata rather than the stronger source-locked programming-evidence process.

Dynamic ST Product Selector observations are recorded as official basic-product metadata with:

- ST authority;
- Product Selector source surface;
- official ST Product Selector URL;
- observation date;
- explicit statement that no content lock exists.

The profile does **not** invent a SHA-256 lock for dynamic web content.

This lighter provenance is acceptable only for basic product information. It is not
sufficient authority for Programming Profile facts such as Flash-controller semantics,
unlock keys, erase/program sequences or destructive-security behavior.

## API boundary

`GET /api/devices/search` may return:

```text
manufacturer_device_basic_profile
```

independently from:

```text
selected_profile
```

For example, an STM32F1 exact ICPN may have a Basic Profile while
`selected_profile=null`. That means its basic device information is available but its
manufacturer-derived Programming Profile has not been established.

The Basic Profile always carries:

```text
programming_profile_authority = false
hardware_runtime_ready = false
physical_programming_qualified = false
```

## Coverage effect

At this baseline:

```text
Production ICPNs       4,641
STM32F1 exact ICPNs      280

M0+                    4,641
M1+                      280
M2+                        1
M3+                        1
M4+                        1
M5                         0
```

Highest-level distribution is:

```text
M0  4,361
M1    279
M2      0
M3      0
M4      1
M5      0
```

`STM32F103C8T6` remains the only M4 golden reference. The other 279 STM32F1 exact
ICPNs stop at M1.

## UI boundary

The IC Information section shows the eight Basic Profile fields only.

It does not display:

- Memory Map or address ranges;
- I/O supply;
- VDDA;
- Flash page geometry;
- Flash-controller registers.

Programming remains a separate section and continues to fail closed when
`selected_profile` is absent.

## Validation

The deterministic controls prove:

- all 280 STM32F1 Production exact ICPNs are explicitly bound;
- reusable density groups are complete;
- catalog identity/package/pin/Flash/temperature drift is rejected;
- non-ST authority is rejected;
- a fake content lock is rejected;
- removing an exact binding does not fall back to family inference;
- non-STM32F1 targets do not gain Basic Profile applicability;
- M1 coverage rises to 280 while M2+ remains unchanged.

No deployment, PPU runtime, Socket or physical programming state changes are part of this
profile.
