# LOM-P2A-0 — Local enrollment and Recovery-Gated Takeover specification

> **Status: SPECIFICATION, amended by LOM-P2A-2 Gate 1 (2026-11-09).** Protocol `plasma.ppu.local-enrollment.v1`. Implemented Host-only by `scripts/ppu_controller.py`, `scripts/ppu_local_enrollment.py`, `scripts/ppu-enroll.py` and the Manager client ([P2A-2 Gate 1 report](opf-local-owner-mode-p2a2-gate1-20261109.md)); **not deployed**, real Z2 behavior NOT_RUN. P2A-2 amendments: the **PS-GPIO button** is the prototype's production enrollment entry (§3.1), the **Engineering CLI** replaces the serial development alternative (§3.2), the SD ticket is the rescue entry (§3.3), and the Gateway write binding G13 is specified in §6.1.
> Policy: [ADR-0008](../adr/0008-local-owner-mode.md); owner-confirmed [B1–B5](opf-local-owner-mode-b1b5-design-20261109.md); B3 decision **(b) Recovery-Gated Takeover** (owner, 2026-11-09).
> Executable reference: `software/python/tests/lom_p2a0_reference_model.py` (**test-only**, imported by nothing in the product) and `software/python/tests/test_lom_p2a0_enrollment_spec.py`. LOM-P2A-2 must make the real Bootstrap and Manager pass equivalent cases (§9).

## 1. Invariants

1. **One active controller per PPU.** The PPU stores one controller record with a monotonic **Controller Generation**; exactly one credential is valid at any instant.
2. **Physical presence only.** A controller relationship is created or replaced only after a PPU-local arming action: a long press of the PS-GPIO enrollment button bound to exactly one Control Station request (production entry on the prototype), a one-time ticket printed by root under a trusted Engineering Mode policy (controlled development entry), or a single-use ticket consumed **at boot** from the SD boot partition (rescue). No LAN request alone can arm, claim, reset or rotate; a LAN button *request* is inert until the physical press binds it.
3. **Atomic handover.** Credential, generation and mode change in **one** atomic record replacement. Before it, the old controller is fully valid; after it, every old-credential request fails (`CONTROLLER_REVOKED`), including requests on open connections.
4. **Takeover never acts on hardware.** Enrollment never cancels, interrupts, re-sends or marks PASS any Job, Flash, Bundle deployment or FPGA operation, and never deletes or rewrites journals, Site seals, the Active Set, Boot IDs, transaction results or recovery evidence.
5. **No old computer or old credential is required.** Reclaim needs only the ticket.
6. **Not a license.** The credential is a device-specific machine secret (B2), not a user account, manufacturer approval or entitlement.

## 2. Durable PPU records (root-owned, `0600`, atomic temp+fsync+rename+dir-fsync)

| Record | Content | Notes |
| --- | --- | --- |
| `controller` | `generation`, `credential` (256-bit, hex), `mode`, `controller_id`, `label`, `last_enrollment {enrollment_id, controller_nonce, response, source}` | Single record ⇒ atomic cutover. `response` makes a lost claim response retrievable (§5.4) |
| `ledger` | `consumed` ticket IDs, `high_water` generation | IDs appended **before** the ticket file is deleted. Capacity 4096 IDs, then `ENROLLMENT_LEDGER_FULL` |
| `pending` | `enrollment_id`, window key, `boot_id`, `deadline` (boot-time clock, 900 s window), `failures`, `source` (`ps-gpio-button` / `engineering-cli` / `sd-boot-partition`); button windows also `controller_public`, `ppu_public` | Valid only for the boot that armed it |
| `reconciliations` | `outcome.reconcile` decisions keyed by transaction | Append-only; never rewrites the original outcome |

`device_id` (machine-id derived) and, where readable under a qualified image, PL DNA are **binding attributes**, never secrets (B2). Migration (P2A-2): an existing P2A-1 `control-token` becomes `controller` generation 1, mode `NORMAL`, without changing the secret.

## 3. Arming entries (one engine, one claim exchange)

### 3.1 PS-GPIO button (prototype production entry)

1. The Control Station posts `POST /v1/enrollment/button-request {controller_public, label}` (X25519 public key, 64 hex). The PPU keeps **at most one** request per 120 s window. A request with a different key inside the window destroys every request and fails closed with `ENROLLMENT_CONTENDED` until the window ends; no station is ever chosen between competitors. While a window is armed, requests fail with `ENROLLMENT_BUSY`. With the board profile disabled: `ENROLLMENT_BUTTON_DISABLED`.
2. A debounced long press (board profile: default active-low, 50 ms debounce, 3 s hold; a line active at start must be released first) arms the window **only if exactly one uncontended request exists**: the PPU creates an ephemeral X25519 key pair; window key `K = HMAC-SHA256(X25519(ppu_priv, controller_public), schema‖"button-key"‖device_id‖request_id‖controller_public‖ppu_public)`; `enrollment_id = request_id`. Otherwise the press is ignored (`BUTTON_PRESS_*` event) and nothing arms.
3. The challenge additionally returns `source`, `controller_public` and `ppu_public`; the claim (§5) is unchanged. Only the station holding the private key of the bound request can produce the claim MAC or unwrap the credential.
4. GPIO chip label, line, active level, debounce, hold and poll period come from the root-owned board profile (`plasma.ppu.enrollment-button-profile.v1`); no board pin is hard-coded in the engine. The line is only ever configured and verified as an input.

### 3.2 Engineering CLI (controlled development entry)

`ppu-enroll.py arm` run as root (SSH or local console) arms a window with source `engineering-cli` and prints a one-time ticket once. It requires a root-owned, not group/other-writable Engineering Mode policy (`plasma.ppu.engineering-mode.v1`, `enrollment_cli: true`, unexpired `expires_at_epoch_s`); a CLI flag alone cannot enable it (`ENGINEERING_MODE_NOT_AUTHORIZED`). No LAN endpoint arms. Evidence must label it development.

### 3.3 SD ticket (rescue)

File `plasma-enroll.json` on the FAT boot partition, at most 4096 bytes:
`{"schema": "plasma.ppu.enrollment-ticket.v1", "ticket": "<64 lowercase hex>", "note": "<≤128 chars, optional>"}`; any other key is invalid. Ticket ID = first 32 hex of `SHA256("ticket-id\n" + ticket)`. Ticket key `K_t = HMAC-SHA256(bytes(ticket), "plasma.ppu.local-enrollment.v1/ticket-key")`. The Control Station may generate the file for the owner to copy; it contains no credential.

## 4. Boot-time consumption (PPU-local unit, before Bootstrap/Gateway accept mutations)

1. Drop `pending` from any previous boot (a reboot always ends a window).
2. If the ticket file exists: validate → invalid: delete, event `ENROLLMENT_TICKET_INVALID`, not armed.
3. Ticket ID already in `ledger.consumed` → delete, `ENROLLMENT_TICKET_REPLAYED`, not armed. Ledger full → delete, `ENROLLMENT_LEDGER_FULL`.
4. Append the ID to the ledger (durable) → delete the file from the boot partition (fsync) → write `pending` (deadline = boot clock + 900 s). If the delete fails: `ENROLLMENT_TICKET_NOT_CONSUMED`, not armed (the next boot rejects it as a replay).
5. A file written to the boot partition while the system runs is **not** read until the next boot. The Bootstrap service never reads the boot partition.

The former serial development alternative is replaced by the Engineering CLI (§3.2); a serial console is just one way to run it.

## 5. Enrollment exchange (Bootstrap HTTP; inert unless ARMED)

### 5.1 Challenge
`GET /v1/enrollment/challenge` → `{schema, device_id, enrollment_id, nonce, current_generation}`; single-use memory-only nonce. Without a valid pending window: `ENROLLMENT_NOT_ARMED` or `ENROLLMENT_EXPIRED`.

### 5.2 Claim
`POST /v1/enrollment/claim` `{enrollment_id, nonce, controller_nonce (32 hex), label (≤64), mac}` with
`mac = HMAC-SHA256(K_t, schema‖"claim"‖device_id‖enrollment_id‖nonce‖controller_nonce‖current_generation‖label)` (newline-joined).
Order: window → enrollment ID → nonce consumed (`ENROLLMENT_NONCE_INVALID`) → controller state not rollback-faulted → MAC (`ENROLLMENT_PROOF_INVALID`; the 5th failure deletes `pending` → `ENROLLMENT_LOCKED_OUT`) → takeover policy (§6) → commit.

### 5.3 Commit and response
Under the exclusive **transition fence** (§6): new 256-bit credential; `generation = max(current, high_water) + 1`; `mode` per §6; one atomic `controller` write; then `ledger.high_water`. Response: `{schema, device_id, generation, mode, recovery_blockers, controller_id, wrap_nonce, wrapped_credential}`. Credential wrapping (stdlib, PYNQ-safe): keystream = HMAC-SHA256 counter mode under `K_t` with info `schema/wrap‖nonce‖controller_nonce‖generation`; ciphertext = credential ⊕ keystream; tag = HMAC(K_t, info‖ciphertext). The plaintext credential is never sent.

### 5.4 Lost-response retrieval
Within the same window a claim by the **same** `controller_nonce` with a valid MAC (computed with the now-current generation) returns the stored response unchanged (no new generation). A different controller gets `ENROLLMENT_TICKET_CONSUMED`.

### 5.5 Manager side (P2A-2)
Manager credential store schema v2 adds `generation`, `controller_id` (v1 files migrate in place to generation 1). P2A-1 `GET /v1/auth/challenge` gains `controller_generation`; a Manager whose stored generation is lower reports **replaced by another controller**, stops all writes and never retries automatically. After enrollment the Manager signs every Bootstrap and Gateway request automatically; the owner never types a token. The PPU migrates a P2A-1 `control-token` to controller generation 1 / `NORMAL` with the same secret and then removes the legacy file.

## 6. Recovery-Gated Takeover (owner decision B3 (b))

Evaluated after a valid claim proof, under the exclusive transition fence. Every PPU admission path (Bootstrap mutation, Gateway Job/Batch/settings/activation writes, FPGA load) holds the fence shared, so no operation can be admitted between evaluation and commit. If the fence cannot be taken within 10 s the claim is deferred (`TAKEOVER_DEFERRED_ACTIVE_OPERATION`, `write-admission-in-progress`). An observation that cannot be made (Runtime lease, reload fence or seal directory unreadable) is a recovery blocker, never "no operation".

| PPU condition at claim | Result | Effects |
| --- | --- | --- |
| Any active operation: Site Job queued/running/cancelling, Bootstrap deployment queued/running/activating, FPGA reload fence held | `TAKEOVER_DEFERRED_ACTIVE_OPERATION` with the operation list | Nothing changes: no rotation, no cancel/interrupt/resend; failure counter unchanged; ticket stays armed for its window; client re-claims after the operation is terminal |
| No active operation, but unresolved safety state: any `site<N>.sealed`, any unreconciled `OUTCOME_UNKNOWN`, Bootstrap/Active Set `recovery_required` | Commit with mode `RECOVERY_ONLY` and `recovery_blockers` | Old controller revoked atomically; new controller limited to recovery actions (§7) |
| No active operation and no unresolved state | Commit with mode `NORMAL` | Manager still runs P2B preflight before showing READY |

### 6.1 Gateway write binding (G13)

The Gateway (`:18080`) classifies every `POST` route into an operation class; an unclassified route fails closed with `CONTROLLER_OPERATION_UNCLASSIFIED` before its body is read. A classified write needs the P2A-1 `PLASMA-PPU-HMAC-V1` proof under the **current** controller credential over a PPU-issued nonce (`GET /api/auth/challenge`). The Gateway never holds the credential: it forwards header, method, target, body SHA256 and class to the root Bootstrap **controller admission socket**, which verifies against the controller record re-read for every request, applies the mode policy, and holds the transition fence shared until the Gateway closes the connection after its response. Responses carry `X-Plasma-PPU-Response-Auth` signed through the same connection. The generation is never a credential. Without a configured admission socket the deployed Gateway entrypoint refuses to start unless explicitly run as a host lab (`--host-lab-unauthenticated-writes`).

## 7. RECOVERY_ONLY → NORMAL

- Allowed in `RECOVERY_ONLY` (explicit request each time): status/diagnostics, `site.diagnose`, `site.recover` (existing Embedded seal procedure; archives the marker with evidence), `outcome.reconcile` (appends a decision `CONFIRMED_NOT_EXECUTED` / `CONFIRMED_EXECUTED_VERIFIED` / `CONFIRMED_FAILED` with evidence; the original outcome stays `OUTCOME_UNKNOWN`, never PASS), `recovery.complete`. Without an explicit request: `RECOVERY_ACTION_NOT_REQUESTED`.
- Denied in `RECOVERY_ONLY`: every normal write → `CONTROLLER_RECOVERY_ONLY`.
- `recovery.complete` re-evaluates: no active operation, no seal, every `OUTCOME_UNKNOWN` reconciled, Active Set not `RECOVERY_REQUIRED`, observed `device_id` equals the enrolled one. Any blocker → `RECOVERY_BLOCKED` with the list. Success changes `mode` to `NORMAL` atomically; generation unchanged. Never automatic.

## States

- Controller: `UNENROLLED` (no record), `NORMAL`, `RECOVERY_ONLY`, `FAULT` (record generation below `ledger.high_water`, e.g. a restored backup — all requests fail `CONTROLLER_STATE_ROLLBACK`; an unreadable record fails `CONTROLLER_STATE_INVALID`).
- Enrollment window: `NONE`, `ARMED`, `CONSUMED`, `LOCKED_OUT`, `EXPIRED`.
- Button request window (memory only, 120 s): `AWAITING_BUTTON` (exactly one request), `CONTENDED` (a second key appeared; nothing can arm until the window ends).

```text
UNENROLLED --claim(no blockers)--> NORMAL
UNENROLLED --claim(blockers)-----> RECOVERY_ONLY
NORMAL/RECOVERY_ONLY --claim(active op)--> (unchanged)  TAKEOVER_DEFERRED_ACTIVE_OPERATION
NORMAL/RECOVERY_ONLY --claim(blockers)---> RECOVERY_ONLY (generation+1, old revoked)
NORMAL/RECOVERY_ONLY --claim(clean)------> NORMAL        (generation+1, old revoked)
RECOVERY_ONLY --recovery.complete(all clear)--> NORMAL   (same generation)
any --controller generation < high_water--> FAULT
NONE --boot consumes valid new ticket--> ARMED --commit--> CONSUMED
NONE --engineering CLI (trusted policy)--> ARMED
NONE --one button request + long press--> ARMED ; two requests --> CONTENDED (no arm)
ARMED --5 bad proofs--> LOCKED_OUT ; ARMED --900 s or reboot--> EXPIRED
```

## Operation classes

- Normal writes (denied in RECOVERY_ONLY): `bundle.upload`, `bundle.admit`, `bundle.install`, `runtime.deploy`, `fpga.load`, `site.job.submit`, `site.settings.write`, `site.activation`, and the Gateway classes `site.job.cancel`, `ppu.settings.write`, `engineering.write`.
- Recovery actions (allowed in both modes, explicit request): `status.read`, `site.diagnose`, `site.recover`, `outcome.reconcile`, `recovery.complete`.
- Bootstrap deployment reconciliation (P0, recovery action, explicit request): `deployment.reconcile` closes one `coordinator_result_unreconciled` Runtime deployment only after the PPU re-verifies the Coordinator receipt, the active release and a fresh G13-admitted PS loopback; see [the P0 recovery report](opf-local-owner-mode-p2a2-p0-runtime-reconcile-20261110.md).

## Error codes

| Code | Meaning |
| --- | --- |
| `ENROLLMENT_NOT_ARMED` | No boot-consumed ticket window |
| `ENROLLMENT_EXPIRED` | Window deadline passed or armed in another boot |
| `ENROLLMENT_NONCE_INVALID` | Nonce unknown or already used |
| `ENROLLMENT_PROOF_INVALID` | Wrong ticket proof / enrollment ID / device / malformed claim |
| `ENROLLMENT_LOCKED_OUT` | Fifth failed proof; window destroyed |
| `ENROLLMENT_TICKET_INVALID` | Boot-time file malformed; deleted |
| `ENROLLMENT_TICKET_REPLAYED` | Ticket ID already consumed; deleted |
| `ENROLLMENT_TICKET_CONSUMED` | Window already committed for another controller |
| `ENROLLMENT_TICKET_NOT_CONSUMED` | Boot-partition delete failed; not armed |
| `ENROLLMENT_LEDGER_FULL` | Ledger capacity reached; maintenance needed |
| `TAKEOVER_DEFERRED_ACTIVE_OPERATION` | Active Job/deployment/FPGA operation; nothing changed |
| `CONTROLLER_NOT_ENROLLED` | No controller record |
| `CONTROLLER_REVOKED` | Credential is not the current generation's |
| `CONTROLLER_RECOVERY_ONLY` | Normal write attempted in recovery mode |
| `CONTROLLER_STATE_ROLLBACK` | Controller record older than the ledger high-water mark |
| `RECOVERY_BLOCKED` | Recovery completion preconditions not met |
| `RECOVERY_ACTION_NOT_REQUESTED` | Recovery action without explicit request |
| `ENROLLMENT_BUTTON_DISABLED` | Button entry not enabled by the board profile |
| `ENROLLMENT_CONTENDED` | More than one station requested in the button window; nothing arms |
| `ENROLLMENT_BUSY` | A window is already armed |
| `ENGINEERING_MODE_NOT_AUTHORIZED` | Engineering CLI without a trusted, unexpired Engineering Mode policy or root |
| `CONTROLLER_STATE_INVALID` | Controller records unreadable or not root-private |
| `CONTROLLER_OPERATION_UNCLASSIFIED` | Write route or operation not in a known class; fails closed |
| `CONTROLLER_TRANSITION_IN_PROGRESS` | Admission waited too long behind a takeover/recovery commit |
| `CONTROLLER_UNAUTHENTICATED` | Request proof invalid (wrong, revoked or replayed credential/nonce); carries the current generation |

## Crash points

Each point is a simulated power loss in the reference model; the stated outcome is normative.

| Point | Required outcome |
| --- | --- |
| `boot.after_ledger_append` | File still present at next boot → rejected as replay and deleted; not armed; old controller valid |
| `boot.after_ticket_delete` | Ticket lost; not armed; owner writes a new ticket; old controller valid |
| `boot.after_arm` | Window survives a service restart within the same boot |
| `claim.before_controller_commit` | Old controller fully valid; generation unchanged; retry with a fresh nonce succeeds |
| `claim.after_controller_commit` | Cutover complete; old credential revoked; not FAULT although high-water lags; same controller retrieves the response |
| `claim.after_high_water` | Same as a completed claim |
| `recovery.before_mode_commit` | Still RECOVERY_ONLY; recovery completion can be repeated |

## 8. Threats and limits

- LAN attacker: cannot arm (no endpoint arms), cannot guess a 256-bit ticket, 5-attempt lockout, nonces single-use. Challenge flooding is a bounded DoS on the controlled link.
- Button race: a competing station inside the request window makes the window `CONTENDED` (fail closed, nobody wins); after a press binds a request, only that request's private key can claim. Repeated competing requests are a DoS on the controlled link; the Engineering CLI and SD ticket remain available.
- **Active man-in-the-middle on the management link during a button enrollment is NOT prevented**: without a PPU display there is no out-of-band comparison of the X25519 keys, so an attacker who can rewrite traffic between the station and the PPU at the moment of the press can substitute its own key. X25519 defeats passive observers only. This is the same link class whose confidentiality is already NOT_QUALIFIED. **Owner decision (2026-11-09):** accepted **for development only, on an isolated management network**. It is **not resolved for the production product**: production use of the button entry requires an explicit mitigation (for example an LED short-authentication pattern or a press-count confirmation) and a new decision before it may be claimed safe. No runtime gate was added.
- Physical attacker with the SD card or local console = owner by policy (B1/B2). A cloned SD card clones the credential; a hardware key store is a separate future decision.
- **G13 (new):** today the Gateway (`:18080`) write routes are not bound to the controller credential; the single-controller invariant therefore covers Bootstrap only until **P2A-2/P2B bind every PPU mutating surface to the current generation** (required by §6 fence and §7).
- Confidentiality: claim and P2A-1 traffic are integrity-protected only; TLS remains NOT_QUALIFIED. The wrapped credential is protected by the ticket key.

## 9. Test design and acceptance

Implemented now (reference model, Host-only, 35 cases): first enrollment; replacement station without the old computer/credential; serial labelled development; RECOVERY_ONLY for seal / UNKNOWN / Active Set recovery with full preservation; explicit recovery and reconciliation then NORMAL; lost-response retrieval; LAN cannot arm; runtime-written ticket ignored; malformed tickets; SD replay; expiry by time and reboot; proof failure lockout; nonce reuse and wrong device; deferral for Site Job, Bootstrap deployment and FPGA with zero side effects; explicit-request requirement; unenrolled and unknown operations; delete failure and full ledger; two stations racing the same ticket; restored-backup rollback fault; every crash point; and a document/model lock-step check.

LOM-P2A-2 Gate 1 status: implemented Host-only (see the Gate 1 report); the list below remains the exit definition, with hardware items NOT_RUN. LOM-P2A-2 exit: the same cases against the real boot unit, Bootstrap endpoints, atomic file records and Manager credential store v2, plus real fsync/rename crash injection, Gateway write binding (G13), concurrent HTTP races under the transition fence, PYNQ Python 3.10, and a separately approved hardware check of SD consumption on a Z2. Host-only PASS is never hardware PASS.
