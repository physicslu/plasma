# Optional Plasma Manager Control Plane

## Status

**Current software architecture contract.**

Plasma Manager remains optional to each PPU's autonomous execution capability, but it is authoritative for routing requests issued by the central Control Console in Managed Mode.

Canonical ownership is defined in [Control Plane Routing Architecture](control-plane-routing-architecture.md).

## Architectural invariant: PPU autonomy

A Plasma PPU is a complete autonomous execution node. It must not require a live Manager connection to:

- start its local Plasma Server and PPU Gateway;
- expose its explicit local/Standalone maintenance boundary;
- continue an already accepted Job or Batch;
- recover a Site;
- perform local maintenance and diagnostics.

Dependency remains one-way:

```text
Plasma Manager -> PPU
```

PPU autonomy does **not** mean that a centrally managed Console may bypass Manager.

```text
Standalone Mode
local client -> PPU Gateway -> Plasma Server -> local execution

Managed Mode
Control Console -> BFF -> Manager -> selected PPU Gateway -> Plasma Server -> local execution
```

Manager is optional for the PPU, but mandatory for a Managed Mode central request once that mode is selected.

## Deployment roles

### PPU role — intended Z2 production direction

```text
PPU / Z2
├── PPU Gateway
├── Plasma Server
├── PS runtime
├── PL / FPGA
└── Sites / target ICs
```

The PPU owns execution. It does not own the fleet registry.

The integration-host Vite development runtime, build toolchain and Plasma Manager are not mandatory Z2 runtime dependencies.

### Management Host role

A Management Host may be a Mac, industrial PC, mini PC, VM or factory server:

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

The Management Host owns centralized visibility and managed routing. It does not execute FPGA/IC operations.

## Mode A: Standalone PPU

No Manager or central host is required for local PPU capability:

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

Standalone Mode is an explicit operating mode and local recovery boundary. It is not an automatic fallback from Managed Mode.

## Mode B: Managed fleet

Managed Mode uses one routing owner:

```text
Control Console
      |
      v
BFF
      |
      v
Plasma Manager
      |
      | resolve configured ppu_alias / canonical identity
      v
Target PPU Gateway
      |
      v
Plasma Server
      |
      v
local execution
```

PMode, EMode, Programming Asset/Image transfer and PS Loopback use the same Managed Mode routing ownership.

A previously stored direct Gateway URL is not the Managed Mode routing source of truth. When the Management Host is configured for Manager routing, the shared Workspace API base uses the same-origin Manager BFF path. An operator may select Standalone Mode explicitly when a direct local PPU workflow is intended.

## Browser-facing BFF boundary

BFF means **Backend for Frontend**. It is the presentation boundary for the Control Console.

It provides:

- same-origin browser APIs;
- validation of the management-host-local Manager configuration;
- a configured PPU alias without exposing the PPU endpoint;
- bounded body forwarding for Programming Asset/Image traffic;
- propagation of required `Authorization` and `Idempotency-Key` headers;
- binary response preservation for readback;
- fail-closed behavior when Manager is unavailable.

The BFF does not accept arbitrary PPU destination URLs and does not own the alias-to-endpoint mapping.

The PPU/Site configuration surface also uses an alias-scoped BFF route for PPU network desired state. The Browser supplies a registry alias and the fixed `ppu-network` resource kind; it never supplies the physical PPU destination URL.

## Plasma Manager boundary

Manager owns fleet identity and managed route resolution:

```text
ppu-a -> configured PPU A Gateway
ppu-b -> configured PPU B Gateway
```

A managed request is relayed only through explicit allowlisted domain route families. Manager is **not** a generic arbitrary-method/arbitrary-URL HTTP proxy.

Current managed route families support the central PPU workflow for:

- PPU health/status and target discovery;
- Engineering sessions;
- Programming Asset/Image check and upload;
- Job submit/status/cancel/readback;
- server-side Batch submit/status/cancel;
- Gateway communication-policy read/write;
- PPU network desired-state read/write through `/api/settings/ppu-network`;
- Engineering Mock runtime settings read/write when that PPU runtime exposes the Mock feature;
- authenticated Principal introspection;
- PS real-path Loopback.

The Gateway/Mock/PPU-network settings writes remain subject to the PPU secure Gateway authorization/idempotency contracts. Manager merely preserves and routes that evidence.

PPU network **activation** is not part of the generic managed relay allowlist in this slice. Changing a PPU endpoint and changing Manager's durable registry endpoint form one commissioning transaction and require explicit orchestration, same-`ppu_id` revalidation and rollback handling. The Browser therefore cannot promote desired-state access into an arbitrary activation sequence.

The fleet registry and fleet observation resources themselves remain read-only surfaces except for the explicit runtime-registry lifecycle API. Unsupported write routes fail closed.

## PPU Gateway boundary

The PPU Gateway is the northbound network boundary of one Programmer:

```text
Z2 / PPU
├── PPU Gateway
├── Plasma Server
├── PS
├── PL
└── IC
```

It validates its local REST/security contract, translates accepted requests to local runtime behavior and reports local status/errors. It does not choose between PPUs.

The PPU secure Gateway remains the final execution authorization authority. Manager/BFF preserve authentication and idempotency evidence but do not grant permissions or widen Facility/PPU/Site scopes.

## PPU northbound contract

Core fleet-facing reads remain:

```text
GET /api/health/live
GET /api/health/ready
GET /api/node
GET /api/status
```

Managed write/read relay uses the existing PPU Gateway production API rather than defining a second Programming protocol. Exact Manager allowlisting is intentionally narrower than the complete standalone Gateway API surface.

## Programming Asset / Image direction

Phase 1 uses Manager-mediated Asset/Image transfer:

```text
Control Console
 -> BFF
 -> Manager
 -> selected PPU Gateway
 -> Programming Asset / Batch contract
 -> PPU cache / Programming Runtime
```

The common routing owner does not require one wire representation for every workflow. EMode individual Engineering Jobs use binary Programming Asset cache upload plus `asset_sha256` Job references. PMode server-side Batch preserves its existing bounded JSON Asset envelope containing `asset_base64`, declared size and SHA-256; the PPU Gateway decodes and validates that envelope before caching/execution.

Manager does not introduce or translate either representation. BFF and Manager forward the incoming body without decoding/re-encoding the Asset. Current PMode limits a selected Image to 4 MiB, so the Base64-expanded Batch body remains below the current 24 MiB managed request bound.

This is a deliberate Phase-1 compatibility decision: first establish one trustworthy route owner without silently redesigning the Batch data contract. A later direct-to-PPU or pre-upload/reference-only data plane requires measured evidence of a material bottleneck and must preserve authorization, identity binding, Asset integrity and diagnostic coverage.

## Failure-domain rule

```text
Manager / BFF unavailable
    -> no new centrally managed request can be routed
    -> already accepted PPU work continues locally
    -> explicit Standalone/local maintenance remains available

Gateway failure on one PPU
    -> that PPU loses managed REST access
    -> other PPUs remain independent

Plasma Server failure on one PPU
    -> readiness/execution for that PPU fails
    -> other PPUs remain independent
```

This separates control-plane availability from execution-plane autonomy.

## Security boundary

Manager routing does not replace [Remote Write Security Boundary](remote-write-security-boundary.md).

Current invariants include:

- caller cannot supply a PPU destination URL;
- Manager resolves only enrolled/configured aliases;
- BFF and Manager forward only intentional headers;
- PPU Gateway remains authoritative for Principal, permission and resource scope;
- `Idempotency-Key` remains available to the PPU replay ledger;
- unsupported route/method combinations fail closed;
- Managed Mode does not silently bypass Manager.

## Current capability summary

| Capability | Current software contract |
|---|---|
| PPU local autonomy | Preserved |
| Manager fleet registry/observation | Implemented; runtime registry lifecycle mutations are explicit, observation remains read-only |
| Manager PS Loopback relay | Implemented through shared managed route; legacy fixed route retained for compatibility |
| Managed Programming Job routing | Implemented as explicit allowlisted relay |
| Managed Programming Asset/Image relay | Implemented, bounded; EMode binary upload and PMode bounded Batch envelope retain their existing PPU contracts |
| Managed Batch routing | Implemented for current server-side Batch REST family |
| Managed Gateway/Mock settings | Explicit allowlisted read/write routes; PPU secure Gateway remains authorization authority |
| Managed PPU network desired state | Explicit allowlisted `GET/POST /api/settings/ppu-network`; activation is not exposed through generic relay |
| Manager network commissioning transaction | Not implemented in this slice; must own static endpoint migration, identity revalidation, commit/rollback and registry reconciliation |
| Manager arbitrary reverse proxy | Prohibited |
| PL Loopback | Not implemented; fail closed |
| IC Loopback | Not implemented; fail closed |

Software implementation is not evidence of Z2/FPGA/real-IC behavior. Integration runtime acceptance and hardware acceptance remain separate evidence layers.

## Capacity validation on Z2

Future Z2 acceptance must measure programming workload under 1/2/4/8 concurrent Sites, including CPU, RAM, PS/PL transfer, filesystem/network I/O, throughput and soak stability.

Manager-mediated Asset transfer must likewise be measured at intended fleet scale before deciding whether a split data plane is justified.
