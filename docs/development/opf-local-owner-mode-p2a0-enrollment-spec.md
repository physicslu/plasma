# LOM-P2A-0 — Local enrollment and Recovery-Gated Takeover specification

> **Status: FROZEN SPECIFICATION (Gate 1 approved 2026-11-09). Not implemented.** Protocol `plasma.ppu.local-enrollment.v1`. This PR authorizes specification and test design only: no Bootstrap/Manager/Console code, deployment, SWPC/PPU/DUT operation or merge.
> Policy: [ADR-0008](../adr/0008-local-owner-mode.md); owner-confirmed [B1–B5](opf-local-owner-mode-b1b5-design-20261109.md); B3 decision **(b) Recovery-Gated Takeover** (owner, 2026-11-09).
> Executable reference: `software/python/tests/lom_p2a0_reference_model.py` (**test-only**, imported by nothing in the product) and `software/python/tests/test_lom_p2a0_enrollment_spec.py`. LOM-P2A-2 must make the real Bootstrap and Manager pass equivalent cases (§9).

## 1. Invariants

1. **One active controller per PPU.** The PPU stores one controller record with a monotonic **Controller Generation**; exactly one credential is valid at any instant.
2. **Physical presence only.** A controller relationship is created or replaced only by a PPU-local, single-use enrollment ticket consumed **at boot** from the SD boot partition (primary) or printed by root on the local console (development alternative). No LAN request can arm, claim, reset or rotate.
3. **Atomic handover.** Credential, generation and mode change in **one** atomic record replacement. Before it, the old controller is fully valid; after it, every old-credential request fails (`CONTROLLER_REVOKED`), including requests on open connections.
4. **Takeover never acts on hardware.** Enrollment never cancels, interrupts, re-sends or marks PASS any Job, Flash, Bundle deployment or FPGA operation, and never deletes or rewrites journals, Site seals, the Active Set, Boot IDs, transaction results or recovery evidence.
5. **No old computer or old credential is required.** Reclaim needs only the ticket.
6. **Not a license.** The credential is a device-specific machine secret (B2), not a user account, manufacturer approval or entitlement.

## 2. Durable PPU records (root-owned, `0600`, atomic temp+fsync+rename+dir-fsync)

| Record | Content | Notes |
| --- | --- | --- |
| `controller` | `generation`, `credential` (256-bit, hex), `mode`, `controller_id`, `label`, `last_enrollment {enrollment_id, controller_nonce, response, source}` | Single record ⇒ atomic cutover. `response` makes a lost claim response retrievable (§5.4) |
| `ledger` | `consumed` ticket IDs, `high_water` generation | IDs appended **before** the ticket file is deleted. Capacity 4096 IDs, then `ENROLLMENT_LEDGER_FULL` |
| `pending` | `enrollment_id`, ticket-derived key, `boot_id`, `deadline` (boot-time clock, 900 s window), `failures`, `source` | Valid only for the boot that armed it |

`device_id` (machine-id derived) and, where readable under a qualified image, PL DNA are **binding attributes**, never secrets (B2). Migration (P2A-2): an existing P2A-1 `control-token` becomes `controller` generation 1, mode `NORMAL`, without changing the secret.

## 3. Ticket

File `plasma-enroll.json` on the FAT boot partition, at most 4096 bytes:
`{"schema": "plasma.ppu.enrollment-ticket.v1", "ticket": "<64 lowercase hex>", "note": "<≤128 chars, optional>"}`; any other key is invalid. Ticket ID = first 32 hex of `SHA256("ticket-id\n" + ticket)`. Ticket key `K_t = HMAC-SHA256(bytes(ticket), "plasma.ppu.local-enrollment.v1/ticket-key")`. The Control Station may generate the file for the owner to copy; it contains no credential.

## 4. Boot-time consumption (PPU-local unit, before Bootstrap/Gateway accept mutations)

1. Drop `pending` from any previous boot (a reboot always ends a window).
2. If the ticket file exists: validate → invalid: delete, event `ENROLLMENT_TICKET_INVALID`, not armed.
3. Ticket ID already in `ledger.consumed` → delete, `ENROLLMENT_TICKET_REPLAYED`, not armed. Ledger full → delete, `ENROLLMENT_LEDGER_FULL`.
4. Append the ID to the ledger (durable) → delete the file from the boot partition (fsync) → write `pending` (deadline = boot clock + 900 s). If the delete fails: `ENROLLMENT_TICKET_NOT_CONSUMED`, not armed (the next boot rejects it as a replay).
5. A file written to the boot partition while the system runs is **not** read until the next boot. The Bootstrap service never reads the boot partition.

**Serial development alternative:** root on the PPU-local console runs the enrollment CLI, which generates a ticket in memory, appends its ID to the ledger, arms `pending` with `source: serial-dev` and prints the ticket once on that console. Evidence must label it development; it is physical presence only when the UART is not attached to a networked host.

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
Manager credential store schema v2 adds `generation`, `controller_id`. P2A-1 `GET /v1/auth/challenge` gains `controller_generation`; a Manager whose stored generation is lower reports **replaced by another controller**, stops all writes and never retries automatically.

## 6. Recovery-Gated Takeover (owner decision B3 (b))

Evaluated after a valid claim proof, under the exclusive transition fence. Every PPU admission path (Bootstrap mutation, Gateway Job/Batch/settings/activation writes, FPGA load) holds the fence shared, so no operation can be admitted between evaluation and commit.

| PPU condition at claim | Result | Effects |
| --- | --- | --- |
| Any active operation: Site Job queued/running/cancelling, Bootstrap deployment queued/running/activating, FPGA reload fence held | `TAKEOVER_DEFERRED_ACTIVE_OPERATION` with the operation list | Nothing changes: no rotation, no cancel/interrupt/resend; failure counter unchanged; ticket stays armed for its window; client re-claims after the operation is terminal |
| No active operation, but unresolved safety state: any `site<N>.sealed`, any unreconciled `OUTCOME_UNKNOWN`, Bootstrap/Active Set `recovery_required` | Commit with mode `RECOVERY_ONLY` and `recovery_blockers` | Old controller revoked atomically; new controller limited to recovery actions (§7) |
| No active operation and no unresolved state | Commit with mode `NORMAL` | Manager still runs P2B preflight before showing READY |

## 7. RECOVERY_ONLY → NORMAL

- Allowed in `RECOVERY_ONLY` (explicit request each time): status/diagnostics, `site.diagnose`, `site.recover` (existing Embedded seal procedure; archives the marker with evidence), `outcome.reconcile` (appends a decision `CONFIRMED_NOT_EXECUTED` / `CONFIRMED_EXECUTED_VERIFIED` / `CONFIRMED_FAILED` with evidence; the original outcome stays `OUTCOME_UNKNOWN`, never PASS), `recovery.complete`. Without an explicit request: `RECOVERY_ACTION_NOT_REQUESTED`.
- Denied in `RECOVERY_ONLY`: every normal write → `CONTROLLER_RECOVERY_ONLY`.
- `recovery.complete` re-evaluates: no active operation, no seal, every `OUTCOME_UNKNOWN` reconciled, Active Set not `RECOVERY_REQUIRED`, observed `device_id` equals the enrolled one. Any blocker → `RECOVERY_BLOCKED` with the list. Success changes `mode` to `NORMAL` atomically; generation unchanged. Never automatic.

## States

- Controller: `UNENROLLED` (no record), `NORMAL`, `RECOVERY_ONLY`, `FAULT` (record generation below `ledger.high_water`, e.g. a restored backup — all requests fail `CONTROLLER_STATE_ROLLBACK`).
- Enrollment window: `NONE`, `ARMED`, `CONSUMED`, `LOCKED_OUT`, `EXPIRED`.

```text
UNENROLLED --claim(no blockers)--> NORMAL
UNENROLLED --claim(blockers)-----> RECOVERY_ONLY
NORMAL/RECOVERY_ONLY --claim(active op)--> (unchanged)  TAKEOVER_DEFERRED_ACTIVE_OPERATION
NORMAL/RECOVERY_ONLY --claim(blockers)---> RECOVERY_ONLY (generation+1, old revoked)
NORMAL/RECOVERY_ONLY --claim(clean)------> NORMAL        (generation+1, old revoked)
RECOVERY_ONLY --recovery.complete(all clear)--> NORMAL   (same generation)
any --controller generation < high_water--> FAULT
NONE --boot consumes valid new ticket--> ARMED --commit--> CONSUMED
ARMED --5 bad proofs--> LOCKED_OUT ; ARMED --900 s or reboot--> EXPIRED
```

## Operation classes

- Normal writes (denied in RECOVERY_ONLY): `bundle.upload`, `bundle.admit`, `bundle.install`, `runtime.deploy`, `fpga.load`, `site.job.submit`, `site.settings.write`, `site.activation`.
- Recovery actions (allowed in both modes, explicit request): `status.read`, `site.diagnose`, `site.recover`, `outcome.reconcile`, `recovery.complete`.

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
- Physical attacker with the SD card or local console = owner by policy (B1/B2). A cloned SD card clones the credential; a hardware key store is a separate future decision.
- **G13 (new):** today the Gateway (`:18080`) write routes are not bound to the controller credential; the single-controller invariant therefore covers Bootstrap only until **P2A-2/P2B bind every PPU mutating surface to the current generation** (required by §6 fence and §7).
- Confidentiality: claim and P2A-1 traffic are integrity-protected only; TLS remains NOT_QUALIFIED. The wrapped credential is protected by the ticket key.

## 9. Test design and acceptance

Implemented now (reference model, Host-only, 35 cases): first enrollment; replacement station without the old computer/credential; serial labelled development; RECOVERY_ONLY for seal / UNKNOWN / Active Set recovery with full preservation; explicit recovery and reconciliation then NORMAL; lost-response retrieval; LAN cannot arm; runtime-written ticket ignored; malformed tickets; SD replay; expiry by time and reboot; proof failure lockout; nonce reuse and wrong device; deferral for Site Job, Bootstrap deployment and FPGA with zero side effects; explicit-request requirement; unenrolled and unknown operations; delete failure and full ledger; two stations racing the same ticket; restored-backup rollback fault; every crash point; and a document/model lock-step check.

LOM-P2A-2 exit (to be implemented, NOT_RUN): the same cases against the real boot unit, Bootstrap endpoints, atomic file records and Manager credential store v2, plus real fsync/rename crash injection, Gateway write binding (G13), concurrent HTTP races under the transition fence, PYNQ Python 3.10, and a separately approved hardware check of SD consumption on a Z2. Host-only PASS is never hardware PASS.
