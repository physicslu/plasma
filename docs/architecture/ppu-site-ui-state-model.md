# PPU / Site UI State Model

> Status: P0 Engineering Console UI baseline.

This document defines presentation semantics for PPU admission and Programming Site configuration. It does not change Manager, Plasma Gateway, Protocol v3.3, or canonical PPU configuration contracts.

## 1. PPU state dimensions are orthogonal

The Engineering Console must not collapse lifecycle, connectivity, and health into one generic `Status` value.

| Dimension | Source | UI values |
|---|---|---|
| Lifecycle | Manager registry `lifecycle` | Pending, Commissioned, Disabled |
| Connectivity | Fleet `transport_state` | Online, Offline, Unknown |
| Health | Fleet identity/degraded observation | Healthy, Degraded, Error, Unknown |

Examples that must remain representable:

```text
Lifecycle = Commissioned
Connectivity = Offline
Health = Degraded
```

A commissioned PPU does not become uncommissioned merely because it is temporarily unreachable.

## 2. Admission readiness is explicit

`Validate & Enable` is eligible only when the current Fleet observation proves all existing admission prerequisites:

```text
Observation current
Transport reachable
Execution ready
No identity conflict
Not degraded
```

A disabled action must expose the failing prerequisites. A disabled button without an explanation is not sufficient operator feedback.

The UI derives this checklist from already-existing Fleet fields. It does not create a second admission policy or change Manager authorization.

## 3. Site configuration has three state layers

Configuration presentation follows the existing configuration architecture:

```text
Draft -> Desired -> Runtime
```

- **Draft**: browser-local edits not yet persisted.
- **Desired**: canonical PPU-owned Site configuration accepted by the PPU.
- **Runtime**: separately observed running state.

`Save Desired` means the Desired state was persisted. It must not imply that Runtime already changed.

The current Site settings contract reports `runtime_apply_supported=false`. A Desired/Runtime mismatch can therefore be shown as `Restart Required`. The UI must not invent a runtime apply operation or a revision identifier that the API does not provide.

## 4. Canonical Site domain

The canonical hierarchy remains:

```text
Facility -> PPU -> SITE 1..SITE N
```

`Site` is one independently controlled Programming Site inside a PPU. The Browser discovers topology from canonical PPU/Fleet data and must not hard-code eight Sites even when a particular hardware product has eight programming positions.

Retired Programmer/Channel identity is not reintroduced by this UI work. A genuine lower-level hardware or bus channel may still use the word `channel` only when it is distinct from canonical Programming Site identity.

## 5. Non-goals for this P0

This P0 does not add:

- automatic runtime Site apply;
- WebSocket/SSE transport;
- a new Manager write contract;
- hard-coded eight-Site topology;
- central Job/Batch routing;
- a browser-authoritative inventory or capability model.

Those require separate architecture and contract decisions.
