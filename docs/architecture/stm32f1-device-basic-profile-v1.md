# Manufacturer Device Basic Profile v1

Status: Current read-only manufacturer metadata profile registry
Scope: STM32F1 / STM32F2 / STM32C0 / STM32G0 / STM32G4 Production exact ICPNs
Programming authority: none
Hardware authority: none

## Purpose

This profile family supplies the basic information required by the IC Selector **IC Information**
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
I/O Supply
VDDA
Operating Temperature
```

Memory Map, Flash-controller registers, erase/program geometry and programming sequences
are deliberately outside this Basic Profile. I/O Supply and VDDA remain in the fixed
operator contract but are null until direct ST Product Selector/eStore evidence is admitted.

## Composition

Family profiles are stored under:

```text
data/ic-support/device-basic/*-device-basic-v1.json
```

The registry currently contains:

- STM32F1: 280 exact ICPNs;
- STM32F2: 105 exact ICPNs;
- STM32C0: 226 exact ICPNs;
- STM32G0: 406 exact ICPNs;
- STM32G4: 273 exact ICPNs;
- 1,290 exact bindings in total;
- catalog constraints for Base Device, Package, Pin Count, Flash and Operating Temperature;
- official ST Product Selector/eStore provenance for reusable RAM/electrical groups.

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

Dynamic ST Product Selector/eStore observations are recorded as official basic-product metadata with:

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

For example, an admitted STM32F1/F2/C0/G0/G4 exact ICPN may have a Basic Profile while
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
Production ICPNs       4,853
STM32F1 exact ICPNs      280
STM32F2 exact ICPNs      105
C0 + G0 + G4 ICPNs       905

M0+                    4,853
M1+                    1,290
M2+                        1
M3+                        1
M4+                        1
M5                         0
```

Highest-level distribution is:

```text
M0  3,563
M1  1,289
M2      0
M3      0
M4      1
M5      0
```

`STM32F103C8T6` remains the only M4 golden reference. The other 279 STM32F1 exact
ICPNs stop at M1.

## UI boundary

The IC Information section always shows the ten-field contract. Missing optional electrical
fields render as `—`. STM32F2 has direct ST Product Selector evidence for RAM and Operating VDD while I/O Supply and VDDA remain unavailable. STM32G4 has direct ST eStore evidence for VDDA and therefore
renders a real VDDA range; I/O Supply remains unavailable because no separate allowed-source
value is admitted.

It does not display:

- Memory Map or address ranges;
- Flash page geometry;
- Flash-controller registers.

Programming remains a separate section and continues to fail closed when
`selected_profile` is absent.

## Validation

The deterministic controls prove:

- all 1,290 current Basic Profile Production exact ICPNs are explicitly bound;
- reusable series/density groups are complete;
- catalog identity/package/pin/Flash/temperature drift is rejected;
- non-ST authority is rejected;
- a fake content lock is rejected;
- removing an exact binding does not fall back to family inference;
- one family profile never grants applicability to another family;
- separate F1/F2/C0/G0/G4 family profiles are required for all 1,290 exact bindings;
- registry-wide M1 coverage is 1,290 while M2+ remains unchanged;
- optional VDDA can become available only when directly evidenced; I/O Supply remains fail-closed.

No deployment, PPU runtime, Socket or physical programming state changes are part of this
profile.
