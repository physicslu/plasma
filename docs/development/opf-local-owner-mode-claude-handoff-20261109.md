# Claude Code handoff — PLASMA OPF Local Owner Mode full delivery plan

> **Status: planning handoff only / NO implementation authorization in this document.**
> Product policy: [ADR-0008](../adr/0008-local-owner-mode.md). Baseline code audit: [2026-11-09 Gate 1 ledger](opf-local-owner-mode-gate1-20261109.md).
> Source baseline: `main` `6706758d5a4ef536d9f02a7df860ccfa3b565b80`. Claude must rebase its **analysis** onto latest main and re-check exact call sites before preparing an implementation PR.
> Path for planning/source-only implementation: ordinary Claude Code on an authorized checkout, Host-only. No SWPC service restarts, deployment, PPU/Z2/DUT operations, privileged commands, credential extraction or unsafe recovery. GitHub PR merges always require explicit owner Gate 2.

## Mission and non-goals

Deliver the PLASMA PPU default product experience: `Connect PPU` -> authenticated local ownership -> trusted preflight -> truthful `READY` / `BUSY` / `RECOVERY_REQUIRED` -> owner-selected Runtime, Bundle, Provider, FPGA and explicit programming. No cloud account, License, manufacturer approval, copied pairing token, or repeatedly requested maintenance capability. Control must be recoverable from a replacement computer with physical possession alone, without the previous token or original PC. Retain device-specific transaction authentication, SHA256/Target/ABI, Root/FPGA/Site ownership, SAFE_OFF, SEALED and UNKNOWN no-replay.

Do **not** create another Engine/Router, merge standalone OPF with PPU Bootstrap, eliminate HMAC/Bearer checks before a trusted substitute exists, add factory allowlists, or claim that an untrusted bitstream is electrically safe from its manifest. Local Owner Mode is the PPU Host policy; portable OPF Core stays PPU-independent.

## Required preflight before touching implementation

1. Read latest `AGENTS.md`, `docs/development/plasma-development-common.md` and affected Manager/Web/Embedded contracts; review current executable code rather than assuming this plan still matches main. Load FPGA domain contract if the PR changes PL, MMIO, bitstream or ABI.
2. Find any newer Local Owner PR; reconcile before branching. Record `main` SHA, existing open-PR overlaps, dynamic API callers, tests and deployment-profile consumers. Check old `fixed-lifecycle` versus `mutable` policy behavior separately.
3. Record a **no-hardware** current-state baseline: focused Manager/Bootstrap/BFF/Registry tests and docs integrity. Report what is observed versus proposed (`PASS`, `FAIL`, `NOT_RUN`).
4. Resolve the **physical-presence primitive** by inventorying actual Z2 GPIO/button, maintenance jumper, serial/USB availability and PPU product-hardware assumptions. Source inspection is permitted; physical activation and testing are not included in planning. If no trusted primitive exists, report `DESIGN BLOCKED` instead of inventing an HTTP-only reclaim endpoint.
5. Audit `:18081` Bootstrap binding/firewall exposure, Gateway/BFF local bind, Manager registry persistence, credential file permissions, and `OUTCOME_UNKNOWN`/Site seals. Do not publish secrets or credential contents.

## Cross-cutting design decisions to freeze before implementation

| ID | Decision | Required contract |
| --- | --- | --- |
| D1 — Enrollment | Only a physically bounded PPU-local process can create/reassign the Manager trust relationship; the normal LAN is read-only until trust is established. | No remotely callable unauthenticated `claim`, `reset` or credential rotation. If direct cable is used as proof, document how exclusive physical access is actually established and defended. |
| D2 — Device identity | Bind the enrollment to observed immutable device identity and an authenticated PPU endpoint; do not trust only MAC/IP/`device_id` string. | Reject swapped/duplicated identity, alias collision, stale observation, spoofed bootstrap endpoint. |
| D3 — Credential | Generate per-PPU high-entropy secret/keys locally. Manager stores device-bound key material in owner-only storage, not Browser; rotate atomically. | No manufacturer secret or cloud service, no fleet-wide token, no printed long-lived token, no replay across device/action/SHA/transaction. |
| D4 — Ownership transfer | Reclaim allowed without prior computer/token, subject to actual physical presence and safe transaction reconciliation. | Block while unsafe/in-flight; never delete PPU journals, seals, active Set identity or unknown outcome; revoke old controller after atomic cutover. |
| D5 — Network boundary | Console/BFF and Manager loopback on controller; only controlled PPU ingress can accept management mutations. | Shared-LAN host must not gain writes from reachability alone; enforce same-origin/API allowlist and local-control context server-side. |
| D6 — Readiness | `DISCOVERED` is information, `ENROLLED` is local control, `READY` requires preflight. | BUSY, RECOVERY_REQUIRED, WRONG_DEVICE, INCOMPATIBLE are distinct; do not auto-enable unsafe hardware. |
| D7 — Owner customization | Owner Bundle/Provider/FPGA need no manufacturer whitelist. | Verify user-selected package/image integrity and actual Target/ABI/hardware capabilities; unsafe arbitrary PL behavior needs independent fail-safe evaluation. |
| D8 — Operator intent | Connect and readiness can be automatic; `Start`, deployment, activation and FPGA reload need explicit user intent. | Continue one-attempt/UNKNOWN policy; never secretly resend a possibly executed Flash or B3 activation. |

## Staged implementation plan for Claude Code

Each implementation phase is a **separate small Draft PR**, with affected source, tests, change ledger and no merge/deploy unless separately approved. Keep replacement and its callers/tests together; retire old API/UI only after the new path is proven (Replace-by-Default).

### LOM-P2A — Bootstrap local enrollment and recovery (highest dependency)

> **2026-11-09 refresh:** split into **LOM-P2A-1** (mutual request authentication; credential never on the wire; not blocked by D1), **LOM-P2A-0** (protocol freeze after owner D1/D2/D4 decisions) and **LOM-P2A-2** (enrollment/reclaim below). See [Gate 1 ledger §5](opf-local-owner-mode-gate1-20261109.md#5-latest-main-gap-audit-refresh-claude-code-2026-11-09).

**Likely touched:** `scripts/ppu-bootstrap-service.py`, `software/python/plasma_manager/bootstrap.py`, `verified_bootstrap.py`, credential store and focused tests; device-specific setup helpers only when necessary.

- Define enrollment states and a monotonic limited local-presence window with fresh challenge/nonce; do not choose a button/USB implementation until D1 is proven feasible. The enrollment handshake must authenticate the actual PPU, not merely a claimed Device ID.
- Add an owner-controlled, manufacturer-independent re-enrollment/rotation path; support a fresh Manager and a lost prior token. Prevent external unauthenticated invocation over the shared LAN.
- Preserve existing Bootstrap POST protection and exact HMAC transaction binding, using new enrolled credentials internally. Never print or return a long-lived credential to Console/Browser.
- Define crash-atomic credential transition (device and controller) and explicit reconciliation for partial transfer. Do not reset B1/B2/B3 status, Active Set or programming outcomes during reclaim.
- **Host-only negatives:** wrong device, replayed/expired enrollment, duplicate Manager, second LAN host, bad file permissions, interrupted rotation, no physical presence, in-flight Flash/B3, `UNKNOWN` persistence, stale credential use.
- **Exit:** complete Host-only state-machine and API contracts, no old-token dependency for the new physical recovery path, no network takeover; actual physical hardware proof remains separately scoped/NOT_RUN.

### LOM-P2B — Automatic Registry registration and local control readiness

**Likely touched:** `plasma_manager/registry.py`, `server.py`, `programming.py`, fleet observation/config and Manager tests.

- Introduce a bounded `Connect PPU` orchestration: discovery may propose a candidate but cannot grant write access. Reconcile live topology/device ID, enrolled local trust, duplicate endpoint, active Site/job and persistence before marking Ready.
- Retain atomic durable registry file, compare-and-swap endpoint migration and `disabled`/remove safeguards. Replace operator `Validate & Enable` as an authorization prerequisite only where the new trusted enrollment has equivalent authority.
- Keep old/current states truthful during migration: `pending` is not secretly commissioned. Do not allow a stale Fleet observation to commission a new PPU.
- **Negatives:** spoofed/mismatched identity, duplicate alias/endpoint, changed endpoint mid-claim, Manager crash/restart, registry corruption/persistence failure, active Job, conflicting control computer.
- **Exit:** new trusted PPU is automatically reconciled to READY without a second approval; untrusted candidate remains read-only or blocked.

### LOM-P1 — One-screen Console/BFF `Connect PPU`

**Likely touched:** `software/web/app/engineering/ppu-site-configuration.tsx`, `ppu-runtime-deployment.tsx`, `ppu-runtime-activation.tsx`, BFF Registry/Bootstrap routes, shared API typings, Browser tests.

- One owner action to connect; show topology, firmware/Runtime/FPGA/Active Set and correct readiness or recovery reasons. No Pairing Token box, explicit `Authorize Platform Maintenance` button or manual `Validate & Enable` in Local Owner Mode.
- Browser never sees a device secret. Maintain loopback Manager endpoint, strict BFF route allowlist, same-origin request controls and authoritative Manager/PPU enforcement; UI disabling alone is not a security boundary.
- Remove `fixed-lifecycle` Cookie/HTTPS-Origin product dependency for this **local profile**, without deleting optional public-demo/remote-profile protection until its consumers are audited. Do not replace it with an open-LAN write exception.
- **Negatives:** direct curl bypass, wrong-origin mutation, fake READY, stale topology, wrong device after reconnect, transfer in progress, USER `Start` absent, firmware/cache mismatch.
- **Exit:** new PPU and already-paired PPU use the same visible flow; no manual token/license prompt; a fail-closed PPU is not shown as Ready.

### LOM-P3 — Unified owner maintenance and programming

**Likely touched:** Manager Bootstrap coordinator/owner HMAC issuer, Runtime/Bundle/FPGA Console actions, PPU admission and associated Host-only tests. Reuse existing Bundle v3 B1/B2/B3 and Runtime engine.

- From one explicit operator-selected artifact, Manager automatically generates exact-action transaction proof to the authenticated PPU. Admission is distinct from install/activation; FPGA load is still a separate requested effect.
- Allow user-developed Provider/Bundle, with Source/Publisher commercial allowlists not introduced; the actual manifest, target, ABI and executable safety contract still applies.
- Validate Site/fence, Loaded Image/Root identity, electrical safety and no-retry state before executing. During reload/activation, active Jobs remain protected; unknown B3/Flash states require reconciliation.
- **Negatives:** wrong SHA/Target/ABI, tampered HMAC/transaction, B2-to-B3 replay/action swap, inactive/unknown Set, wrong-Image, in-flight Site, failed SAFE_OFF, untrusted bitstream attempting unsafe I/O.
- **Exit:** users may update Runtime/Bundle/Provider/FPGA and program without extra authorization prompts, with precise receipts and protected recovery.

### LOM-P4 — Retirement and acceptance

- Delete only superseded Pairing Token UI, manual commissioned ceremony, stale branches/tests/docs. Verify no old CLI/Browser/API consumer is orphaned; retain unrelated secure demo profiles when they serve a separate purpose.
- Run Python unit/integration, Web unit/Browser, documentation-integrity and repository-contract CI at the exact PR HEAD; record Runner/Run ID, SHA, negative evidence and no-replay proof.
- Prepare a **separately owner-authorized real PPU** test plan for a fresh device, replacement computer, lost credentials, Manager restart, custom Provider, FPGA update and Site programming. Require authentic receipts; Host-only must never be labeled electrical/HIL PASS.
- **Exit:** Local Owner Mode functional acceptance across both new and existing devices, no manufacturer approval dependency and no regression to electrical/transaction safety. Eight-Site HIL remains an independent qualification goal.

## Gate-by-gate acceptance ledger to maintain

| Case | Host-only / Browser | Real PPU |
| --- | --- | --- |
| New device discovers, enrolls, reaches Ready | Mock presence and real cryptographic handshake test | Separate hardware owner gate |
| New PC / old PC gone / token missing | Key-rotation and clean-state tests | Separate hardware owner gate |
| Restart Manager / power-loss during rotation | Crash injection and journal replay tests | Separate hardware owner gate |
| Attacker LAN discovers then attempts write/reclaim | HTTP rejection and race/CSRF negatives | Isolated-network smoke, separately approved |
| Two Managers race / active Flash | Exclusive transfer and no-preemption tests | Separate hardware owner gate |
| Runtime/B1/B2/B3 with owner's custom Bundle | SHA/Target/ABI/HMAC positive and negative | Authentic receipts on one Site |
| FPGA custom Image and SAFE_OFF failure | Static/virtual safety tests; not equivalent to hardware | Electrical qualification before PASS |
| UNKNOWN Flash or deployment outcome | Durable no-replay and Recovery state tests | Fault injection only with separate approval |

Use the current baseline suite from the [Gate 1 audit](opf-local-owner-mode-gate1-20261109.md) as the regression anchor; add actual feature tests in the phase that implements the feature. A mock positive proves software contract only. CI PASS does not authorize Gate 2 merge or device operation.

## Handoff protocol and stop conditions

Claude Code should start with an **updated read-only Gap Audit** against latest main, confirm D1–D8 and produce a file/function-level proposed diff plan. For each phase, create a separate Draft PR after its Gate 1 authorization, run the required hosted tests, and report exact HEAD/checks/threads/mergeability to ChatGPT for independent Gate 2 review. Never auto-merge or deploy.

**Stop and ask owner** if real physical-presence hardware is unavailable, a direct-LAN management port cannot be isolated/authenticated, control-transfer semantics would discard an in-flight/UNKNOWN result, custom FPGA could bypass independent safety gating, an authentication permission boundary is blocked, or a phase expands into unrelated OPF redesign. Do not treat these as excuses to weaken guards.

This file is an **execution-ready specification for a future Claude Code operator**, not evidence that Claude was invoked, code was changed, a PPU was reclaimed or any feature was accepted.
