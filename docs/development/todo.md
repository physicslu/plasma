# Plasma Development Debt Register

This file tracks known executable gaps that are intentionally deferred from the current implementation scope. A Current architecture document may link here, but it must not describe these items as already implemented.

An item leaves this register only when its backend invariant, recovery semantics, tests and operator documentation are merged together. UI-only masking is not closure.

## High Priority

### Remote Write Authentication and Authorization

**Status:** TODO

**Layer:** Security/control plane

**Reason:** Optional Plasma Manager is observation-only and current remote write surfaces are not a production authorization design. Browser/runtime execution-owner tokens are concurrency identities only; they are not authenticated security principals.

Required work:

- authenticate operator and service identities;
- authorize Facility/PPU/Site and operation scope;
- provide replay/idempotency and auditable command identity;
- keep standalone PPU execution independent from Manager availability;
- complete threat modeling before exposing write APIs outside a trusted network.

### EMode Design System convergence to PMode baseline

**Status:** TODO

**Layer:** Web presentation/component ownership

**Reason:** PMode is the current canonical operational visual baseline, while EMode still owns presentation variants for equivalent concepts. Shared domain semantics must not create two independently drifting visual systems.

Required work:

- reuse canonical typography, spacing, border, card and semantic status tokens;
- converge Batch Summary / PASS / FAIL / YIELD presentation ownership;
- converge Section Card and Site Card shell ownership;
- converge button, select, input and checkbox variants;
- preserve EMode-specific engineering information architecture and diagnostic controls;
- keep PMode and EMode behavior contracts independent where their operational responsibilities differ;
- protect the shared design-system boundary with source/E2E/visual regression tests.

Non-goal: do not make EMode a copy of the PMode layout. The target is one Plasma design system with mode-specific workflows.

## Deferred product capability

### Real Provider and Physical IC Quantity Handoff

**Status:** TODO / deferred from the current 1-4 technical-debt sequence

**Layer:** Production execution

**Reason:** Current `Repeat` produces IC quantity semantics only in Mock. Repeating operations against one physically loaded target is not proof that multiple ICs were processed.

Required work:

- implement an approved authenticated real-PPU execution provider;
- introduce explicit operator/MES planned quantity and next-device handoff/acknowledgement;
- bind PASS/FAIL to one physical IC identity or traceable presentation event;
- preserve `PROCESSED IC = PASS + FAIL` and exclude infrastructure ERROR;
- validate sockets, hardware, Z2/FPGA path and real target separately from Mock.

## Resolved architecture debt

### Backend PPU Execution Ownership / Lease

Resolved by the backend execution-ownership contract merged in PR #164.

The physical PPU now enforces:

```text
one PPU -> at most one active execution owner
```

The invariant lives at the Python/backend PPU execution boundary, supports same-owner multi-Site concurrency, exposes `E4010 PPU_BUSY` / HTTP 409 for conflicting owners, preserves ownership until terminal Job state, and is not bypassed by direct REST access. PMode/EMode navigation guards remain UX protection rather than concurrency authority.

See [PPU Execution Ownership](../architecture/ppu-execution-ownership.md).

### Persistent Batch State and Gateway Restart Recovery

Resolved by the durable Batch persistence/reconciliation contract introduced with PR #165.

The current invariant is:

```text
Gateway restart -> recover Batch identity and reconcile durable Job IDs -> no fabricated terminal result
```

The implementation persists immutable Batch input, frozen communication policy, Programming Asset material when needed, execution checkpoints and Job admission state in versioned SQLite storage. Recovery reconciles `submitting` / `accepted` Job IDs against authoritative independent-PPU state, rebuilds Site cursors from the durable Job ledger, handles restart during ABORT idempotently, retries transient recovery observation according to Gateway policy, and retains terminal Batch history for later REST lookup.

The process-coupled Engineering Mock topology cannot preserve an independent PPU Job registry across Gateway restart; non-terminal Mock work therefore becomes an infrastructure recovery ERROR rather than a fabricated manufacturing result.

See [Batch Persistence and Gateway Restart Recovery](../architecture/batch-persistence-recovery.md).

## Resolved maintenance debt

Resolved items belong in Git history rather than staying as open TODOs. In particular, do not reintroduce static test-count reports, superseded duplicate UI specifications, retired Programming Image filenames, or the misleading `gateway_legacy` module name. CI documentation integrity checks protect these boundaries.
