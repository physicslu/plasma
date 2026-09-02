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

### macOS Control Station Static Asset / Font Packaging 404

**Status:** TODO / observed during installed Control Station acceptance after PR #242

**Layer:** Control Station Web runtime / Common Release Format / macOS installer

**Reason:** Real installed-Control-Station browser acceptance observed `.woff2` and related static-asset requests returning HTTP 404 from `127.0.0.1:18000`. Managed routing itself passed: the Browser remained on the Manager-owned route and did not leak direct PPU Gateway traffic. This packaging/serving defect must therefore remain a separate deployment debt item rather than being misclassified as a routing failure.

Required work:

- capture the exact missing font/static-asset URLs and map each reference back to the generated Web build output;
- determine whether the loss occurs during Web build, standalone runtime assembly, Common Release Format packaging, macOS installer staging, or installed static-file serving;
- ensure every asset referenced by installed HTML/CSS/JS is present under the immutable installed runtime with the same hashed path/name expected by the browser;
- verify CJK/local font packaging explicitly, including `.woff2` files, rather than relying only on source-tree or development-server behavior;
- extend packaged-runtime and macOS installer acceptance to request referenced static assets and fail deterministically on unexpected 404 responses;
- add an installed-browser smoke assertion that no required `/assets/...` or font request returns 404 during normal page load;
- preserve the Single Routing Owner invariant while fixing asset serving: static-asset repair must not reintroduce Browser-owned PPU/Gateway routing or direct Gateway fallback.

Closure evidence must include a rebuilt/installed macOS package and real browser Network evidence showing required static/font assets load successfully without the previously observed 404 class.

## Deferred architecture evolution

### Plasma Hardware API / OpenOCD Adapter Productization

**Status:** TODO / post-PoC architecture evolution

**Layer:** Device Support / Programmer Backend / PPU hardware execution

**Reason:** The current PoC should continue using PYNQ + Python because it maximizes learning velocity for `PS -> PL -> Site -> real IC`. After the PoC proves the end-to-end programming path, the product architecture should decouple Python Device Support and replaceable Programmer Backends from board-specific PL access. The approved direction is documented in [Device Support / Hardware Execution / OpenOCD Architecture](../architecture/device-support-hardware-openocd.md) and must remain a Plan until production implementation and hardware evidence exist.

Required work:

- keep Device Support, parsers, Device Profiles, Programming Plans and Image handling in Python so new IC support remains data/rule driven rather than C-code driven;
- define a semantic Plasma Hardware API that exposes operations such as Site power/reset, SWD/JTAG transactions, program start/cancel and status without exposing raw register addresses to Programming Logic;
- evaluate a stable `libplasma_hw.so` boundary after PoC, with Python calling it through an approved binding only where C is justified;
- use UIO as the user-space hardware resource boundary, MMIO for control/status register access, IRQ for events and DMA for Programming Image bulk transfer;
- keep raw `/dev/mem` and per-register implementation details out of the production application contract;
- design a custom OpenOCD Plasma adapter that calls the Plasma Hardware API while preserving OpenOCD as a replaceable Programmer Backend;
- avoid per-bit OpenOCD/Python MMIO bit-banging; send high-level SWD/JTAG transactions to PL protocol engines so deterministic timing and multi-Site parallelism remain in hardware;
- keep OpenOCD target/flash-algorithm knowledge separate from Plasma hardware execution so a future Plasma-native or vendor backend can use the same Hardware API;
- after PYNQ is removed from the production hardware path, make Plasma own its Python runtime version instead of coupling application Python to the PYNQ image;
- evaluate Linux FPGA Manager for production bitstream loading and remove any production dependency on Jupyter;
- add native Z2 acceptance for UIO/MMIO/IRQ/DMA behavior, memory/resource stability, PS-to-PL execution, Site I/O and real IC programming before declaring this architecture Current.

Architectural invariant:

> Device knowledge and programming orchestration remain high-level and replaceable; the Hardware API describes Plasma hardware capabilities rather than raw registers, and PL owns deterministic protocol execution.

### Split Programming Image Data Plane

**Status:** TODO / future architecture optimization

**Layer:** Control plane / Programming data plane

**Reason:** Managed Mode currently sends Programming Asset/Image traffic through the same `Control Console -> BFF -> Manager -> PPU Gateway` routing ownership as Programming commands. This deliberately favors one trustworthy production route over premature data-plane separation. A direct or otherwise separate Image data channel should be introduced only when measured fleet bandwidth, concurrency, latency, memory pressure or reliability shows that Manager relay is a material bottleneck.

Required work before any split data plane may become canonical:

- measure Manager CPU, RAM, network utilization, Image throughput, concurrent PPU transfers, command latency and failure behavior at intended fleet scale;
- define an explicit Image data-channel contract that does not let the caller choose an arbitrary PPU URL;
- keep Manager authoritative for managed PPU identity/routing policy even if the Image bytes no longer transit Manager;
- preserve PPU identity binding, authorization, auditability, bounded transfer semantics and fail-closed behavior;
- preserve source Asset SHA-256, PPU cache identity and the Job/Batch reference to the exact Asset/Image consumed by execution;
- define retry, resume, cache, timeout and partial-transfer recovery semantics before deployment;
- prove that control commands such as status/cancel retain predictable latency while Image transfers are active.

### Loopback Coverage for a Split Image Data Plane

**Status:** TODO / mandatory companion to any future split Image data plane

**Layer:** Diagnostics / Programming data plane

**Reason:** If Programming later uses separate Control and Image data paths, a Control Path Loopback PASS alone no longer proves that the Programming Image route is healthy. Diagnostics must cover every production path that Programming depends on; otherwise Plasma could again report diagnostic PASS while Programming fails on an untested transport boundary.

Required work:

- add an Image Path diagnostic that uses the real production Programming Asset upload/cache API rather than a diagnostic-only upload route;
- verify `Console -> production Image data channel -> PPU Asset Service/Cache` with byte count, content integrity and SHA-256 evidence;
- verify that the uploaded/cached Asset identity is the same `asset_sha256` referenced by the Job or Batch that consumes it;
- preserve production authentication, PPU identity binding, timeout, retry, cache and error behavior during the diagnostic;
- report Control Path and Image Data Path evidence separately so a shallow PASS cannot be presented as complete Programming readiness;
- define complete Programming-path readiness as requiring all production-path evidence that the selected operation depends on.

Architectural invariant:

> If Programming is split into a Control Path and an Image Data Path, diagnostics must cover both production paths. Plasma must never claim complete Programming Route PASS from a Control Path Loopback alone.

## Deferred product capability

### UI Configuration Profiles — Save / Load

**Status:** TODO / future product capability

**Layer:** Control Station / Settings / configuration management

**Reason:** Plasma Settings will grow beyond one-off browser controls. Operators and engineers need a deterministic way to save a known-good configuration and later restore it without manually re-entering every field. This must be implemented as configuration management, not as an unversioned localStorage dump.

Required work:

- define which settings are profile-owned versus runtime/session-owned, PPU-owned, Manager-owned or security-sensitive;
- provide Settings UI actions to save a named configuration profile and load/activate an existing profile;
- define a versioned profile schema with validation, defaults and forward migration rules;
- preserve configuration ownership boundaries so loading a UI profile cannot bypass Manager routing, backend authorization or PPU-specific constraints;
- exclude secrets and credentials from portable profile data unless a separate approved secure-secret contract exists;
- define profile scope explicitly, including whether a profile is Control-Station-local, user-specific, Facility-specific, PPU-specific or portable;
- provide deterministic import/export only after schema/version/validation semantics are defined;
- show the active profile, unsaved changes and load/save failures clearly in the UI;
- add backend or durable local persistence based on the final ownership decision rather than treating browser localStorage as the canonical store;
- add tests for save/load round-trip, invalid or stale profile rejection, schema migration, partial failure and Managed/Standalone routing invariants.

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
