# Control Plane Routing Architecture

## Status

**Current software architecture contract.**

Managed Mode now uses one production routing owner for Programming and diagnostics:

```text
Control Console
      |
      v
BFF
      |
      v
Plasma Manager
      |
      v
PPU Gateway @ selected PPU
      |
      v
Plasma Server
```

The implementation is software/CI validated. Integration-host runtime acceptance is a separate evidence layer; Z2, PS <-> PL, FPGA, electrical and real-IC behavior remain unproven until their own acceptance is executed.

Standalone PPU operation remains a separate supported mode and does not require Manager.

## First-principles boundary

Plasma assigns three different questions to three different components:

```text
How does the UI call backend services safely?
        -> BFF

Which PPU should receive this command?
        -> Plasma Manager

How does this PPU expose its local execution service?
        -> PPU Gateway
```

These responsibilities must not collapse into a browser-selected target URL or an arbitrary Manager reverse proxy.

## Canonical vocabulary and ownership

| Term | Canonical role | Owns | Must not own |
|---|---|---|---|
| **Control Console** | Operator-facing product UI | User intent, presentation, workflow state | PPU network topology or direct managed-device routing policy |
| **BFF — Backend for Frontend** | Presentation Boundary | Same-origin browser API, request shaping, browser security/session boundary, sanitized errors | Fleet routing, arbitrary destination URLs, device execution |
| **Plasma Manager** | Fleet / Routing Ownership | PPU registry, canonical identity, managed PPU selection, explicit command routing | FPGA/IC execution, caller-controlled generic proxying |
| **PPU Gateway** | Device Network Boundary | One PPU's REST boundary, local request validation, REST-to-runtime translation, local status/errors | Fleet-wide PPU selection |
| **Plasma Server** | PPU Execution Service | Local Job/Batch/diagnostic dispatch, Site execution, Protocol v3.3 runtime | Fleet routing or browser presentation |
| **PS** | Embedded Linux processing system | Local control/runtime and PS-side hardware integration | Fleet ownership |
| **PL** | FPGA programmable logic | Deterministic/custom hardware peripheral behavior | Control-plane policy |
| **Site** | Independent programming position | One target execution path and local Site state | Fleet identity |
| **IC** | Physical target device | Actual target programmable state | Control-plane routing |
| **Programming Asset** | Source data supplied to programming | Source bytes, metadata and source identity | PPU selection |
| **Programming Image / Image** | Programming data used to build target-memory execution data | Image content identity | Fleet routing |
| **Programming Job** | One requested Site operation | Operation intent, Site and execution references | PPU discovery |
| **Control Plane** | Central intent/routing layer | Identity, selection, policy and routing | Direct hardware execution |
| **Execution Plane** | Per-PPU runtime | Job/Batch/diagnostics and PS/PL/Site/IC execution | Global fleet routing |

## BFF — Backend for Frontend

BFF exists for the Control Console. It provides same-origin APIs and hides the local Manager listener from the browser.

Current Managed Mode browser base is conceptually:

```text
/api/manager/ppu
```

The BFF:

- resolves only the configured Manager and configured PPU alias;
- forwards only intentional request headers needed by the PPU contract;
- preserves `Authorization` and `Idempotency-Key` for the PPU security boundary;
- supports bounded Programming Asset/Image bodies;
- preserves binary responses such as readback data;
- never accepts a caller-controlled PPU host or arbitrary destination URL.

BFF does not decide which fleet endpoint an alias means. That mapping belongs to Manager.

## Plasma Manager

Manager is the Managed Mode routing source of truth:

```text
ppu-a -> configured PPU A Gateway
ppu-b -> configured PPU B Gateway
ppu-c -> configured PPU C Gateway
```

The browser identifies the configured managed PPU by alias/identity. Manager resolves that alias from its registry and forwards only explicitly allowlisted Plasma domain routes.

Manager therefore answers:

> Which Programmer should receive this managed request?

Manager does not execute FPGA or IC operations and is not a generic HTTP proxy. Unsupported route/method combinations fail closed.

Current relay families cover the Managed Mode production needs for:

- PPU liveness/readiness/node/status;
- Engineering session and target catalog;
- Programming Asset cache check/upload;
- Job submit/status/cancel/readback;
- Batch create/status/cancel and target cancellation;
- Gateway communication-policy reads needed by runtime observation;
- authenticated Principal introspection;
- PS real-path Loopback.

The allowlist is intentionally narrower than the PPU Gateway's complete local API surface.

## PPU Gateway

Each physical PPU owns its own Gateway. In the target Z2 product:

```text
PPU / Z2
├── PPU Gateway
├── Plasma Server
├── PS runtime
├── PL / FPGA
└── Sites / target ICs
```

The Gateway answers:

> What request is this Programmer being asked to execute, and how is it translated to the local runtime?

It knows one PPU. It does not know which other PPUs exist and does not own fleet selection.

The PPU secure Gateway remains the execution authorization authority. Manager/BFF preserve the browser's authorization and idempotency evidence; they do not replace the PPU's Principal/permission/scope/replay checks.

## Deployment modes

### Managed Mode

Typical Management Host:

```text
Mac / industrial PC / server / VM
├── Control Console
├── BFF
└── Plasma Manager
       |
       | network
       v
PPU / Z2
├── PPU Gateway
├── Plasma Server
├── PS
├── PL
└── IC
```

When Manager routing is configured, the shared Workspace API base is the same-origin managed BFF path. PMode, EMode and Loopback therefore use the same routing ownership.

Manager failure in Managed Mode is fail-closed. The Console must not silently switch to a stored direct PPU URL.

### Standalone Mode

A PPU remains autonomous:

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
PS -> PL -> Site -> IC
```

Standalone Mode may explicitly use a direct Gateway API base. This is a distinct operating mode, not an automatic Managed Mode fallback.

## Programming route

Managed Programming uses:

```text
Control Console
      |
      v
BFF
      |
      v
Plasma Manager
      |  resolve configured ppu_alias
      v
PPU Gateway
      |
      v
Plasma Server
      |
      v
Programming Job / Batch Runtime
      |
      v
SiteManager / SiteWorker
      |
      v
PS / local Interface
      |
      v
PL / FPGA
      |
      v
Site electrical / protocol path
      |
      v
Target IC
```

PMode and EMode share the same Workspace API base. Managed routing no longer uses a target PPU URL as the browser source of truth.

## Programming Asset / Image route — Phase 1

Programming Asset/Image bytes intentionally use the same managed routing ownership:

```text
Control Console
      |
      | binary Programming Asset / Image
      v
BFF
      |
      v
Plasma Manager
      |
      v
PPU Gateway
      |
      v
PPU Asset Service / Cache
      |
      v
Programming Runtime
```

The implementation preserves binary content instead of converting the transfer to a Manager-specific Base64 protocol. Both BFF and Manager impose bounded request/response sizes.

Integrity/provenance remains defined by the production Asset contract:

```text
Browser-computed source SHA-256
        =
PPU Programming Asset cache identity
        =
Job-referenced asset_sha256
```

For normalized Images, source Asset SHA and Normalized Image SHA remain distinct identities as defined by the Programming data model.

A direct-to-PPU Image data plane is not part of this phase. It may be introduced only if measured fleet throughput, latency, concurrency or reliability demonstrates that Manager relay is a material bottleneck, and only if identity binding, authorization, integrity and diagnostic coverage remain intact.

## Loopback route

Loopback is a production-boundary diagnostic, not a parallel transport.

Managed PS Loopback uses the same Workspace base and same BFF/Manager relay as Programming:

```text
Control Console
 -> BFF
 -> Manager
 -> PPU Gateway
 -> Plasma Server
      |
      v
    PS diagnostic handler
      |
      v
    return through the same route
```

Programming and Loopback may diverge only after the target Plasma Server receives the request.

### Loopback selected

```text
Plasma Server
    |
    v
Diagnostic Dispatcher
    |
    +--> PS endpoint  -> echo / validate at PS
    +--> PL endpoint  -> PS -> PL -> return        [not implemented]
    +--> IC endpoint  -> PS -> PL -> IC -> return  [not implemented]
```

### Normal Programming selected

```text
Plasma Server
    |
    v
Programming Job / Batch Runtime
    |
    v
SiteManager / SiteWorker
    |
    v
PS -> PL -> Site -> IC
```

Unsupported PL/IC Loopback remains fail-closed and must never fall back to Mock or a shallower endpoint.

## Diagnostic evidence model

A PASS claim stops at the deepest real endpoint traversed:

```text
PS Loopback PASS
Console -> BFF -> Manager -> PPU Gateway -> Server -> PS

PL Loopback PASS
Console -> BFF -> Manager -> PPU Gateway -> Server -> PS -> PL

IC Loopback PASS
Console -> BFF -> Manager -> PPU Gateway -> Server -> PS -> PL -> IC
```

Therefore:

```text
PS PASS + PL FAIL
=> investigate PS <-> PL / PL endpoint

PL PASS + IC FAIL
=> investigate PL <-> Site / IC boundary
```

PS Loopback PASS does not prove Programming Job semantics, PL behavior, socket/electrical behavior or real-IC Programming.

## Security and routing invariants

- Managed callers do not supply destination URLs.
- BFF Manager address is management-host-local and remains loopback-only in the current deployment model.
- Manager resolves PPU alias only from its registry.
- Manager routes are explicit allowlisted domain paths and methods.
- `Authorization`, `Idempotency-Key`, content type and accepted response type are preserved where required.
- The PPU secure Gateway remains authoritative for Principal, permission, Facility/PPU/Site scope and replay/idempotency enforcement.
- Managed Mode never silently falls back to direct PPU routing.
- Programming and Loopback share the same BFF -> Manager -> PPU Gateway boundary.
- PL/IC diagnostics fail closed until real paths exist.
- Mock success is never substituted for physical-path evidence.
- Programming Asset/Image identity must remain bound to the Job/Batch that consumes it.

## Failure-domain contract

```text
Manager / BFF unavailable
    -> no new centrally managed request can be routed
    -> already accepted PPU Jobs continue locally
    -> explicit Standalone/local PPU maintenance remains possible

One PPU Gateway unavailable
    -> that PPU loses managed access
    -> other PPUs remain independent

One Plasma Server unavailable
    -> that PPU cannot accept/execute new local work
    -> other PPUs remain independent
```

Central routing does not make an accepted in-flight Job depend on continuous Manager liveness.

## Validation boundary

Software tests can prove route allowlisting, alias ownership, byte-preserving Asset relay, browser/Manager boundary behavior, security-header propagation and shared PMode/EMode/Loopback API ownership.

Integration runtime acceptance must separately prove the deployed Management Host -> PPU path. Z2, PS <-> PL, FPGA, electrical and real-IC claims require their own evidence and are not implied by Managed Programming software tests.
