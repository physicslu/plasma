# ADR-0008 — PLASMA PPU Local Owner Mode

> Status: **Accepted product policy / implementation pending** — owner decision 2026-11-09.
> Scope: PLASMA PPU product integration (Console, BFF, Manager, Bootstrap, Runtime and FPGA maintenance); **not** a mandatory dependency of standalone OPF Core.
> Gate 1: architecture, source audit and Host-only regression/test design only. No executable authorization changes, deployment, SWPC, PPU, FPGA or DUT operation. Merge requires a separate Gate 2 approval.

## Decision

**The device owner controls the programmer. The manufacturer does not license individual operations.** Local Owner Mode is the intended **default PLASMA PPU product mode**, including development and future offline shipping. A control station may run without internet access or a manufacturer service after installation. Possession must be established by a bounded local enrollment/recovery mechanism, **not** inferred from arbitrary network reachability.

The normative requirements are:

1. PLASMA PPU **MUST** operate offline without a cloud account, Cloudflare Tunnel, manufacturer license server, periodically renewed permission, or manufacturer approval for Runtime, Bundle, Provider, FPGA or programming operations.
2. Owner-facing workflows **MUST NOT** require a username/password, manually copied Pairing Token, manually obtained Maintenance Capability, or per-operation commercial authorization. A deliberate `Start`, deployment selection or other state-changing operator intent remains required; no silent Flash or installation.
3. Discovery **MUST** distinguish observed device identity from authenticated local-control authority. Device ID, IP address, MAC address, subnet adjacency and reachable HTTP alone are **NOT** possession proofs.
4. The PPU **MUST** provide a manufacturer-independent physical/local means to enroll a new control station and regain control after the previous station, token or local state is lost. An unauthenticated LAN request **MUST NOT** reset, transfer or claim ownership. The exact physical-presence primitive is a required hardware/Bootstrap design decision before P2 implementation.
5. After successful local enrollment, Manager and PPU **MAY** automatically negotiate, securely store and rotate device-specific internal credentials and transaction HMACs. These are **machine-to-machine safety and replay controls**, not licenses, cloud entitlements or extra user prompts. No shared hard-coded fleet credential.
6. Every write **MUST** be bounded by the enrolled control context and intended action, device identity, exact transaction and payload SHA256. Untrusted LAN origins and unclaimed or conflicted device identities fail closed. Management endpoints are loopback-bound on the Console host and exposed on the PPU only through an explicitly controlled local management interface/segment or equivalent authenticated channel.
7. **MUST** retain format and hash integrity, Target Platform and FPGA/Driver ABI checks, device capability, active Set, Site Lease/fence, Root/FPGA reload ownership, SAFE_OFF, electrical compatibility, SEALED and Recovery. `OUTCOME_UNKNOWN` **MUST NOT** be transformed into PASS or automatically retried merely because the owner has control.
8. A user-authored Provider or Bundle **MUST NOT** require a manufacturer whitelist or prior manufacturer approval. Verified provenance and user-selected trust policy may protect execution; hash matching alone does **NOT** prove software authenticity or safe behavior. User-authored FPGA images are allowed subject to actual hardware-interface and fail-safe qualification, not declared safe merely by metadata.
9. Startup/restart and recovery **MUST** preserve durable transaction records, activation identity and unresolved hardware states. Recovery of control credentials **MUST NOT** erase a pending Flash outcome, Site seal or active Lease, or trigger deployment/replay.
10. This product policy **MUST NOT** be converted into a mandatory PPU/Bundle/Owner-HMAC import of standalone OPF Core. Introducing manufacturer or third-party operation entitlements in future **requires a new explicit owner-approved ADR**; it cannot be hidden in an API, installer, UI or deployment profile.

## Authorization is not hardware safety

| Concern | Local Owner decision | Retained enforcement |
| --- | --- | --- |
| User account, password, commercial License, Cloudflare Tunnel | Not required for local owner operations | No dependency on external service availability |
| Registry Add / Validate & Enable | One owner-facing `Connect PPU` workflow; automatic observation and readiness admission | Durable identity/endpoint consistency, fresh topology observation, concurrent owner protection |
| Bootstrap Pairing Token | No manual entry, including after controller replacement | Local possession-based enrollment; secret handling and key rotation remain internal |
| Owner Operation Authorization (Bundle B2/B3) | No per-operation manual grant; Manager issues internal exact-action proof | Transaction, device, SHA, B1/B2/B3 consistency and anti-replay protections |
| Maintenance Capability Cookie / HTTPS Origin | Not a prerequisite in Local Owner Mode | Loopback/same-origin BFF and private PPU management ingress; no open-LAN writes |
| Runtime / Bundle / Provider / FPGA | Owner can select and install without manufacturer allowlist | Target, ABI, manifest, SHA, capability, runtime state, fences and rollback/recovery |
| Flash `Start` and Site selection | Explicit operator intent, no license prompt | Voltage/electrical validation, Site lease, SAFE_OFF, one-attempt/UNKNOWN policies |

### Distinct authority and ownership concepts

- **Physical owner/local-controller enrollment** establishes which local Manager may send state-changing requests. It is a product-security boundary, not a user account or a legal proof of ownership.
- **Manager registry membership** identifies and routes a PPU; readiness depends on live trusted observation and local control, not a separate human `Validate & Enable` approval. `disabled`/removal for operational maintenance remain distinct from unpairing or factory reset.
- **PPU execution owner** arbitrates multiple simultaneous Sites/Jobs. It is not human authentication, not a license, and does not entitle an unrelated Manager to take over an in-flight Job.
- **Bundle action HMAC** authorizes one exact internal transaction using a currently enrolled device-specific secret. It is not a manufacturer signature or a per-Bundle manufacturer whitelist.
- **Hardware safety authority** is independent of enrollment: an accepted controller cannot waive SAFE_OFF, unknown outcomes or hardware compatibility checks.

## Target local-control state machine

```text
DISCOVERED (read-only identity/topology)
    -> LOCAL_ENROLLMENT_REQUIRED (no trusted local control)
    -> ENROLLED (local physical-presence proof and device-specific trust)
    -> PREFLIGHT (runtime, active set, FPGA, Sites and transaction reconciliation)
    -> READY / BUSY / RECOVERY_REQUIRED / INCOMPATIBLE
```

`Connect PPU` is the single owner-facing flow. An already-enrolled PPU can proceed from discovery to preflight automatically. A first-time PPU may enroll automatically **only if** a physically bounded local channel is actually demonstrated; otherwise the PPU requires a bounded physical action (e.g. maintenance button/serial console) without asking for a copied Token. On an ordinary shared LAN, discovery remains read-only until the local enrollment condition is met.

A second control station must not silently invalidate a first controller during an active transaction. Transfer/reclaim needs proven physical access and an atomic credential transition, with any incumbent transaction reconciled before new writes. The owner can recover without the old controller or original credential; the system must explicitly report if recovery would reset non-safety configuration. Preserve evidence, active firmware identities, sealed markers and unresolved Jobs.

## FPGA / arbitrary Provider threat limit

An arbitrary FPGA bitstream can drive pins or bypass an expected PL-level `SAFE_OFF` implementation. The Gate 1 audit **cannot** claim a host-only ABI/manifest check proves electrical safety for an untrusted image. The later implementation must establish an independent fail-safe boundary (or document the exact unsupported image/hardware class and refuse unsafe activation). Keep Root-owned reload fencing, per-Site leases, output/power isolation and protected recovery. Provider subprocess isolation and authority to touch `/dev/mem`/USB/MMIO are likewise Host-owned and must not be granted merely by OPF Provider metadata.

## Migration gap: policy accepted, functionality not yet implemented

As of main `6706758d5a4ef536d9f02a7df860ccfa3b565b80`:

- Manager Registry still exposes `pending` -> `commissioned` via explicit `Validate & Enable`, with managed writes gated on `commissioned`; Console still presents the manual lifecycle flow.
- Bootstrap mutations require a provisioned Bearer Token. Verified Manager pairing accepts a manually supplied token, probes it against the live device and persists the token locally; no physical-presence reclaim/enrollment service exists in this reviewed path.
- The Console Runtime panel still asks for a factory/recovery pairing token and a user-triggered authorization button. `fixed-lifecycle` BFF policy still uses a short-lived maintenance cookie and HTTPS Origin; `mutable` policy does **not** require that cookie.
- Bundle HMAC issues/checks are device-, transaction-, action- and SHA-bound; the retained safety check is valuable. The credential provisioning and enrollment source must change before the manual input can be removed.
- The current portable OPF Core already supports standalone Host-only usage without Bundle/PPU or owner HMAC; the new owner policy belongs at PPU Host integration, not in Core.

The observed source audit and proposed small-PR sequence are documented in [Local Owner Mode Gate 1 ledger](../development/opf-local-owner-mode-gate1-20261109.md). The existing [Manager Registry](../architecture/manager-runtime-ppu-registry.md), [Remote Write Security Boundary](../architecture/remote-write-security-boundary.md) and other current implementation documents describe their **current** behavior until executable migration lands. They are not evidence that this target mode is operational.

## Delivery and acceptance

1. **P0 — Freeze and audit:** This ADR, call-chain inventory, threat model, minimal PR plan and Host-only baseline/negative evidence. No local enrollment implementation claimed.
2. **P2 — Bootstrap control continuity:** Device-specific local enrollment/credential rotation and physical recovery, first/second controller and token-loss negatives, no remote takeover or automatic replay.
3. **P1 — Console simplification:** Replace Add / Validate & Enable / Pair with `Connect PPU` and truthful readiness states after P2 is available.
4. **P3 — Unified control plane:** Remove user-facing operation entitlement friction across Runtime, Bundle, Provider, FPGA and Jobs while retaining exact-action transaction proofs and safety fences.
5. **P4 — Acceptance and retirement:** Host-only and Browser positive/negative tests; separate owner-authorized real PPU validation; retire only proven-dead UI/branches with no regression of recovery or existing historical evidence.

The minimum required scenario matrix includes fresh PPU, replacement station, lost token, Manager restart, malicious LAN claim/write, concurrent controllers, owner-developed Provider/FPGA, unsafe voltage/image, and `OUTCOME_UNKNOWN` with no replay. Tests that do not exercise the new enrollment path must be reported as baseline regression, **not** Local Owner Mode PASS. This ADR does not authorize merge, deployment, or hardware actions.
