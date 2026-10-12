# Selected IC Profile v1

Status: Current read-only composition for the STM32F103C8T6 pilot.

## Purpose

The Selected IC Profile is the read-only composition shown after an admitted exact ICPN
is selected. It is not a new Product Mode and it is not an execution authorization
record.

The v1 information model is deliberately layered:

```text
Production Device Catalog
        |
        | exact admitted ICPN
        v
IC Support binding
        |
        +--> Manufacturer Device knowledge
        |       - identity characteristics
        |       - operating electrical characteristics
        |       - memory map
        |
        +--> Manufacturer Programming knowledge
        |       - interface/pins
        |       - manufacturer clock evidence
        |       - programming electrical conditions
        |       - Flash geometry
        |       - machine-readable programming semantics
        |
        +--> Programmer Backend
        |       - OpenOCD mapping/provider/runtime evidence
        |
        `--> PLASMA Compatibility / Qualification
                - Site electrical compatibility
                - Socket compatibility
                - hardware runtime readiness
                - physical programming qualification
```

## Ownership

### Production Device Catalog

Owns commercial identity admission:

- manufacturer;
- exact ICPN;
- family/series/base device;
- commercial package and pin count;
- catalog Flash-size projection;
- current production backend route.

Catalog admission does not prove electrical safety or physical programming support.

### Manufacturer Device Profile

Owns intrinsic IC characteristics:

- operating VDD and I/O supply characteristics;
- package/device characteristics;
- Flash/SRAM/system-memory map;
- main-Flash address range and page organization.

Absolute maximum ratings, when later added, must remain distinct from valid operating
ranges and must never become power setpoints.

### Manufacturer Programming Profile

Owns how the target is programmed:

- SWD/JTAG or other programming interface;
- programming pins and signaling constraints;
- manufacturer-stated min/max/recommended interface clock;
- programming VDD/VPP and power/reset conditions;
- erase/program geometry and alignment;
- unlock/erase/program/verify semantics;
- option/security constraints and destructive recovery behavior.

An interface clock value from OpenOCD or another programmer is not a manufacturer limit.
Missing manufacturer speed evidence remains explicit `unknown`.

### Programmer Backend

OpenOCD is implementation evidence, not device-specification authority. Backend defaults,
timeouts, RAM loaders, target-halt policy and board convenience overrides must not mutate
the manufacturer profile.

For the STM32F103C8T6 pilot:

- the exact manufacturer Flash capacity remains 64 KiB;
- the OpenOCD Blue Pill 128-KiB board override is not admitted into the Device Profile;
- OpenOCD's 1-MHz target configuration default does not populate manufacturer SWD/JTAG
  speed fields.

### PLASMA Compatibility / Qualification

Compatibility remains independent:

- `site_electrical_compatibility=not_evaluated`;
- `socket_compatibility=not_evaluated`;
- `hardware_runtime_ready=false`;
- `physical_programming_qualified=false`.

A compatible voltage range is not physical qualification. A mapped backend is not
physical qualification.

## API

`GET /api/devices/search` remains the stable route. Results may include an additive
`selected_profile` field.

For an exact ICPN with an admitted manufacturer profile, the projection includes:

```text
selected_profile
├── manufacturer_baseline
├── catalog_identity
├── device
│   ├── identity
│   ├── operating_electrical
│   └── memory_map
├── programming
│   ├── interfaces
│   ├── electrical
│   ├── flash_geometry
│   ├── flash_controller
│   ├── special_constraints
│   └── program_model
├── plasma_compatibility
└── ic_support
```

An admitted ICPN without manufacturer enrichment returns `selected_profile=null`; the
service does not invent family-derived values.

## UI

The IC Selector presents the selected ICPN in three primary sections:

1. **IC Information** — identity, operating electrical characteristics and memory map.
2. **Programming** — programming interface/electrical conditions/Flash geometry/flow.
3. **PLASMA Compatibility** — Site/Socket/hardware/physical readiness.

Backend build/provenance detail remains available under Advanced Backend / Evidence so
normal operator information hierarchy is not dominated by CI and runtime metadata.

## Safety invariants

- Missing required manufacturer operating or programming electrical data fails profile
  resolution closed.
- Exact ICPN Flash capacity must agree with the admitted catalog identity.
- Backend-derived speed/default values cannot fill manufacturer-unknown fields.
- Selected IC Profile is read-only and cannot enable DUT power or programming.
- No Mock/CI/software evidence may set hardware or physical qualification true.
