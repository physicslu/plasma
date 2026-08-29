# Optional Plasma Manager Control Plane

## Status and scope

This document separates two different truths that must not be conflated:

1. **Current implementation:** Plasma Manager is optional and read-only.
2. **Approved production target:** the normal operator path is `Central Web Console -> Plasma Manager -> one or more PPUs`, including deployments with exactly one PPU.

The approved target topology is defined in [Production Operation Topology](production-operation-topology.md). It does not mean the current Manager already implements programming-command routing.

## Architectural invariant

A Plasma PPU is an autonomous execution node. Centralized management must not move deterministic Site execution, local safety, protocol timing, or recovery ownership out of the PPU.

The current dependency direction is one-way:

```text
Plasma Manager -> PPU
```

A PPU must never require a live Manager connection in order to start its local Plasma Server, expose its local Gateway, finish already accepted local work, recover a Site, or perform maintenance and diagnostics.

For the approved production target, Manager may become the normal northbound orchestration/routing boundary for new operator commands, but those commands must still enter the PPU through an explicit PPU contract. Manager must not bypass the PPU and call internal `SiteManager` or `SiteWorker` APIs.

## Deployment roles

Plasma distinguishes the **PPU role** from the **Management Host role**. The integration workstation may run both roles for development, but production Z2 deployment must not inherit that co-location as a requirement.

### PPU role — intended Z2 production direction

```text
Management Host / service client
        |
        v
PPU Plasma Web REST Gateway
        |
        v
Plasma Server
        |
        v
SiteManager / SiteWorker
        |
        v
PYNQ / FPGA PL / target IC
```

The intended embedded role contains the programming runtime and PYNQ/FPGA integration. The integration-host Vite development server, npm build toolchain, Plasma Manager and Fleet UI are **not** mandatory Z2 runtime dependencies.

Direct browser/CLI access to a PPU may remain available for engineering, commissioning, diagnostics, maintenance and recovery. It is a service capability, not a second canonical production workflow.

### Management Host role

Central Web Console and Plasma Manager are separate logical components but may run on the same physical host:

```text
Management Host / Operator PC
├── Central Web Console
└── Plasma Manager
      |
      +--> PPU A Gateway -> local execution
      +--> PPU B Gateway -> local execution
      +--> ...
```

They may later be split across hosts when availability, security or scale requires it. Co-location is a deployment choice, not a code-level requirement.

## Current implementation: read-only Manager

The currently implemented Manager remains an optional read-only registry and aggregation service. It observes configured PPUs but does not own command routing, central scheduling, discovery, authentication policy, audit persistence or PPU execution.

The current browser-facing fleet shape is:

```text
Browser
   |
   | HTTPS / same origin
   v
Fleet Web UI
   |
   | GET /api/fleet
   v
Fleet BFF
   |
   | loopback only
   v
Plasma Manager :18180
   |
   +--> PPU A Gateway -> local execution
   +--> PPU B Gateway -> local execution
   +--> ...
```

Manager and Fleet UI failure currently remove centralized visibility only. They do not enter the programming execution path.

## Approved production target

The canonical production operator topology is cardinality-independent:

```text
one PPU:
Central Web Console -> Plasma Manager -> PPU #1

many PPUs:
Central Web Console -> Plasma Manager
                       +-> PPU #1
                       +-> PPU #2
                       +-> PPU #N
```

A one-PPU installation is not a separate product mode. Adding PPUs expands managed inventory rather than changing operator workflow.

The target write/orchestration path remains future work. Before Manager may route programming commands, Plasma must define and validate authentication, authorization, auditability, replay/idempotency, failure semantics, recovery and the exact PPU northbound write contract.

No write capability is implied merely by this target topology.

## Engineering / service direct access

Direct access is retained for engineering and recovery:

```text
Engineer / service tool
        |
        +--> PPU Gateway
        +--> PPU CLI / diagnostics
```

Typical uses include commissioning, diagnostics, recovery and fault isolation when the management control plane is unavailable.

This direct path must not evolve into a second independent production UI, a second configuration authority, or an ungoverned fallback that silently bypasses Manager policy.

## Browser-facing BFF boundary

The current browser must not call the Manager's internal listener directly. Manager remains loopback-only on a co-located Management Host. The Web application exposes a narrow same-origin read-only BFF endpoint:

```text
Browser GET /api/fleet
    -> Web BFF
    -> http://127.0.0.1:18180/api/fleet
```

The current BFF accepts GET only, requires a loopback Manager source, and returns a sanitized browser-facing contract. It intentionally does not expose:

- configured PPU endpoint URLs or IP addresses;
- raw Manager exception/error strings;
- Manager filesystem paths;
- POST/PUT/PATCH/DELETE command routing;
- programming operations.

The browser-facing fleet payload contains operational identity/state only: Facility/PPU identity, transport/execution state, current/stale/unknown observation state, current capacity, last-known topology and non-sensitive Manager cache/persistence health.

This creates an explicit security boundary:

```text
PUBLIC / USER SIDE
Browser -> Fleet UI -> BFF

INTERNAL CONTROL PLANE
Manager -> registry -> PPU internal endpoints -> observation store
```

Moving Manager to a separate management server in a later phase will require an authenticated service-to-service connection. The current loopback design must not be generalized into an unauthenticated remote Manager API.

## Fleet UI opt-in in the current release

Fleet Web is currently optional. The BFF defaults disabled unless the management-host runtime explicitly enables it. This remains an implementation fact even though the approved production target makes Central Web Console + Manager the normal operator topology.

The public demo entry exposes two product views:

```text
/       -> demo selector
/ppu    -> original single-PPU demo/current direct path
/fleet  -> read-only Manager/Fleet demo
```

These routes describe the current prototype and demo packaging; they are not a requirement to preserve two independent production operating modes.

## PPU northbound contract

The PPU exposes a small Manager-friendly contract through the existing Plasma Web REST Gateway. These endpoints are additive and remain useful for direct service diagnostics.

### `GET /api/health/live`

Reports whether the REST Gateway process itself is alive. This endpoint deliberately does not contact the local Plasma Server.

### `GET /api/health/ready`

Checks whether the Gateway can reach the local Plasma Server and obtain canonical PPU identity. A live Gateway may return HTTP 503 when local execution is unavailable.

### `GET /api/node`

Returns the stable fleet-facing node descriptor. The current contract includes `manager_required = false`, canonical PPU identity and relative links.

Future production command routing must extend the PPU northbound contract deliberately; it must not be implemented by bypassing the Gateway/Server boundary.

## What is intentionally not implemented

The current Manager/Fleet slice does not add Manager registration, mDNS discovery, authentication/authorization, remote Programming Image rollout, central audit storage, fleet scheduling, job routing, PPU restart controls or programming commands.

In particular, a future Manager write path must not be created merely by adding buttons to Fleet UI. Authentication, authorization, auditability, replay/idempotency and failure semantics must be defined first.

## Failure-domain rule

The design target is explicit fault containment:

```text
Manager / Central Web Console failure
    -> new centrally initiated operator actions may be unavailable
    -> already accepted PPU execution remains locally owned
    -> PPU safety/recovery remains local

Gateway failure on one PPU
    -> that PPU loses northbound REST access
    -> other PPUs remain independent

Plasma Server failure on one PPU
    -> readiness for that PPU fails
    -> Gateway liveness can still distinguish the failure
    -> other PPUs remain independent
```

This separation is required for production equipment. A centralized control plane may own operator workflow and future orchestration, but it must not become part of the deterministic local execution loop.

## Capacity validation on Z2

Fleet/UI code is not the primary embedded performance risk. Z2 acceptance must instead measure programming workload under 1/2/4/8 concurrent Sites, including CPU, RAM, PS/PL transfer, filesystem/network I/O, throughput and soak stability. Management polling and browser connectivity must be shown not to materially degrade programming behavior before production claims are made.
