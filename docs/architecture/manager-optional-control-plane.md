# Optional Plasma Manager Control Plane

## Status

This document distinguishes **current implementation** from the **approved managed-routing target**.

The canonical vocabulary and target routing ownership are defined in [Control Plane Routing Architecture](control-plane-routing-architecture.md).

## Architectural invariant: PPU autonomy

A Plasma PPU is a complete autonomous execution node. Plasma Manager is optional to the PPU itself and MUST NOT become a runtime prerequisite for local programming.

The dependency direction remains one-way:

```text
Plasma Manager -> PPU
```

A PPU must never require a live Manager connection in order to start its local Plasma Server, expose its local maintenance/programming boundary, execute an already accepted Job, recover a Site, or perform local maintenance and diagnostics.

This invariant does **not** mean that a centrally managed Console should bypass Manager. The approved target distinguishes two operating modes:

```text
Standalone Mode
local client -> PPU Gateway -> Plasma Server -> local execution

Managed Mode
Control Console -> BFF -> Manager -> selected PPU Gateway -> Plasma Server -> local execution
```

Manager is therefore optional for PPU autonomy but authoritative for **centrally managed routing** when Managed Mode is used.

## Deployment roles

Plasma distinguishes the **PPU role** from the **Management Host role**. The integration workstation may run both roles for development, but production Z2 deployment must not inherit that co-location as a requirement.

### PPU role — intended Z2 production direction

```text
PPU / Z2
├── PPU Gateway
├── Plasma Server
├── PS runtime
├── PL / FPGA
└── Sites / target ICs
```

The PPU role owns programming execution, PYNQ/FPGA integration and local Site behavior. The integration-host Vite development server, npm build toolchain and Plasma Manager are not mandatory Z2 runtime dependencies.

A production PPU Web artifact, if used for a local Console, should be built off-target and served without requiring the Z2 to perform frontend compilation. Exact production serving mechanics remain a later Z2 deployment task and require target validation before being claimed complete.

### Management Host role

The Management Host may be a Mac, industrial PC, mini PC, VM or factory server.

Approved target:

```text
Management Host
├── Control Console
├── BFF
└── Plasma Manager
       |
       +--> PPU A Gateway -> local execution
       +--> PPU B Gateway -> local execution
       +--> ...
```

The Management Host owns centralized visibility and managed PPU routing. It does not own FPGA / IC execution.

## Mode A: standalone PPU

No Manager, central PC, registration service, heartbeat service, external scheduler or Fleet UI is required for local PPU capability.

```text
Local client / local PPU Console
        |
        v
PPU Gateway
        |
        v
Plasma Server
        |
        v
SITE 1 .. SITE N
```

This remains the fault-containment baseline and local-recovery path.

## Mode B: managed fleet

### Current implementation

Today Manager provides read-only registry / fleet aggregation plus a narrowly allowlisted PS Loopback pass-through. General Programming Job / Batch / Programming Asset write routing is not implemented through Manager yet.

Current Manager behavior therefore remains intentionally limited and must not be described as a completed general command router.

### Approved target

Managed Console operations use one routing owner:

```text
Control Console
      |
      v
BFF
      |
      v
Plasma Manager
      |
      | resolve canonical ppu_alias / ppu_id
      v
Target PPU Gateway
      |
      v
Plasma Server
      |
      v
local execution
```

Programming and Loopback diagnostics must share this managed prefix. The Console must not use a target PPU URL as the managed routing source of truth.

The target write path must be implemented as explicit domain APIs. Manager must not become a generic arbitrary-URL reverse proxy.

## Browser-facing BFF boundary

BFF means **Backend for Frontend** and is the presentation boundary serving the Control Console.

Its role is to provide same-origin browser APIs, hide internal Manager listener details, shape UI requests, enforce browser-facing validation/session boundaries and sanitize errors.

It does **not** own fleet routing.

Current fleet read path is conceptually:

```text
Browser GET /api/fleet
    -> Web BFF
    -> Manager
```

The approved managed write direction extends this same ownership model with explicit APIs rather than exposing Manager internals or arbitrary PPU endpoint URLs directly to the browser.

## Plasma Manager boundary

Manager owns fleet identity and managed routing:

```text
ppu-a -> configured PPU A Gateway
ppu-b -> configured PPU B Gateway
```

A managed caller supplies canonical identity / alias; Manager resolves it through its registry.

Manager must not accept caller-controlled destination URLs for production command forwarding. Authentication, authorization, auditability, replay/idempotency, timeout and failure semantics must be defined on explicit write contracts before each command family becomes production-capable.

## PPU Gateway boundary

The PPU Gateway is the northbound network boundary of one Programmer.

Target Z2 placement:

```text
Z2 / PPU
├── PPU Gateway
├── Plasma Server
├── PS
├── PL
└── IC
```

It accepts requests for this PPU, validates the local REST contract, translates to local Plasma runtime behavior and reports local status/errors. It must not decide which PPU in the fleet should receive a request.

## PPU northbound contract

The PPU exposes Manager-friendly endpoints through the existing Plasma Web REST Gateway.

### `GET /api/health/live`

Reports whether the REST Gateway process itself is alive. This endpoint deliberately does not contact the local Plasma Server.

### `GET /api/health/ready`

Checks whether the Gateway can reach the local Plasma Server and obtain canonical PPU identity. A live Gateway may return HTTP 503 when local execution is unavailable.

### `GET /api/node`

Returns the stable fleet-facing node descriptor. The same PPU can therefore be addressed through its local standalone boundary or selected through Manager in Managed Mode.

Programming write routes remain implementation work and must follow the contracts in [Control Plane Routing Architecture](control-plane-routing-architecture.md) and the applicable security design.

## Programming Asset / Image direction

For the first Managed Mode Programming implementation, Programming Asset / Image traffic is planned to follow the same routing ownership:

```text
Control Console
 -> BFF
 -> Manager
 -> selected PPU Gateway
 -> PPU Asset Service / Cache
```

This is a deliberate Phase-1 simplicity decision: establish one trustworthy production routing source before optimizing the binary data plane.

A direct-to-PPU Image data path may be introduced later only if measured throughput, concurrency, latency or reliability evidence justifies it and the replacement preserves identity binding, authorization, integrity and diagnostic coverage.

## Failure-domain rule

Centralized routing must not turn Manager into an execution dependency for an accepted PPU Job.

Approved target behavior:

```text
Manager / BFF unavailable
    -> no new centrally managed command can be routed
    -> already accepted PPU Jobs continue locally
    -> local PPU execution / maintenance remains possible

Gateway failure on one PPU
    -> that PPU loses managed REST access
    -> other PPUs remain independent

Plasma Server failure on one PPU
    -> readiness for that PPU fails
    -> other PPUs remain independent
```

This is the distinction between **control-plane availability** and **execution-plane autonomy**.

## Security boundary

The current loopback-only Manager relay must not be generalized by simply proxying arbitrary HTTP methods or URLs.

Future managed write APIs require explicit decisions for:

- authentication and authorization;
- PPU identity binding;
- auditability;
- replay and idempotency;
- timeout / retry semantics;
- cancellation ownership;
- Programming Asset integrity;
- failure recovery.

See [Remote Write Security Boundary](remote-write-security-boundary.md) for the security-specific constraints.

## Current versus target capability

| Capability | Current | Approved target |
|---|---|---|
| PPU local autonomy | Implemented architectural property | Preserve |
| Manager fleet observation | Read-only | Preserve |
| Manager PS Loopback relay | Narrow allowlist | Preserve as part of shared managed route |
| Managed Programming Job routing | Not implemented | BFF -> Manager -> selected PPU Gateway |
| Managed Programming Asset relay | Not implemented | Manager-mediated Phase 1 |
| Manager as arbitrary reverse proxy | Not implemented | Prohibited |

The approved target is a design contract, not evidence that the write-path implementation already exists.

## Capacity validation on Z2

Fleet/UI code is not the primary embedded performance risk. Z2 acceptance must measure programming workload under 1/2/4/8 concurrent Sites, including CPU, RAM, PS/PL transfer, filesystem/network I/O, throughput and soak stability.

When Manager-mediated Programming Asset transfer is implemented, Manager and network measurements must also demonstrate that centralized relay does not materially degrade command responsiveness or programming throughput at the intended fleet scale. Optimization should follow measured evidence rather than speculation.
