# Engineering Programming Workspace

## Purpose

`Engineering Mode -> Programming` is the canonical single-PPU engineering programming workspace.

The browser selects:

```text
Facility -> PPU -> Site
```

and executes Erase / Program / Verify / Read using the same canonical PPU/Site job model used elsewhere in Plasma.

## Provider boundary

Engineering target discovery and execution are server-owned. React does not invent Facility, PPU or Site topology.

```text
Engineering UI
    |
    | Web REST v3
    v
Plasma Web REST Gateway
    |
    v
EngineeringPPUProvider
    |\
    | +--> MockEngineeringPPUProvider  (current)
    |
    +----> RealPPUProvider             (future)
```

The Provider boundary owns:

- Facility / PPU catalog;
- selected PPU STATUS;
- Engineering connection-session lifecycle;
- Programming Asset cache validation/materialization;
- Asset -> Normalized Image conversion for Program/Verify;
- E/P/V/R Job submission;
- job status/progress and cancellation;
- Read output retrieval;
- target memory geometry required by canonical Read;
- PPU-wide shared-resource invariants.

## Current server-side Mock topology

Each of three Facilities contains four PPUs with heterogeneous Site counts:

```text
Facility 01/02/03
├── PPU 01 -> 2 Sites
├── PPU 02 -> 4 Sites
├── PPU 03 -> 6 Sites
└── PPU 04 -> 8 Sites
```

Total:

```text
3 Facilities
12 PPUs
60 Sites
```

Topology exists in Python, not React. Canonical identity is:

```text
(facility_id, ppu_id, site_id)
SITE 1 .. SITE N
```

There is no canonical SITE 0.

## Mock execution is a real Plasma software path

Each Mock PPU is a real `PlasmaServer` with its own PPU configuration, `SiteManager`, `SiteWorker`, job registry, output directory and MockInterface instances.

```text
Browser / Engineering Programming
    |
    | Web REST v3
    v
Plasma Web REST Gateway
    |
    | select facility_id / ppu_id
    v
MockEngineeringPPUProvider
    |
    | Plasma Protocol v3.3 / PLASMA33
    v
selected virtual PlasmaServer
    |
    v
SiteManager / SiteWorker
    |
    v
MockInterface
```

Therefore E/P/V/R, job state, progress, cancellation, Read output and per-Site independence exercise the normal Plasma software execution model. Passing this path does not prove Z2, FPGA I/O, socket, voltage, timing or real IC programming.

## Programming data model

Plasma deliberately separates source inputs from execution instructions and target-memory data.

```text
Programming Asset             source/input data
├── Image
├── Key
├── Option
├── Serial Number
└── Calibration

Programming Recipe            instructions telling the PPU what to do
                              separate control-plane concept, not an Asset

Image Asset
    |
    | parser / normalizer
    v
Normalized Image              data actually programmed to or verified
                              against target IC programmable memory
```

Asset semantics and file serialization are independent. Declared formats include binary, Intel HEX, S-Record, ELF, CSV, text, JSON and PEM.

Only `Image + binary` normalization is implemented today. The other types/formats exist in the domain model but are rejected at execution boundaries until a real parser/consumer is implemented and validated.

## Canonical Read semantics

The stable display code `R` means **Read Entire Main Flash**.

The operator does not enter an offset or length. The browser must not guess memory geometry and must not silently substitute a convenience default such as 256 bytes.

```text
Target IC / Device Support
        |
        v
Main Programmable Flash geometry
(base address + size)
        |
        v
READ complete Main Flash
        |
        v
Read output file
```

`Main Flash` is deliberately narrow. It means the normal programmable code/data Flash region supported by the selected target. It does **not** implicitly include:

- Option Bytes;
- OTP / one-time-programmable memory;
- EEPROM or separate Data Flash;
- Security, secure, protected or vendor-reserved regions;
- Configuration Words / fuses;
- any other special memory region.

Those regions require future explicit memory-region features and separate validation. They must never be silently folded into `R`.

Memory geometry is execution-provider / Device Support evidence, not presentation state. A real target implementation must resolve the Main Flash base and size before dispatch. If it cannot resolve that geometry with adequate evidence, Read must fail closed rather than perform a partial or guessed read.

For the current Mock Provider, Main Flash is the configured Mock flash (`flash_size_bytes`), so canonical Read resolves to address `0` and the complete configured size. The provider overrides any legacy compatibility range that may still arrive from an older client.

## Serial Number

`serial_number` is a first-class Programming Asset type and is not a security key.

A Serial Number represents per-device identity and may eventually come from MES, database, API, generated allocation, operator input or a file. It is normally assigned per device/Site.

It must not inherit PPU-wide Image sharing semantics merely because both are Programming Assets. Current Program/Verify does not consume a Serial Number Asset directly.

## Programming Asset session cache

Connect/Reconnect creates a logical Engineering `session_id`. Reconnect passes the previous session ID so its cache can be invalidated.

Cache scope:

```text
(connection session, facility_id, ppu_id)
```

Unlike the old single-image model, one session/PPU may hold multiple Assets simultaneously. This is required for future workflows such as:

```text
Image + Option + Key + Serial Number + Calibration
```

The Mock Provider stores materialized Asset data in process memory only.

Each Asset is identified by metadata including:

```text
asset_name
asset_type
asset_format
asset_size
asset_sha256
```

Program/Verify preparation for the current binary Image path is:

```text
first use
  -> fingerprint check
  -> cache miss
  -> upload Asset once
  -> normalize Asset to Image
  -> Site Jobs reference session_id + asset_sha256

same Asset again in same session/PPU
  -> fingerprint check
  -> cache hit
  -> no upload

additional Asset
  -> stored alongside existing Assets

Reconnect
  -> new session
  -> previous session cache invalidated
```

Concurrent Sites share one in-flight preparation/upload path. A 2/4/6/8-Site batch must not upload the same source Asset separately for every Site.

## PPU-wide active Normalized Image invariant

Asset cache identity and execution-resource identity are intentionally different.

```text
source Asset SHA
    |
    v
normalize
    |
    v
Normalized Image SHA
    |
    v
PPU-wide Program/Verify lease
```

The normalized Image SHA is the concurrency authority because it represents the target-memory data actually being programmed.

```text
PPU idle
  -> first Program/Verify Image SHA A acquires lease A

additional Site Program/Verify Image SHA A
  -> allowed concurrently

different Image SHA B while lease A active
  -> rejected as recoverable SITE_BUSY

all Image SHA A Program/Verify Jobs terminal
  -> lease released
```

A future parser may produce the same normalized Image from two different source files. Those files can have different Asset SHA values while still representing the same PPU execution resource.

Reconnect may invalidate a source-Asset cache while already accepted Jobs finish. Their normalized Image lease remains active until terminal state.

## Size-aware Mock timing model

Engineering Mock timing is designed to exercise progress, cancellation and concurrency rather than act as an instant UI animation.

```text
estimated_time = fixed_operation_overhead + bytes / throughput_bytes_per_second
```

Current profile:

| Operation | Size basis | Throughput | Fixed overhead | Example |
|---|---|---:|---:|---:|
| Erase | full 4 MiB mock flash | 2 MiB/s | 1.0 s | 3.0 s full-chip erase |
| Program | normalized Image bytes | 96 KiB/s | 4.0 s | 5.04 s for 100 KiB |
| Verify | normalized Image bytes | 192 KiB/s | 1.0 s | 1.52 s for 100 KiB |
| Read | complete Main Flash | 192 KiB/s | 1.0 s | ~22.3 s for 4 MiB |

Engineering Mock operation timeout is currently 90 seconds. These values are simulation parameters, not real PPU/IC performance specifications.

## REST shape

Canonical Web REST contract: [`web-rest-api-contract.md`](web-rest-api-contract.md).

Current contract:

```text
Web REST v3
Plasma Protocol v3.3 / PLASMA33
```

Catalog/session:

```text
GET  /api/engineering/targets
POST /api/engineering/session
```

Selected PPU base:

```text
/api/engineering/targets/{facility_id}/{ppu_id}
```

Programming Asset and PPU operations:

```text
POST .../api/programming-assets/check
POST .../api/programming-assets?session_id=...&name=...&type=...&format=...&sha256=...
GET  .../api/status
GET  .../api/status?job={job_id}
POST .../api/jobs
POST .../api/jobs/{job_id}/cancel
GET  .../api/jobs/{job_id}/files/{filename}
```

Engineering Program/Verify Job bodies reference `session_id + asset_sha256`; they do not carry source Asset bytes again.

Canonical Read intent is `main_flash`; concrete address/length are provider-resolved execution details. Legacy offset/length request fields may remain temporarily for compatibility, but they are not operator semantics and the canonical Mock Provider does not use them to narrow Read.

There is no legacy REST alias layer in the canonical development contract.

## Site execution invariants

- selected Sites execute independently unless a real shared resource requires synchronization;
- one Site does not wait for an unrelated Site pipeline;
- per-Site cancellation does not cancel unrelated Sites;
- batch cancellation controls batch classification without rewriting truthful underlying Job results;
- Program means write only;
- Read means the complete Main Programmable Flash and does not implicitly include special memory regions;
- a complete flow such as Erase -> Program -> Verify is composed explicitly;
- batch operation selection may contain any subset of Erase / Program / Verify / Read.

## Runtime enablement

The server-side Engineering Mock Provider is opt-in:

```text
--engineering-mock
--engineering-mock-root <path>
```

A standalone PPU Gateway does not need to instantiate the 12 Mock PPUs.

## Manager boundary

Plasma Manager remains optional and read-only in the current phase. Engineering Mock write execution does not pass through Manager.

A future `RealPPUProvider` must use an explicitly approved authenticated control path. The existence of the Provider abstraction does not authorize converting the current read-only Manager into an implicit write proxy.

## Real PPU replacement principle

The intended migration is:

```text
Engineering UI
    |
    v
same Web REST v3 contract
    |
    v
EngineeringPPUProvider
    |
    +-- MockEngineeringPPUProvider today
    |
    +-- RealPPUProvider later
            |
            v
        real remote/local PPU
```

The UI and domain model should not need another redesign when the hardware provider changes.
