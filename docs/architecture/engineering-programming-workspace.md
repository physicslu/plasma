# Engineering Programming Workspace

## Purpose

`Engineering Mode -> Programming` is the canonical single-PPU engineering programming workspace.

The browser selects one target through:

```text
Facility -> PPU -> Site
```

and then uses the normal Erase / Program / Verify / Read job model. Production Mode and Engineering Mode continue to share the same canonical Facility / PPU / Site domain vocabulary.

## Provider boundary

Engineering target discovery and execution are server-owned. The browser does not create Facility, PPU, or Site topology.

```text
Engineering UI
    |
    v
Engineering PPU Control API
    |
    v
EngineeringPPUProvider
    |\
    | +--> MockEngineeringPPUProvider  (current)
    |
    +----> RealPPUProvider             (future)
```

The provider boundary owns:

- Facility / PPU catalog;
- selected PPU STATUS;
- E/P/V/R job submission;
- job status/progress;
- cancellation;
- Read output retrieval.

The browser contract does not depend on whether the selected PPU is mock or real. A future real-PPU provider should therefore replace or coexist with the Mock provider without requiring a second Programming UI or a second Site/job state model.

## Current server-side mock topology

The current `MockEngineeringPPUProvider` creates three Facilities. Each Facility contains four PPUs with heterogeneous Site counts:

```text
Mock Facility 01
├── Mock PPU 01 -> 2 Sites
├── Mock PPU 02 -> 4 Sites
├── Mock PPU 03 -> 6 Sites
└── Mock PPU 04 -> 8 Sites

Mock Facility 02
├── Mock PPU 01 -> 2 Sites
├── Mock PPU 02 -> 4 Sites
├── Mock PPU 03 -> 6 Sites
└── Mock PPU 04 -> 8 Sites

Mock Facility 03
├── Mock PPU 01 -> 2 Sites
├── Mock PPU 02 -> 4 Sites
├── Mock PPU 03 -> 6 Sites
└── Mock PPU 04 -> 8 Sites
```

The total simulated topology is:

```text
3 Facilities
12 PPUs
60 Sites
```

This topology exists in Python, not in React.

Canonical identity remains:

```text
(facility_id, ppu_id, site_id)
SITE 1 .. SITE N
```

There is no `SITE 0` and Sites are not flattened into a global integer namespace.

## Mock execution is a real Plasma software path

A Mock PPU is not a static Web fixture. Each mock PPU is a real `PlasmaServer` instance with its own canonical PPU configuration, `SiteManager`, `SiteWorker`, job registry, output directory and MockInterface instances.

Current execution path:

```text
Browser / Engineering Programming
    |
    | HTTP REST
    v
Plasma Web REST Gateway
    |
    | EngineeringPPUProvider selects (facility_id, ppu_id)
    v
MockEngineeringPPUProvider
    |
    | Plasma Protocol v3.2 / PLASMA32 over loopback TCP
    v
selected virtual PlasmaServer
    |
    v
SiteManager / SiteWorker
    |
    v
MockInterface
```

Therefore E/P/V/R, job state, progress, cancellation, Read output and per-Site independence exercise the normal Plasma software execution model. The only substituted layer is the PPU/hardware provider side.

A successful Mock PPU operation still does not prove Z2, FPGA I/O, socket, voltage, timing, or real IC programming.

## REST shape

Catalog:

```text
GET /api/engineering/targets
```

Selected PPU virtual API base:

```text
/api/engineering/targets/{facility_id}/{ppu_id}
```

The normal PPU Console contract is then preserved beneath that base:

```text
GET  .../api/status
GET  .../api/status?job={job_id}
POST .../api/jobs
POST .../api/jobs/{job_id}/cancel
GET  .../api/jobs/{job_id}/files/{filename}
```

The Web UI can therefore keep one programming interaction model while the Python provider selects the target implementation.

## Runtime enablement

The server-side Engineering Mock provider is opt-in. `plasma_web.gateway` supports:

```text
--engineering-mock
--engineering-mock-root <path>
```

A normal standalone PPU Gateway does not need to create 12 mock PPUs. Integration-host activation is a separate runtime/deployment setting.

## Manager boundary

Plasma Manager remains read-only in this phase. Engineering Mock write execution does not pass through Manager and does not weaken the existing Manager security boundary.

For real remote PPUs, the future `RealPPUProvider` must use an explicitly approved authenticated control path. The existence of the provider interface is not authorization to turn the current read-only Manager into a write proxy.

## Replacement principle for real PPUs

The intended transition is:

```text
Today:
EngineeringPPUProvider -> MockEngineeringPPUProvider -> virtual PlasmaServer -> MockInterface

Future:
EngineeringPPUProvider -> RealPPUProvider -> real PPU control endpoint -> real PlasmaServer -> hardware interface
```

The following must remain stable across that replacement:

- Facility / PPU / Site identity;
- one-based `site_id`;
- E/P/V/R operation semantics;
- `PROGRAM` means write only;
- Job state/progress/cancel semantics;
- Read output semantics;
- dynamic 2/4/6/8/N Site presentation.

## Validation expectations

Required validation includes:

- server catalog reports exactly 3 Facilities / 12 PPUs / 60 Sites for the current mock fixture;
- every Facility reports four PPUs with 2 / 4 / 6 / 8 Sites;
- every selected Mock PPU reports its own canonical STATUS through a real PlasmaServer runtime;
- a job submitted to one `(facility_id, ppu_id, site_id)` does not appear on another PPU;
- E/P/V/R submission routes to the selected target identity;
- Read output remains job- and PPU-scoped;
- Engineering browser selection comes from the Python catalog rather than hard-coded React topology;
- SITE 0 and Site N+1 are never exposed as canonical Sites;
- existing standalone PPU and Production Mode behavior remains unchanged when the Engineering provider is disabled.
