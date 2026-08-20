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
- Engineering connection-session lifecycle;
- PPU-scoped firmware cache validation;
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

## Size-aware Mock timing model

Engineering Mock operations must take long enough to exercise progress polling, cancellation and multi-Site concurrency realistically. The timing model is therefore not an instant/fixed-delay UI animation.

For a configured operation throughput, Mock execution time is modeled as:

```text
estimated_time = fixed_operation_overhead + bytes / throughput_bytes_per_second
```

The current Engineering Mock profile is intentionally conservative and configurable in Python:

| Operation | Size basis | Throughput | Fixed overhead | Approx. 100 KiB |
|---|---|---:|---:|---:|
| Erase | full 4 MiB mock flash | 2 MiB/s | 1.0 s | 3.0 s full-chip erase |
| Program | firmware bytes | 96 KiB/s | 4.0 s | 5.04 s |
| Verify | firmware bytes | 192 KiB/s | 1.0 s | 1.52 s |
| Read | requested read bytes | 192 KiB/s | 1.0 s | 1.52 s for 100 KiB |

The Program profile intentionally keeps a 100 KiB job above five seconds so an operator has a practical manual cancellation window while the duration still increases with firmware size.

Erase is deliberately not modeled from firmware file size. The current interface is a full-chip erase, so its physical work basis is target flash size. Program, Verify and Read scale from the actual requested byte count.

These values are a simulation profile, not a benchmark or specification for a real PPU or IC. When real target data is available, the profile can be calibrated without changing the Engineering UI, Job model or Provider boundary.

The generic `MockInterface` remains backward compatible: explicit per-operation `delays` override the throughput model, and deployments/tests that do not configure throughput keep the historical `default_delay_s` behavior.

The Engineering catalog reports its `timing_profile` so diagnostics can identify the active simulation model from the server rather than infer it from Web behavior.

Engineering Mock operation timeout is currently 90 seconds and is owned by the Provider/PPU profile. The browser does not impose its former 30-second Job timeout on Engineering targets. This is required for the current 4 MiB Program simulation, which is approximately 46.7 seconds.

## Engineering connection session and firmware cache

A PPU programs one firmware image across its Sites. The browser must not upload the same image separately for every Site.

Engineering therefore uses a logical connection session. A Connect/Reconnect creates a new `session_id`. When reconnecting, the browser passes its previous session ID and the Provider invalidates that previous session's firmware cache.

The cache scope is:

```text
(connection session, facility_id, ppu_id)
```

The Mock provider keeps the cached firmware bytes in process memory only. It does not write cached firmware into the Engineering state directory.

Within one session, one PPU holds at most one cached firmware image. The browser identifies a file using:

```text
filename
size
SHA-256
```

Program/Verify firmware preparation is:

```text
First use after Connect/Reconnect
    |
    v
send fingerprint only
    |
    v
Server cache miss
    |
    v
upload binary exactly once
    |
    v
Program/Verify Site Jobs send session_id + SHA-256 only

Same file again in the same session and PPU
    |
    v
send fingerprint only
    |
    v
Server cache hit
    |
    v
no binary upload

File changes
    |
    v
SHA-256 changes
    |
    v
cache miss -> upload replacement image

Reconnect
    |
    v
new session; previous session cache invalidated
    |
    v
same file is a miss -> upload again on first Program/Verify
```

Concurrent Sites share one in-flight fingerprint check/upload. A 2/4/6/8-Site Program batch therefore uploads the image once to the selected PPU, not once per Site.

The server validates the SHA-256 of uploaded bytes before admitting them to the cache. A claimed fingerprint that does not match the binary is rejected.

### PPU-wide active firmware invariant

Session caches are not the final concurrency authority. Multiple browser sessions can exist, but one physical PPU must never execute Program/Verify Jobs for two different firmware images at the same time.

The Provider therefore owns a PPU-wide active firmware lease:

```text
PPU idle
  -> first Program/Verify SHA A acquires lease A

additional Site Program/Verify SHA A
  -> allowed concurrently

any session requests Program/Verify SHA B while lease A is active
  -> rejected as recoverable SITE_BUSY

all SHA A Program/Verify Jobs terminal
  -> lease released
  -> SHA B may start
```

This is enforced server-side. The Web firmware selector is also locked while target Jobs are active, but UI locking is only an operator guard and is not the authority boundary.

A reconnect may invalidate the old session cache while previously accepted Jobs are still finishing. Their active PPU firmware lease remains until those Jobs become terminal, so reconnecting cannot be used to switch the PPU to another firmware image mid-operation.

## REST shape

Catalog and connection session:

```text
GET  /api/engineering/targets
POST /api/engineering/session
```

Selected PPU virtual API base:

```text
/api/engineering/targets/{facility_id}/{ppu_id}
```

Firmware cache and normal PPU operations beneath that base:

```text
POST .../api/firmware/check
POST .../api/firmware?session_id=...&name=...&sha256=...
GET  .../api/status
GET  .../api/status?job={job_id}
POST .../api/jobs
POST .../api/jobs/{job_id}/cancel
GET  .../api/jobs/{job_id}/files/{filename}
```

`/api/firmware/check` contains the file fingerprint only. The binary upload endpoint accepts `application/octet-stream`. Engineering Program/Verify Job submission contains the session and firmware fingerprint reference rather than Base64 firmware bytes.

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
- one active firmware image per PPU across concurrent Program/Verify Jobs;
- connection-session firmware cache semantics;
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
- Mock timing scales with Program / Verify / Read byte count and uses full target flash size for Erase;
- a 100 KiB Program is at least five seconds and has a practical cancellation window; cancellation reaches the normal terminal `cancelled` Job state;
- a same-URL Connect creates a new session and restarts catalog plus selected-PPU STATUS polling so Facility / PPU / Site controls recover;
- first firmware use after Connect is a fingerprint miss followed by exactly one binary upload for all concurrent Sites;
- a second same-file burn in the same session sends a fingerprint probe but no binary upload;
- changing the file causes a cache miss and replacement upload;
- reconnect invalidates the prior session cache so the first burn uploads again;
- uploaded bytes must match the claimed SHA-256;
- cached firmware remains memory-only;
- concurrent Sites using the same firmware SHA are allowed on one PPU;
- a different firmware SHA from the same or another session is rejected while the PPU firmware lease is active, and becomes admissible after all prior Program/Verify Jobs are terminal;
- the real Mock CD browser stack exercises a 1 MiB two-Site Program through Browser -> Gateway -> Provider -> PlasmaServer and verifies upload/reuse/reconnect request counts without API mocking;
- Read output remains job- and PPU-scoped;
- Engineering browser selection comes from the Python catalog rather than hard-coded React topology;
- SITE 0 and Site N+1 are never exposed as canonical Sites;
- existing standalone PPU and Production Mode behavior remains unchanged when the Engineering provider is disabled.
