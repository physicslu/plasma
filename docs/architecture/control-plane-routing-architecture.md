# Control Plane Routing Architecture

## Status

**Plan / canonical target direction.**

This document defines the approved managed-routing architecture and vocabulary for Plasma. It is intentionally more forward-looking than the current implementation: today, Manager fleet observation is read-only except for the narrow PS Loopback relay, and PMode / EMode Programming can still address a PPU Gateway directly through a browser `apiBase`. Those current limitations remain real until the corresponding implementation PR lands.

The architecture goal is to make Managed Mode use one production routing owner for both Programming and diagnostics while preserving autonomous standalone PPU operation.

## First-principles boundary

Plasma has three different questions that must not be assigned to the same component by accident:

```text
How does the UI call backend services safely?
        -> BFF

Which PPU should receive this command?
        -> Plasma Manager

How does this PPU expose its local execution service?
        -> PPU Gateway
```

The canonical managed prefix is therefore:

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
PPU Gateway @ target PPU / Z2
      |
      v
Plasma Server
```

Programming and Loopback diagnostics MUST share this production prefix in Managed Mode. They may diverge only after the request reaches the target Plasma Server and is dispatched to the intended execution or diagnostic handler.

## Canonical vocabulary and ownership

| Term | Canonical role | Owns | Must not own |
|---|---|---|---|
| **Control Console** | Operator-facing product UI | User intent, presentation, workflow state | PPU network topology or direct device routing policy |
| **BFF — Backend for Frontend** | Presentation Boundary | Same-origin browser API, UI-facing request shaping, browser session/auth boundary, sanitized errors | Selecting arbitrary PPU URLs, fleet scheduling, device execution |
| **Plasma Manager** | Fleet / Routing Ownership | PPU registry, canonical PPU identity, managed PPU selection, command routing, centralized policy/audit hooks | FPGA/IC execution, arbitrary caller-controlled reverse proxy behavior |
| **PPU Gateway** | Device Network Boundary | One PPU's northbound REST boundary, local request validation, REST-to-local-runtime translation, local status/error mapping | Fleet-wide PPU selection or knowledge of other PPUs |
| **Plasma Server** | PPU Execution Service | Local Job / Batch / diagnostic dispatch, Site execution coordination, Protocol v3.3 runtime | Fleet routing or browser presentation |
| **PS** | Embedded Linux processing system | Local control software, PS-side hardware/runtime integration | Fleet ownership |
| **PL** | FPGA programmable logic | Deterministic/custom hardware peripheral behavior | Fleet or browser policy |
| **Site** | Independent programming execution position | One programming target path and local Site state | Fleet identity |
| **IC** | Physical target device | Actual target programmable state | Control-plane routing |
| **Programming Asset** | Source data supplied to a programming workflow | Source identity, source bytes and metadata | Job routing policy |
| **Programming Image / Image** | Programming data used to create the executable target-memory representation | Image content identity | Fleet selection |
| **Programming Job** | One requested programming operation against a Site | Operation intent, Site target, execution references | PPU discovery |
| **Control Plane** | Central intent/routing layer | Identity, selection, policy, routing | Direct hardware execution |
| **Execution Plane** | Per-PPU runtime | Jobs, diagnostics, Site/PS/PL/IC execution | Global fleet routing |

### BFF

BFF means **Backend for Frontend**. It exists for the Control Console, not for the PPU fleet itself.

Typical responsibilities:

- provide same-origin browser endpoints;
- hide internal Manager listener details from the browser;
- translate UI-oriented requests into stable backend contracts;
- enforce browser-facing session/auth and input validation boundaries;
- normalize errors and avoid exposing internal network details.

The BFF is not the PPU routing source of truth. A browser must not be able to turn the BFF into an arbitrary `target_url` proxy.

### Plasma Manager

Plasma Manager is the managed-system **Control Plane** and fleet routing owner.

Conceptually:

```text
ppu-a -> PPU / Z2 A
ppu-b -> PPU / Z2 B
ppu-c -> PPU / Z2 C
```

A managed request identifies the intended PPU by canonical identity / alias. Manager resolves that identity through its registry and sends the request to the corresponding PPU Gateway.

Manager therefore answers:

> Which Programmer should receive this command?

Manager does not execute FPGA or IC operations itself. It also must not become a generic, caller-controlled reverse proxy; production write routes must be explicit, allowlisted domain APIs with defined authorization, idempotency, timeout and failure semantics.

### PPU Gateway

Each physical PPU has its own PPU Gateway. In the target Z2 product architecture the Gateway runs on the Z2 PS side alongside the local Plasma Server.

```text
PPU / Z2
├── PPU Gateway
├── Plasma Server
├── PS runtime
├── PL / FPGA
└── Sites / target ICs
```

The PPU Gateway answers:

> What request is this Programmer being asked to execute, and how is that request translated to the local runtime?

It knows this PPU. It does not own the fleet registry and does not decide between `ppu-a`, `ppu-b`, and `ppu-c`.

## Deployment roles

### Management Host

The intended managed deployment may run Control Console, BFF and Manager on a Mac, industrial PC, server or VM:

```text
Management Host
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

### PPU / Z2

The PPU is an autonomous execution node. Manager is not required for local startup or local execution capability.

Standalone Mode remains valid:

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

Managed Mode adds centralized routing above that autonomous node; it does not move the PPU execution runtime into Manager.

## Programming route — target Managed Mode

The canonical managed Programming route is:

```text
Control Console
      |
      v
BFF
      |
      v
Plasma Manager
      |
      | resolve ppu_alias / ppu_id
      v
PPU Gateway @ selected PPU
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

The Console must not retain a target PPU's URL as the managed routing source of truth. In Managed Mode the selected PPU identity is a domain identifier; Manager owns the identity-to-endpoint mapping.

## Loopback route — target Managed Mode

Loopback exists to test real production boundaries, not a parallel diagnostic transport.

The required shared prefix is identical to Programming:

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

Only then may dispatch differ.

### Loopback enabled / diagnostic request selected

`Loopback enabled` in this architecture means that the operator has selected a Loopback diagnostic operation; it is not a global replacement for normal Programming runtime.

```text
Control Console
  -> BFF
  -> Manager
  -> PPU Gateway
  -> Plasma Server
       |
       v
     Diagnostic Dispatcher
       |
       +--> PS endpoint  -> echo / validate at PS
       +--> PL endpoint  -> PS -> PL -> return        [future until implemented]
       +--> IC endpoint  -> PS -> PL -> IC -> return  [future until implemented]
```

A diagnostic request must not silently fall back to Mock or a shallower endpoint. Unsupported PL / IC routes fail closed until the requested physical boundary is actually implemented and validated.

### Loopback disabled / normal Programming selected

When Loopback is not the requested operation, normal Programming follows the same shared managed prefix and then enters the Programming runtime:

```text
Control Console
  -> BFF
  -> Manager
  -> PPU Gateway
  -> Plasma Server
       |
       v
     Programming Job Runtime
       |
       v
     SiteManager / SiteWorker
       |
       v
     PS -> PL -> Site -> IC
```

This distinction is critical: `Loopback PASS` may prove only the production boundaries actually traversed by that endpoint. It does not prove downstream hardware or Programming semantics that the Loopback request never exercised.

## Diagnostic evidence model

The value of Loopback is fault isolation. The validation claim must stop at the tested endpoint.

```text
PS Loopback PASS
Console -> BFF -> Manager -> PPU Gateway -> Server -> PS

PL Loopback PASS
Console -> BFF -> Manager -> PPU Gateway -> Server -> PS -> PL

IC Loopback PASS
Console -> BFF -> Manager -> PPU Gateway -> Server -> PS -> PL -> IC
```

Examples:

```text
PS PASS + PL FAIL
=> investigate PS <-> PL or PL endpoint behavior

PL PASS + IC FAIL
=> investigate PL <-> Site / IC boundary
```

A PS PASS must never be described as proof of PL, electrical, socket or real-IC Programming behavior.

## Programming Asset / Image route — Phase 1 target

For the first managed Programming implementation, Programming Asset / Image traffic will use the same managed routing ownership:

```text
Control Console
      |
      | Programming Asset / Image
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

This intentionally favors a **single routing source of truth** over premature data-plane optimization.

The contract must preserve verifiable provenance such as:

- Asset identity;
- source size;
- source hash;
- normalized Image identity where applicable;
- the Asset / Image identity actually consumed by the Job.

The Manager must use streaming/bounded-resource behavior appropriate to the implementation rather than assuming unbounded buffering.

A later direct PPU upload data plane may be considered only when measured evidence shows that Manager relay materially harms throughput, latency, concurrency or reliability. If that optimization is introduced, it must preserve authorization, PPU identity binding, Asset integrity and diagnostic coverage. It must not be introduced merely because a split data plane is theoretically fashionable.

## Failure-domain contract

Standalone PPU autonomy remains an architectural invariant.

Target behavior in Managed Mode:

```text
Manager unavailable
    -> no new centrally routed managed command can be accepted
    -> already-running PPU Jobs continue according to local PPU state
    -> local PPU execution / maintenance path remains available

One PPU Gateway unavailable
    -> that PPU is unreachable from Manager
    -> other PPUs remain independent

One Plasma Server unavailable
    -> that PPU cannot execute new local work
    -> other PPUs remain independent
```

Centralized routing must not imply that an in-flight Programming Job depends on continuous Manager liveness after the PPU has accepted ownership of that Job.

## Security and routing invariants

- Managed callers identify a PPU by canonical domain identity, not an arbitrary URL.
- Manager resolves PPU identity to the configured registry endpoint.
- Manager write APIs are explicit domain routes, not a generic proxy.
- BFF exposes only intentional browser-facing contracts.
- PPU Gateway validates requests for its local execution boundary.
- Programming and Loopback use the same Manager -> PPU routing boundary in Managed Mode.
- PL / IC diagnostics fail closed until their real paths exist.
- Mock success is never substituted for physical-path evidence.
- Image / Asset integrity must be bound to the Job that consumes it.

## Current implementation gap

At the time this plan is written, Plasma has not yet completed this consolidation:

| Capability | Current implementation | Target |
|---|---|---|
| Manager fleet observation | Centralized / read-only | Keep |
| PS Loopback Manager relay | Implemented, narrow allowlist | Keep and make it the same managed prefix used by Programming |
| PMode / EMode Programming routing | Browser can address PPU Gateway directly through `apiBase` | Route managed Programming through BFF -> Manager -> PPU Gateway |
| Programming Asset upload | Direct PPU-oriented Web REST path | Relay through Manager in Phase 1 managed mode |
| PL Loopback | Fail closed / not implemented | Real PS <-> PL path only |
| IC Loopback | Fail closed / not implemented | Real PS -> PL -> IC path only |

This document is the architecture contract for the implementation work; it is not evidence that the target write path already exists.

## Acceptance principle for the implementation phase

The future implementation is not complete merely because the APIs compile. Managed acceptance must demonstrate that the same selected PPU identity and Manager routing boundary are used for:

```text
PS Loopback
PMode Programming
EMode Programming
Programming Asset / Image transfer
```

and must retain truthful validation boundaries for Mock, Z2, PL and real IC evidence.
