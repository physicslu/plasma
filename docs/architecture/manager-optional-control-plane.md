# Optional Plasma Manager Control Plane

## Status

**Current software architecture contract.**

Plasma Manager remains optional to each PPU's autonomous execution capability, but it is authoritative for routing requests issued by the central Control Console in Managed Mode.

Canonical ownership is defined in [Control Plane Routing Architecture](control-plane-routing-architecture.md).

## Architectural invariant: PPU autonomy

A Plasma PPU is a complete autonomous execution node. It must not require a live Manager connection to:

- start its local Plasma Server and Plasma Gateway;
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
local client -> Plasma Gateway -> Plasma Server -> local execution

Managed Mode
Control Console -> BFF -> Manager -> selected Plasma Gateway -> Plasma Server -> local execution
```

Manager is optional for the PPU, but mandatory for a Managed Mode central request once that mode is selected.

## Deployment roles

### PPU role — intended Z2 production direction

```text
PPU / Z2
├── Plasma Gateway
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
       +--> PPU A Plasma Gateway -> local execution
       +--> PPU B Plasma Gateway -> local execution
       +--> ...
```

The Management Host owns centralized visibility, managed routing, runtime PPU registry state, and cross-domain network commissioning orchestration. It does not execute FPGA/IC operations and does not receive Linux network-mutation privilege on the PPU.

## Mode A: Standalone PPU

No Manager or central host is required for local PPU capability:

```text
Local client / local PPU Console
        |
        v
Plasma Gateway
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
Target Plasma Gateway
      |
      v
Plasma Server
      |
      v
local execution
```

PMode, EMode, Programming Asset/Image transfer and PS Loopback use the same Managed Mode routing ownership.

A previously stored direct Plasma Gateway Endpoint is not the Managed Mode routing source of truth. When the Management Host is configured for Manager routing, the shared Workspace API base uses the same-origin Manager BFF path. An operator may select Standalone Mode explicitly when a direct local PPU workflow is intended.

## Browser-facing BFF boundary

BFF means **Backend for Frontend**. It is the presentation boundary for the Control Console.

It provides:

- same-origin browser APIs;
- validation of the management-host-local Manager configuration;
- a configured PPU alias without exposing arbitrary destination selection;
- bounded body forwarding for Programming Asset/Image traffic;
- propagation of required `Authorization` and `Idempotency-Key` headers;
- binary response preservation for readback;
- fail-closed behavior when Manager is unavailable.

The BFF does not accept arbitrary PPU destination URLs and does not own the alias-to-endpoint mapping.

The PPU/Site configuration surface uses an alias-scoped BFF route for PPU network desired state. Static IPv4 endpoint migration uses a separate Manager-owned `network-commissioning` resource. The Browser supplies the registry alias and desired static network values; it never supplies the physical candidate Plasma Gateway Endpoint or directly sequences PPU activation calls.

## Plasma Manager boundary

Manager owns fleet identity and managed route resolution:

```text
ppu-a -> configured Plasma Gateway Endpoint for PPU A
ppu-b -> configured Plasma Gateway Endpoint for PPU B
```

A managed request is relayed only through explicit allowlisted domain route families. Manager is **not** a generic arbitrary-method/arbitrary-URL HTTP proxy.

Current managed route families support the central PPU workflow for:

- PPU health/status and target discovery;
- Engineering sessions;
- Programming Asset/Image check and upload;
- Job submit/status/cancel/readback;
- server-side Batch submit/status/cancel;
- Plasma Gateway communication-policy read/write;
- PPU network desired-state read/write through `/api/settings/ppu-network`;
- Engineering Mock runtime settings read/write when that PPU runtime exposes the Mock feature;
- authenticated Principal introspection;
- PS real-path Loopback.

The Plasma Gateway/Mock/PPU-network settings writes remain subject to the secure Plasma Gateway authorization/idempotency contracts. Manager preserves and routes that evidence.

PPU network **activation remains excluded from the generic managed relay allowlist**. Static IPv4 migration is instead implemented as one explicit Manager-owned transaction:

```text
POST /api/registry/{alias}/network-commissioning
```

Manager owns the cross-domain sequence:

```text
current registry endpoint
-> persist desired static state
-> PPU activation apply
-> deterministic candidate reconnect
-> same immutable ppu_id verification
-> PPU activation commit
-> durable registry endpoint compare-and-swap
```

This is not a general command-routing exception. The Browser cannot promote desired-state access into an arbitrary activation sequence or supply an arbitrary candidate URL.

Manager runtime registry lifecycle and endpoint mutations are explicit write surfaces; fleet observation itself remains read-only. Unsupported write routes fail closed.

## Static IPv4 commissioning boundary

Static network commissioning crosses two durable state owners:

1. the PPU owns desired/actual Linux network state and activation rollback;
2. Manager owns the durable alias -> Plasma Gateway Endpoint registry mapping.

The Manager therefore coordinates both without collapsing ownership.

The transaction requires a commissioned PPU, no active Site execution, a current trusted fleet observation, and a mutable runtime registry. Candidate endpoint derivation preserves the old endpoint scheme/port and replaces only the host with the requested static IPv4 address.

The candidate must return the same canonical `ppu_id` from `/api/node` before Manager sends PPU activation commit. Wrong identity fails closed and the Manager registry is never repointed.

After commit, registry reconciliation uses compare-and-swap against the old endpoint captured at transaction start. This prevents the transaction from overwriting a newer operator/concurrent endpoint mutation.

Manager keeps a durable commissioning journal but does not persist the caller's `Authorization` credential. Restart recovery can automatically finish Manager-local registry reconciliation only after `activation_committed` is already durable. Earlier ambiguous states become `recovery_required` rather than guessing whether a protected PPU command succeeded.

DHCP endpoint migration is intentionally not implemented because Manager does not yet own deterministic DHCP lease/discovery evidence bound to the same immutable PPU identity.

## Plasma Gateway boundary

The Plasma Gateway is the northbound API boundary of one PPU:

```text
Z2 / PPU
├── Plasma Gateway
├── Plasma Server
├── PS
├── PL
└── IC
```

It validates its local REST/security contract, translates accepted requests to local runtime behavior and reports local status/errors. It does not choose between PPUs and does not own the fleet registry.

The secure Plasma Gateway remains the final execution/PPU-network authorization authority. Manager/BFF preserve authentication and idempotency evidence but do not grant permissions or widen Facility/PPU/Site scopes.

## PPU northbound contract

Core fleet-facing reads remain:

```text
GET /api/health/live
GET /api/health/ready
GET /api/node
GET /api/status
```

Managed write/read relay uses the existing Plasma Gateway API rather than defining a second Programming protocol. Exact Manager allowlisting is intentionally narrower than the complete standalone Plasma Gateway API surface.

Static IPv4 commissioning internally uses the existing PPU network desired-state and activation APIs, but those activation paths are invoked only by the Manager commissioning coordinator, not exposed as generic Browser relay paths.

## Programming Asset / Image direction

Phase 1 uses Manager-mediated Asset/Image transfer:

```text
Control Console
 -> BFF
 -> Manager
 -> selected Plasma Gateway
 -> Programming Asset / Batch contract
 -> PPU cache / Programming Runtime
```

The common routing owner does not require one wire representation for every workflow. EMode individual Engineering Jobs use binary Programming Asset cache upload plus `asset_sha256` Job references. PMode server-side Batch preserves its existing bounded JSON Asset envelope containing `asset_base64`, declared size and SHA-256; the Plasma Gateway decodes and validates that envelope before caching/execution.

Manager does not introduce or translate either representation. BFF and Manager forward the incoming body without decoding/re-encoding the Asset. Current PMode limits a selected Image to 4 MiB, so the Base64-expanded Batch body remains below the current 24 MiB managed request bound.

This is a deliberate Phase-1 compatibility decision: first establish one trustworthy route owner without silently redesigning the Batch data contract. A later direct-to-PPU or pre-upload/reference-only data plane requires measured evidence of a material bottleneck and must preserve authorization, identity binding, Asset integrity and diagnostic coverage.

## Failure-domain rule

```text
Manager / BFF unavailable
    -> no new centrally managed request can be routed or commissioned
    -> already accepted PPU work continues locally
    -> PPU-side activation rollback remains local and authoritative
    -> explicit Standalone/local maintenance remains available

Plasma Gateway failure on one PPU
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
- candidate Static IPv4 endpoint is derived by Manager rather than supplied as a URL;
- BFF and Manager forward only intentional headers;
- secure Plasma Gateway remains authoritative for Principal, permission and resource scope;
- `Idempotency-Key` remains available to the PPU replay ledger;
- Manager commissioning journal does not persist the caller's authorization credential;
- unsupported route/method combinations fail closed;
- Managed Mode does not silently bypass Manager.

## Current capability summary

| Capability | Current software contract |
|---|---|
| PPU local autonomy | Preserved |
| Manager fleet registry/observation | Implemented; runtime registry lifecycle/commissioning endpoint mutations are explicit, observation remains read-only |
| Manager PS Loopback relay | Implemented through shared managed route; legacy fixed route retained for compatibility |
| Managed Programming Job routing | Implemented as explicit allowlisted relay |
| Managed Programming Asset/Image relay | Implemented, bounded; EMode binary upload and PMode bounded Batch envelope retain their existing PPU contracts |
| Managed Batch routing | Implemented for current server-side Batch REST family |
| Managed Plasma Gateway/Mock settings | Explicit allowlisted read/write routes; secure Plasma Gateway remains authorization authority |
| Managed PPU network desired state | Explicit allowlisted `GET/POST /api/settings/ppu-network` |
| Manager Static IPv4 commissioning | Implemented as explicit Manager-owned transaction with same-`ppu_id` verification, PPU commit, registry endpoint CAS, durable journal and fail-closed recovery state |
| DHCP endpoint migration | Not implemented; deterministic lease/discovery + same-identity evidence is missing |
| PPU activation through generic relay | Prohibited |
| Manager arbitrary reverse proxy | Prohibited |
| PL Loopback | Not implemented; fail closed |
| IC Loopback | Not implemented; fail closed |

Software implementation is not evidence of Z2/FPGA/real-IC behavior. Integration runtime acceptance and hardware acceptance remain separate evidence layers.

## Capacity validation on Z2

Future Z2 acceptance must measure programming workload under 1/2/4/8 concurrent Sites, including CPU, RAM, PS/PL transfer, filesystem/network I/O, throughput and soak stability.

Manager-mediated Asset transfer must likewise be measured at intended fleet scale before deciding whether a split data plane is justified.
