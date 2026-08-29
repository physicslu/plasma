# Production Operation Topology

> Status: **Plan — approved target architecture.** This document defines the intended production operator topology. It does not claim that the current read-only Plasma Manager already implements programming-command routing.

## 1. Decision

Plasma uses one canonical production operator model for both one PPU and many PPUs:

```text
Operator
   |
   v
Central Web Console
   |
   v
Plasma Manager
   |
   +--> PPU #1 Gateway -> Plasma Server -> PS / PL / Sites
   +--> PPU #2 Gateway -> Plasma Server -> PS / PL / Sites
   +--> ...
   +--> PPU #N Gateway -> Plasma Server -> PS / PL / Sites
```

A one-PPU installation is not a different product mode. It is the same topology with a registry containing one PPU:

```text
Central Web Console -> Plasma Manager -> PPU #1
```

Adding PPUs therefore expands inventory rather than changing the operator workflow or introducing a second production UI architecture.

## 2. Physical deployment

Central Web Console and Plasma Manager are separate logical components but may be physically co-located on one management host:

```text
Management Host / Operator PC
├── Central Web Console
└── Plasma Manager
      |
      +--> PPU #1
      +--> PPU #2
      +--> PPU #N
```

They may later be split across hosts when availability, security, scale, or factory operations justify that deployment. Co-location must never become a code-level requirement.

## 3. PPU role

A production PPU is an execution node. Its mandatory responsibilities are the local execution path:

```text
PPU Gateway
   |
   v
Plasma Server
   |
   v
PS execution
   |
   v
PL
   |
   v
Programming Sites / target ICs
```

The normal production PPU role does not require a Node.js/npm/Vite development runtime or a second full production Web Console. Frontend compilation belongs off-target.

The PPU remains the source of truth for its identity, capability, Site topology, local scheduling, protocol timing, safety behavior, diagnostics, and recovery.

## 4. Control plane versus execution plane

The production boundary is:

```text
CONTROL PLANE
Central Web Console
Plasma Manager
Facility / PPU selection
Fleet observation
Future authorized orchestration / command routing

EXECUTION PLANE
PPU Gateway
Plasma Server
PS / PL
Programming Sites
Target IC
```

Manager may coordinate or route future production operations, but it must not bypass the PPU REST contract and call internal `SiteManager` / `SiteWorker` implementation APIs directly.

## 5. Execution autonomy

Centralized operation does not mean centralized execution ownership.

The PPU must remain locally autonomous once work has been accepted. A Manager or Central Web Console outage must not corrupt an in-flight local execution, invalidate PPU safety/recovery rules, or move deterministic Site scheduling into the management host.

The distinction is:

```text
Operator access / fleet orchestration -> control plane
Accepted programming execution       -> PPU execution plane
```

A control-plane outage may make new centrally initiated operations unavailable until the control plane recovers. It must not turn the Manager into a runtime dependency inside the PPU's local execution loop.

## 6. Engineering / service access

Direct PPU access is retained as a service capability, not as a second normal production operating mode:

```text
Engineer / service tool
        |
        +--> PPU Gateway
        +--> PPU CLI / diagnostic interface
```

Typical uses include commissioning, diagnostics, recovery, maintenance, and fault isolation when the central control plane is unavailable.

This path must not cause Plasma to maintain two independent production workflows, two authoritative UI models, or two conflicting sources of configuration truth.

## 7. Current implementation versus approved target

### Current implementation

The current Plasma Manager is optional and read-only. It aggregates PPU health, identity, topology, and last-known observation state. It does **not** currently route programming commands or own central scheduling.

The repository also retains direct/local PPU operation capabilities used by development, integration, diagnostics, and current standalone workflows.

### Approved production target

The approved production operator topology is:

```text
Central Web Console -> Plasma Manager -> one or more autonomous PPUs
```

The future write/orchestration path requires explicit contracts for authentication, authorization, auditability, idempotency/replay, command routing, failure semantics, and recovery. This document approves the topology; it does not pre-approve those security or protocol details.

## 8. One PPU and many PPUs

The architectural invariant is cardinality-independent:

```text
M = 1:
Console -> Manager -> PPU #1

M > 1:
Console -> Manager -> PPU #1..#M
```

No separate "single-PPU production mode" should be introduced merely because `M = 1`.

This reduces product complexity in UI navigation, authentication, session ownership, API routing, acceptance testing, deployment, and operator training.

## 9. Deployment profiles implied by this architecture

The existing integration-host deployment currently co-locates development/demo components. Production deployment should evolve toward explicit roles rather than assuming every host runs every service.

Conceptual target profiles:

```text
management-host:
  Central Web Console
  Plasma Manager

ppu:
  Plasma Web REST Gateway
  Plasma Server
  PS / PL integration
```

Exact `plasmactl` profile syntax and Z2 packaging are implementation work and are not defined by this document.

## 10. Non-goals

This decision does not mean:

- the current read-only Manager already supports programming writes;
- Manager owns deterministic Site execution;
- a PPU may bypass its own Gateway/Server contracts;
- direct service access is a second production workflow;
- Central Web Console and Manager must run in the same process or on the same machine;
- Z2 must run Vite, npm, or frontend compilation;
- Manager failure may silently redirect production commands through an ungoverned alternate path.

## 11. Validation consequences

Future acceptance should test the architecture in layers:

1. Management Host -> Manager control-plane behavior.
2. Manager -> PPU northbound contract.
3. PPU Gateway -> Plasma Server execution contract.
4. PS -> PL real-path behavior.
5. PL -> target IC behavior.
6. Control-plane failure while PPU execution is active.
7. Engineering/service direct access as an explicitly authorized recovery path.

A PASS at a higher layer must never substitute for evidence that a lower physical or execution boundary was actually crossed.
