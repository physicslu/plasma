# Microchip OpenOCD-first Research Gate v1

**Scope:** ADR-0002 and Issue #851. **Research-only. No Production ICPN admission, public PLASMA Catalog publication, runtime execution, PPU or Socket qualification.**

## Source and population boundaries

- The PLASMA release authority is `release/openocd.json`, **OpenOCD 0.12.0**, upstream source tag `v0.12.0`, immutable commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`. Do not silently mix in a newer `master` or an ST/vendor fork.
- The checked-in `microchip-openocd-first-source-lock-v1.json` records nine **P0 static target + Flash driver source leads**, two **P1 target-only leads**, upstream Git blob identities and conservative Core/Transport classes. Neither number is an official *number of chips*.
- Each P0 lead explicitly has `qualification_state=UNKNOWN`: it records an upstream Flash Bank with a named driver whose code has `erase/write/probe/read` handlers, **not** a validated exact ICPN. Target-side silicon ID, memory geometry, revision, security state and specific operation applicability still require proof.
- **Microchip's existing 24,051 source-linked Research candidate ICPNs are preserved.** There is no crosswalk from these exact ordering candidates to every verified silicon variant in this PR; it would be incorrect to publish any as `OpenOCD SUPPORTED` from this analysis alone.
- Historical DFP support-name index: source SHA-256 `9a00c71e262882687219fce322169435a36d45ac06d0a26bf146c4d6a5db83b0`. The DFP device list is a **device-name candidate inventory**, not a manufacturer-wide commercial SKU census.
- The older `openocd-target-capabilities.json` is sourced from upstream commit `56b8d93...`, not the pinned PLASMA release. It must not be used to claim current-release capabilities without a fresh version-locked check.

## Research Core × Debug Transport × Flash Driver source leads

| Priority | Device-group lead | Core (research evidence) | Transport | Pinning: Target → Flash Driver |
|---|---|---|---|---|
| P0 | SAM D/C/R/L0 (bounded; generic config) | ARM Cortex-M0-class (M0 vs M0+ device-specific) | SWD | `at91samdXX.cfg` → `at91samd` |
| P0 | SAM E5/D5 (bounded) | ARM Cortex-M4 | SWD | `atsame5x.cfg` → `atsame5` |
| P0 | SAM3 (representative target only) | ARM Cortex-M3 | SWD/JTAG | `at91sam3ax_8x.cfg` → `at91sam3` |
| P0 | SAM4 (excluding SAM4L; representative target) | ARM Cortex-M4 | SWD/JTAG | `at91sam4sXX.cfg` → `at91sam4` |
| P0 | SAM4L (separate controller) | ARM Cortex-M4 | SWD/JTAG | `at91sam4lXX.cfg` → `at91sam4l` |
| P0 | SAM V7/E70/S70 | ARM Cortex-M7 | SWD/JTAG | `atsamv.cfg` → `atsamv` |
| P0 | SAM7 (legacy JTAG) | ARM7TDMI | JTAG | `at91sam7x256.cfg` → `at91sam7` |
| P0 | PIC32MX | MIPS M4K | JTAG | `pic32mx.cfg` → `pic32mx` |
| P0 | ATmega128 exact base name only | AVR 8-bit | JTAG | `atmega128.cfg` → `avr` |
| P1 | SAM L1x | ARM; exact model unresolved in this pass | SWD | `atsaml1x.cfg` target only; no direct Flash Bank |
| P1 | AVR32 | AVR32 AP7K | JTAG | `avr32.cfg` target only; no direct Flash Bank |

This is a **curated shortlist** based on bounded pinned-source checks. It is **not an unbiased survey** showing that ARM is the majority of supported Microchip ICPNs or of all OpenOCD devices. AVR32 is distinct from the 8-bit AVR architecture. A generic `at91samdXX.cfg` comment mentioning Cortex-M0 does not settle the exact Core for every member of SAM D/C/R/L0; exact device matching remains unresolved.

### Inference limits

- Shared CPU Core, SWD or JTAG transport **does not** imply common Flash memory controller, erasability, device ID or exact orderable variant compatibility.
- A Tcl `target create` is not a Flash programming plan.
- A `flash bank` plus implementation callbacks is **source-level capability evidence**, not a physical or complete software-programming qualification.
- P0/P1/P2 are Research priority labels; `UNKNOWN/CANDIDATE/SUPPORTED/UNSUPPORTED` are distinct software qualification statuses. P0 is not `SUPPORTED`.
- No physical test is required for **eventual Catalog display** when independent, version-pinned OpenOCD *software qualification* exists. HIL and installed backend runtime execution authorization remain separate, fail-closed.
- P2 = cheaply archived in this bounded pass. It does not prove permanent lack of OpenOCD support; revisit only when new driver evidence, demand or explicit owner reprioritization arises.

## Reproducible gate

The stdlib-only tool `microchip_openocd_core_first_v1.py` can validate the checked-in lock and runtime pin offline:

```bash
python -m unittest discover -s data/device-catalog/research -p 'test_microchip_openocd_core_first_v1.py' -v
python data/device-catalog/research/microchip_openocd_core_first_v1.py
```

With a checkout of upstream OpenOCD at **exactly** commit `9ea7f3d...`, it also independently computes and compares the Git blob SHA-1 of each target and C driver source, then checks direct Tcl Flash Bank declarations and driver operation callbacks:

```bash
python data/device-catalog/research/microchip_openocd_core_first_v1.py \
  --openocd-source-root /path/to/pinned-openocd-source
```

With the separately archived **original** vendor DFP `index.html` and `manifest.json` from the 2026-10-13 verified acquisition, the command additionally classifies DFP **support names** into bounded P0/P1 or cheap P2 archive:

```bash
python data/device-catalog/research/microchip_openocd_core_first_v1.py \
  --openocd-source-root /path/to/pinned-openocd-source \
  --dfp-evidence-root /path/to/original-dfp \
  --output /tmp/microchip-openocd-first-research-report.json
```

The live CI workflow checks source pinning and can attach a derived, **Research-only** JSON report. Absence of the immutable original DFP archive must not trigger a synthetic or estimated manufacturer coverage report.

## Next bounded step

Review **only** actual P0/P1 device names from immutable DFP evidence, with manufacturer device/revision and exact ordering-code crosswalk, and prove a pinned OpenOCD Driver supports the claimed Flash operations for each candidate device/profile. Distinguish SWD-only vs JTAG-only hardware fixture implications for later HIL, but **do not make physical Socket testing a prerequisite for Catalog software visibility**. P2 remains archived without exhaustive enrichment.

See [Issue #851](https://github.com/physicslu/plasma/issues/851) for acceptance and [Issue #849](https://github.com/physicslu/plasma/issues/849) for the separately gated public Catalog implementation.
