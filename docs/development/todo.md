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

## Resolved presentation debt

### PMode / EMode Design System Convergence

Resolved by the shared Operator UI convergence work completed through PRs #170-#178 and the final repository audit performed after PR #179.

The current design-system boundary is:

```text
same operational concept
    -> shared component / presentation owner

mode-specific operational responsibility
    -> mode-specific information architecture / diagnostics
```

Shared-equivalent surfaces now have explicit common ownership:

- Programming Job uses the same `ProgrammingJobPanel` component in PMode and EMode, with `operator-ui/programming-job-controls.css` as the shared presentation owner;
- first-level Operator Panel Header / Title / Meta / Collapse presentation is owned by shared `operator-ui/operator-panel.css` primitives;
- Batch Summary and PASS / FAIL / YIELD presentation use shared `operator-ui` ownership and semantic theme tokens;
- Engineering Gateway and Mock Settings use the shared Settings UI primitives rather than independent page-local control systems;
- operator density contracts define shared panel, field, checkbox, action and status sizing for equivalent operator surfaces;
- source, browser parity and visual-regression contracts prevent equivalent PMode / EMode presentation ownership from silently splitting again.

The final audit also confirms that the remaining differences are intentional workflow boundaries rather than unresolved convergence debt:

- PMode keeps LED-first Site cards for production/operator visibility;
- EMode keeps the diagnostic Site table for engineering diagnosis;
- EMode Gateway, Facility/PPU targeting, engineering warnings and Site-selection controls remain Engineering-specific because PMode does not expose equivalent diagnostic controls;
- Engineering navigation and page composition remain mode-specific and are not required to mirror the PMode information architecture.

Therefore the convergence target is complete: Plasma has one shared design system for equivalent concepts without forcing PMode and EMode into one layout. Future presentation duplication should be tracked as a new, concrete ownership defect rather than reopening this broad convergence debt.

Relevant guardrails include:

- `software/web/tests/programming-job-control-design-system-contract.test.mjs`;
- `software/web/tests/engineering-programming-css-ownership-contract.test.mjs`;
- `software/web/tests/settings-ui-design-system-contract.test.mjs`;
- `software/web/e2e/tests/operator-panel-header-parity.spec.ts`;
- `software/web/e2e/tests/programming-job-real-stack-parity.spec.ts`.

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
