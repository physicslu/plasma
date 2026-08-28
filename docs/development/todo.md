# Plasma Development Debt Register

This file tracks known executable gaps that are intentionally deferred from the current implementation scope. A Current architecture document may link here, but it must not describe these items as already implemented.

An item leaves this register only when its backend invariant, recovery semantics, tests and operator documentation are merged together. UI-only masking is not closure.

## High Priority

### Security Rollout and Identity Integration

**Status:** TODO / follow-up after PRs #167-#169

**Layer:** Security/control plane

**Reason:** The core remote-write authentication and authorization boundary is implemented and is no longer technical debt. Remaining work is production rollout and identity lifecycle integration around that boundary.

Required remaining work:

- complete the production threat model before exposing write APIs outside a trusted network;
- decide and document when secure Gateway deployment becomes the canonical production default while preserving standalone PPU operation and rollback;
- map Cloudflare Access / OIDC identities into the existing backend Principal / Permission / Facility-PPU-Site Scope model without bypassing backend authorization;
- add permission-aware disabled/hidden execution controls throughout PMode and EMode as operator guidance, while keeping the backend as the authority;
- add human credential rotation, revocation and session-lifecycle UX;
- define centralized multi-PPU identity management through Plasma Manager without making standalone PPU authorization depend on Manager availability.

### EMode Design System convergence to PMode baseline

**Status:** IN PROGRESS

**Layer:** Web presentation/component ownership

**Reason:** PMode is the current canonical operational visual baseline, while EMode still owns presentation variants for equivalent concepts. Shared domain semantics must not create two independently drifting visual systems.

Completed convergence slices:

- Batch Summary / PASS / FAIL / YIELD presentation uses shared `operator-ui` ownership;
- Engineering Settings uses the shared Settings UI primitives and approved Mock-derived page composition;
- Programming Job operation checkbox tiles and START / ABORT actions use one shared `operator-ui/programming-job-controls.css` visual contract derived from the PMode baseline; mode-local CSS no longer owns those equivalent control visuals.

Required remaining audit/work:

- reuse canonical typography, spacing, border, card and semantic status tokens wherever equivalent concepts still drift;
- audit Section Card and Site Card shell ownership;
- audit remaining button, select, input and checkbox variants outside the Programming Job operation/action controls;
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

### Remote Write Authentication and Authorization

Resolved by the security boundary and integration work merged in PRs #167, #168 and #169.

The current security invariant is:

```text
authenticated Principal
    -> permission authorization
    -> Facility / PPU / Site scope authorization
    -> durable Idempotency-Key command identity
    -> auditable command admission
    -> execution
```

The implementation now provides:

- canonical backend Principal, Permission and Facility / PPU / Site Scope authorization;
- Viewer / Operator / Engineer / Admin / Service role bundles while keeping authorization permission-based rather than role-name based;
- high-entropy Bearer authentication using stored SHA-256 token digests rather than persisted plaintext credentials;
- durable SQLite command/audit state with replay protection and idempotent completed-command replay;
- stable `401/E4101`, `403/E4102`, `409/E4103` and `409/E4104` security contracts;
- secure Gateway deployment wiring with owner-only security state/configuration, restrictive process permissions and reversible systemd enable/disable behavior;
- browser transport for Authorization and Idempotency-Key that remains passive on canonical non-secure deployments;
- authenticated `GET /api/security/me` Principal / permission / scope introspection;
- Viewer / Operator / Engineer / Admin expected-profile entry flow with the backend Principal remaining authoritative;
- standalone PPU authorization that does not depend on Plasma Manager availability.

Cloudflare Access / OIDC identity bridging, permission-aware control disabling, credential lifecycle UX and centralized multi-PPU identity management are follow-up rollout work and are tracked separately above; they do not reopen the completed backend remote-write authorization invariant.

See [Remote Write Security Boundary](../architecture/remote-write-security-boundary.md).

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
