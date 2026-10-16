# Programming Hardware and Socket Profile v1

## Purpose

Catalog Level 2 means a versioned software Programming Provider is qualified for the exact ICPN.
It does not mean that a physical fixture or socket has been designed or qualified.

This contract adds a separate hardware-engineering projection:

```text
L2 exact ICPN
  -> Programming Hardware Profile
  -> exact Socket Profile
  -> schematic / pin assignment
  -> physical fixture build
  -> electrical + signal-integrity validation
  -> runtime / real-target HIL
  -> L3 only when the versioned PLASMA configuration passes
```

## STM32F103C8T6 vertical slice

The first reviewed target is `STM32F103C8T6` in LQFP48 using SWD.

The Programming Hardware Profile records:

- complete physical pins 1..48;
- SWDIO PA13 / pin 34;
- SWCLK PA14 / pin 37;
- NRST pin 7 and its internal pull-up range;
- BOOT0 pin 44 as an optional fixture contact for the SWD route;
- every main VDD/VSS contact plus VDDA/VSSA;
- 2.0–3.6 V programming supply and no external VPP;
- LQFP48 7 mm × 7 mm body, 9 mm × 9 mm lead span, 0.5 mm pitch;
- pin-1 orientation as a mandatory fixture design input.

The exact Socket Profile converts those facts into mandatory and optional fixture contacts.

## Readiness semantics

`design_input_ready` means the repository has enough manufacturer-backed information to begin
socket-carrier schematic and pin-assignment work.

It explicitly does **not** mean:

- a socket vendor/part number has been selected;
- contact resistance/current limits are qualified;
- SWD maximum production clock is qualified;
- signal integrity is proven;
- mechanical cycle life is proven;
- the physical socket has programmed a DUT;
- HIL has passed;
- execution is authorized.

These are later hardware/runtime gates and must remain fail-closed.

## Authority

The current STM32F103C8T6 hardware facts are derived from STMicroelectronics DS5319 Rev 20.
The repository source catalog retains the manufacturer document identity; the deterministic
IC Support validator enforces the machine-readable projection.
