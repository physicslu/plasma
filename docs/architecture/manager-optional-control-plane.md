# Optional Plasma Manager Control Plane

## Architectural invariant

A Plasma PPU is a complete autonomous execution node. Plasma Manager is an optional fleet control plane and MUST NOT become a runtime prerequisite for local programming.

The dependency direction is one-way:

```text
Plasma Manager -> PPU
```

A PPU must never require a live Manager connection in order to start its local Plasma Server, expose its local PPU Console, execute jobs, recover a Site, or perform maintenance and diagnostics.

## Deployment roles

Plasma distinguishes the **PPU role** from the **Management Host role**. The integration workstation may run both roles for development, but production Z2 deployment must not inherit that co-location as a requirement.

### PPU role — intended Z2 production direction

```text
Browser / local client
        |
        v
PPU-local Console
        |
        v
Plasma Web REST Gateway
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

The intended embedded role contains the programming runtime, PYNQ/FPGA integration and a production Web artifact for the local PPU Console. The integration-host Vite development server, npm build toolchain, Plasma Manager, Fleet BFF and Fleet UI are **not** mandatory Z2 runtime dependencies.

A production PPU Web artifact should be built off-target and served without requiring the Z2 to perform frontend compilation. Exact production serving mechanics remain a later Z2 deployment task and require target validation before being claimed complete.

### Management Host role

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

The Management Host may be an integration workstation during development and may later be a separate industrial PC, mini PC, VM or factory server. It is not required to be a Z2.

## Mode A: standalone PPU

No Manager, central PC, registration service, heartbeat service, external scheduler or Fleet UI is required.

```text
Browser
   -> PPU Console
   -> PPU Gateway
   -> Plasma Server
   -> SITE 1 .. SITE N
```

This mode remains the minimum viable product path and the failure-containment baseline.

## Mode B: managed fleet

The Fleet UI is an optional read-only view above independently operating PPUs.

```text
Browser / Fleet UI
        |
        v
Fleet BFF
        |
        v
Plasma Manager
        |
   +----+--------------------+
   |                         |
   v                         v
PPU A                       PPU B
   |                         |
local REST API             local REST API
   |                         |
local execution            local execution
```

Manager and Fleet UI failure remove centralized visibility only. They do not enter the programming execution path.

## Browser-facing BFF boundary

The browser must not call the Manager's internal listener directly. Manager remains loopback-only on a co-located Management Host. The Web application exposes a narrow same-origin read-only BFF endpoint:

```text
Browser GET /api/fleet
    -> Web BFF
    -> http://127.0.0.1:18180/api/fleet
```

The BFF accepts GET only, requires a loopback Manager source, and returns a sanitized browser-facing contract. It intentionally does not expose:

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

## Fleet UI opt-in

Fleet Web is optional. The BFF defaults disabled unless the management-host runtime explicitly enables it. A standalone PPU therefore does not gain a Manager dependency merely because Fleet UI code exists in the repository.

The public demo entry exposes two product views:

```text
/       -> demo selector
/ppu    -> original single-PPU demo
/fleet  -> read-only Manager/Fleet demo
```

The Fleet page may exist while its data source is disabled; in that state it reports that Fleet is opt-in and does not affect `/ppu` local programming.

## PPU northbound contract

The PPU exposes a small Manager-friendly contract through the existing Plasma Web REST Gateway. These endpoints are additive; existing standalone endpoints remain unchanged.

### `GET /api/health/live`

Reports whether the REST Gateway process itself is alive. This endpoint deliberately does not contact the local Plasma Server.

### `GET /api/health/ready`

Checks whether the Gateway can reach the local Plasma Server and obtain canonical PPU identity. A live Gateway may return HTTP 503 when local execution is unavailable.

### `GET /api/node`

Returns the stable fleet-facing node descriptor. The contract includes `manager_required = false`, canonical PPU identity and relative links. The same PPU therefore works when addressed directly in standalone mode or observed by Manager.

## What is intentionally not implemented

The current fleet Web slice does not add Manager registration, mDNS discovery, authentication/authorization, remote Programming Image rollout, central audit storage, fleet scheduling, job routing, PPU restart controls or programming commands. Those capabilities require separate architecture/security decisions.

In particular, a future Manager write path must not be created merely by adding buttons to Fleet UI. Authentication, authorization, auditability, replay/idempotency and failure semantics must be defined first.

## Failure-domain rule

The design target is explicit fault containment:

```text
Manager / Fleet BFF failure
    -> fleet UI unavailable
    -> local PPU execution remains available

Gateway failure on one PPU
    -> that PPU loses REST access
    -> other PPUs remain independent

Plasma Server failure on one PPU
    -> readiness for that PPU fails
    -> Gateway liveness can still distinguish the failure
    -> other PPUs remain independent
```

This separation is required for production equipment. A centralized control plane may improve observability and orchestration, but it must not create a new single point of failure for programming execution.

## Capacity validation on Z2

Fleet/UI code is not the primary embedded performance risk. Z2 acceptance must instead measure programming workload under 1/2/4/8 concurrent Sites, including CPU, RAM, PS/PL transfer, filesystem/network I/O, throughput and soak stability. Management polling and browser connectivity must be shown not to materially degrade programming behavior before production claims are made.
