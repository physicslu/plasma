# Plasma Development Debt Register

This file tracks known executable gaps that are intentionally deferred from the current implementation scope. A Current architecture document may link here, but it must not describe these items as already implemented.

An item leaves this register only when its backend invariant, recovery semantics, tests and operator documentation are merged together. UI-only masking is not closure.

## High Priority

### Backend PPU Execution Ownership / Lease

**Status:** TODO  
**Layer:** Backend control-plane invariant  
**Reason:** The Web UI mode-switch guard only prevents accidental operator navigation in one browser. It cannot prevent another browser tab, another PC, Plasma Manager, or a direct REST client from submitting conflicting work to the same PPU.

Required invariant:

```text
one PPU -> at most one active execution owner
```

The backend must own and enforce an execution lease/ownership record for each PPU. Production Mode and Engineering Mode are clients of that invariant, not its source of truth.

Expected behavior:

- Acquire an execution lease before dispatching a PPU Job.
- Keep the lease while any Site Job for that execution owner is submitting, queued, running, or cancelling.
- Reject conflicting execution from another owner/client with an explicit REST error such as `409 PPU_BUSY`.
- Include enough conflict metadata for diagnostics, for example PPU identity and current execution owner.
- Release the lease only after all owned Jobs reach terminal states, including cancellation completion.
- Define stale-owner recovery for browser/network/client loss without terminating valid PPU Jobs incorrectly.
- Enforce the invariant in the Python/backend execution path so direct REST access cannot bypass it.
- Add concurrency tests covering Production vs Engineering, two browser clients, direct REST calls, cancellation races, and stale lease recovery.

Non-goal: do not rely on a disabled P/E navigation control as the concurrency mechanism. That UI guard is UX protection only.

### Persistent Batch State and Gateway Restart Recovery

**Status:** TODO

**Layer:** Server-side Batch runtime

**Reason:** Batch records and accepted-Job observation currently live in Gateway process memory. A Gateway process restart loses the observer even though a PPU may still own accepted Jobs.

Required invariant:

```text
Gateway restart -> recover Batch identity and reconcile accepted Jobs -> no fabricated terminal result
```

Required work:

- persist immutable Batch input, state transitions, accepted Job IDs and policy revision;
- recover `QUEUED` / `RUNNING` / `STOPPING` records on process start;
- query authoritative PPU Job state before releasing execution ownership;
- make cancel/recovery idempotent;
- define retention and schema migration;
- test restart during submission, observation, retry and ABORT.

### Real Provider and Physical IC Quantity Handoff

**Status:** TODO

**Layer:** Production execution

**Reason:** Current `Repeat` produces IC quantity semantics only in Mock. Repeating operations against one physically loaded target is not proof that multiple ICs were processed.

Required work:

- implement an approved authenticated real-PPU execution provider;
- introduce explicit operator/MES planned quantity and next-device handoff/acknowledgement;
- bind PASS/FAIL to one physical IC identity or traceable presentation event;
- preserve `PROCESSED IC = PASS + FAIL` and exclude infrastructure ERROR;
- validate sockets, hardware, Z2/FPGA path and real target separately from Mock.

### Remote Write Authentication and Authorization

**Status:** TODO

**Layer:** Security/control plane

**Reason:** Optional Plasma Manager is observation-only and current remote write surfaces are not a production authorization design.

Required work:

- authenticate operator and service identities;
- authorize Facility/PPU/Site and operation scope;
- provide replay/idempotency and auditable command identity;
- keep standalone PPU execution independent from Manager availability;
- complete threat modeling before exposing write APIs outside a trusted network.

## Resolved maintenance debt

Resolved items belong in Git history rather than staying as open TODOs. In particular, do not reintroduce static test-count reports, superseded duplicate UI specifications, retired Programming Image filenames, or the misleading `gateway_legacy` module name. CI documentation integrity checks protect these boundaries.
