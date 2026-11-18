# LOM-P2A-2 P0 — Runtime kit self-check fix and controlled Runtime transaction close (Gate 1)

> Status: **Gate 1 implementation, Host-only + CI QEMU.** Owner approval 2026-11-10 covers code, tests, CI and a Draft PR only. **Not merged, not deployed. The Z2 journal, the Bootstrap API record and transaction `370e51bc99fa43329e974ee43a8fd319` are untouched. No recovery, enrollment, takeover, FPGA or DUT action was taken.**
> Policy: [ADR-0008](../adr/0008-local-owner-mode.md). Contracts: [P2A-0 enrollment spec](opf-local-owner-mode-p2a0-enrollment-spec.md), [P2A-2 Gate 1 report (G13)](opf-local-owner-mode-p2a2-gate1-20261109.md), [Bootstrap request authentication](../deployment/ppu-bootstrap-request-authentication.md).

## 1. Problem

The 2026-11-09 synchronized P2A-2 deployment activated Runtime `0.2.1-7e90f95bceb6` on the real Z2. The Coordinator transaction reached `runtime_active` and its journal names the Bootstrap API transaction `370e51bc99fa43329e974ee43a8fd319`.

The kit's post-install verifier (`scripts/plasmactl-z2-ps`, `verify_runtime`) then sent an **unsigned** HTTP POST PS loopback to the local Gateway. G13 correctly refused it (401). The kit therefore exited non-zero, and the Bootstrap API worker recorded `recovery_required / coordinator_result_unreconciled`.

Consequences on the device:

- every later Bootstrap deployment is refused;
- the Manager's Managed relay answers `ppu_platform_recovery_required`;
- a Recovery-Gated Takeover would commit `RECOVERY_ONLY`.

CI did not catch the failure because the QEMU kit path (`z2like-demo-qemu-kit.py`) never runs `plasmactl-z2-ps`.

## 2. Work 1 — kit self-check (read-only)

Owner decisions:

- the kit is not the controller;
- the kit performs no write of any kind, signed or unsigned;
- the kit never obtains the controller credential;
- the signed PS loopback stays with the SWPC Manager under the existing G13 contract;
- no second authentication mechanism and no RBAC, session or role system is added.

| Item | Implementation |
| --- | --- |
| New `scripts/ppu_runtime_local_readiness.py` (stdlib, Python ≥ 3.10) | Sends **GET only**. (1) `/api/health/ready` returns `alive`/`ready`. (2) `/api/auth/challenge` on the Gateway is served through the Bootstrap admission socket and returns a well-formed P2A-1 challenge with `controller_generation`. (3) That challenge's `device_id` equals the local Bootstrap `/v1/status` identity. A host-lab (unauthenticated) Gateway has no challenge route and fails. Evidence: `signed_ps_loopback: DELEGATED_TO_MANAGER_ACCEPTANCE`, `controller_credential_access: NONE`, `http_methods_used: [GET]`. |
| `scripts/plasmactl-z2-ps` `verify_runtime` | The unsigned `curl` POST loopback is deleted and the readiness tool is called instead. |
| Kit packaging | The tool ships in every kit assembly: `z2-ps-release.yml`, the QEMU workflow, `z2like-demo-qemu-build-kit.py`, `ppu-bootstrap-kit.py` (required file), `plasma_ppu.py`. CI path filters are updated. |

## 3. Work 2 — controlled close of one already-activated Runtime transaction

### Design

The close is one new authenticated Bootstrap operation, `POST /v1/deployment/reconcile`.

- **Operation class:** `deployment.reconcile`, a recovery action that requires an explicit request.
- **Owners and locks:** it runs inside the existing Bootstrap service and holds the API `mutation_lock` and the Coordinator's own `deployment.lock` flock (non-blocking) for the whole check.
- **No new coordinator:** no second Deployment Coordinator, no re-run, no re-send and no rollback.
- **Manager action:** `POST /api/registry/<alias>/bootstrap/deployment/reconcile`. The Manager runs one fresh PS loopback, signed under its controller credential through the existing G13 signer, and verifies the PPU response MAC. It then forwards the raw response bytes. The Manager decides nothing.
- **Loopback evidence:** the Bootstrap admission socket already MACs every Gateway response. It now also keeps a bounded, in-memory **receipt** of each MACed response: method, target, status, body SHA-256 and generation, never a secret. The close requires a receipt matching the forwarded bytes. **The Bootstrap never signs a Gateway write.**
- **No dead end:** after a crash or restart the receipts are gone, so the operator simply repeats the call.

### Checks (all inside both locks; any failure → HTTP 409 with a typed code and nothing written)

| # | Required condition | Refusal code |
| --- | --- | --- |
| 1 | API record `transaction_id` = request, `state = recovery_required`, `error_code = coordinator_result_unreconciled`, no deployment thread | `RECONCILE_TRANSACTION_MISMATCH`, `RECONCILE_STATE_NOT_ELIGIBLE`, `RECONCILE_DEPLOYMENT_ACTIVE` |
| 1 | Coordinator journal `api_transaction_id` = request | `RECONCILE_COORDINATOR_TRANSACTION_MISMATCH` |
| 2 | Journal `kind = ppu-runtime`, `state = runtime_active` | `RECONCILE_COORDINATOR_NOT_RUNTIME_ACTIVE` |
| 2 | Journal `transaction_id`, `release_id` and `artifact_sha256` equal the operator's explicit expectations | `RECONCILE_COORDINATOR_IDENTITY_MISMATCH` |
| 3 | `/opt/plasma/current` is a symlink to `releases/<release_id>` | `RECONCILE_CURRENT_RELEASE_MISMATCH` |
| 3 | `install/last-install.json` has `result PASS` and the same release and archive SHA-256 | `RECONCILE_INSTALL_EVIDENCE_MISMATCH` |
| 4 | Admission socket is a live socket of this process | `RECONCILE_ADMISSION_SOCKET_UNAVAILABLE` |
| 4 | Runtime execution lease is `idle` (Server up) | `RECONCILE_SERVER_NOT_IDLE` |
| 4 | Gateway `/api/health/ready` returns `alive`/`ready` | `RECONCILE_GATEWAY_NOT_READY` |
| 4 | Gateway `/api/auth/challenge` returns this device and the current controller generation | `RECONCILE_GATEWAY_NOT_BOUND_TO_CONTROLLER` |
| 5 | A G13-admitted PS loopback receipt exists: status 200, ≤ 300 s old, newer than the activation, current generation, and its body hash equals the forwarded response | `RECONCILE_LOOPBACK_NOT_ADMITTED` |
| 5 | The forwarded response is `ok`, PS endpoint/source and has a matching CRC | `RECONCILE_LOOPBACK_NOT_PASS` |
| 6 | No active operation (deployment, Site Job lease, FPGA reload fence) | `RECONCILE_ACTIVE_OPERATION` |
| 6 | No seal | `RECONCILE_SITE_SEALED` |
| 6 | No unobservable state | `RECONCILE_STATE_UNOBSERVABLE` |
| 6 | The only unknown outcome is this transaction | `RECONCILE_OTHER_UNKNOWN_OUTCOME` |
| 6 | Coordinator journal is in a safe state | `RECONCILE_COORDINATOR_UNSAFE` |
| 6 | No other Coordinator holds the lock | `RECONCILE_COORDINATOR_ACTIVE` |
| 7 | API record and journal bytes are unchanged between the first read and the commit | `RECONCILE_STATE_CHANGED` |

### Commit and crash safety

1. **Evidence record.** The operation first writes a new append-only evidence record, `deployment-reconciliations/<tx>.json` (root, 0600, atomic with fsync). It contains:
   - the verbatim original API record and its SHA-256;
   - the journal SHA-256 and the Coordinator identity;
   - every verified value: release, install evidence, Gateway readiness and challenge, lease, and the loopback receipt;
   - the controller generation, the time and the boot ID.
2. **API record.** It then sets `state` to the new terminal state **`reconciled`**.
   - `error_code`, `error` and `result` (`null`) are kept verbatim. The runner's success is never fabricated.
   - A `reconciliation` summary is added, including the SHA-256 of the evidence record.
   - The Coordinator journal is never written.

If the process crashes after the evidence record but before the API record, a repeat call reuses that record and never rewrites it. The record must name the same original API record SHA-256; anything else gives `RECONCILE_EVIDENCE_RECORD_CONFLICT`. If it crashes after the API record, the record stays `reconciled`; startup recovery leaves it unchanged, and a repeat call gives `RECONCILE_STATE_NOT_ELIGIBLE`.

Clients updated to accept `reconciled` as terminal: `ppu_deploy_api.py`, `plasma_ppu.py`, and the Web type.

### Residual (documented, not solved here)

A controller in `RECOVERY_ONLY` cannot produce the G13-admitted loopback, which is a normal write, so the close fails closed. Before the close, **no Enrollment or Takeover may happen**: a takeover while this transaction is `recovery_required` commits `RECOVERY_ONLY`, and `recovery.complete` is in turn blocked by the same transaction. The real Z2 controller is generation 1 `NORMAL`, so the close is reachable.

## 4. Tests

| Suite | Scope | Result (local) |
| --- | --- | --- |
| `test_lom_p2a2_p0_runtime_readiness.py` (15) | Readiness: enrolled / fresh PPU PASS with GET only; host-lab Gateway, missing admission socket, not ready and another device's identity each FAIL; CLI exit codes; no credential or write in the tool; kit no longer posts; every kit ships the tool. Manager signed loopback: normal with PPU proof, unsigned and wrong-key refused, revoked controller stops, forged response MAC rejected, restart keeps the credential and G13 | PASS |
| `test_lom_p2a2_p0_runtime_reconcile.py` (27) | Positive close (original error preserved, journal byte-identical, unknown outcome cleared, closes once). Negatives with byte-identical state: wrong tx, expected release, artifact or Coordinator ID, journal tx/kind/state, record state/error_code, current symlink, install evidence, Gateway not ready, busy lease, seal, Coordinator lock held, concurrent record change, never-admitted / pre-activation / failed loopback, receipt single-use, unsigned and revoked requests, `RECOVERY_ONLY` residual, strict request shape. Crash after evidence record → restart → completes with the same record; crash after API record → restart → stays reconciled; conflicting evidence record never overwritten | PASS |
| `test_lom_p2a2_p0_bootstrap_stdlib.py` (3) | **Python 3.10, stdlib only.** Plays the Gateway over the real admission socket protocol; close PASS; never-admitted proof refused; readiness tool PASS | PASS on 3.10.12 and 3.12 |
| Existing LOM / G13 / P2A-0 spec / reference equivalence / kit contract | Regression | PASS |
| CI QEMU `qemu-bootstrap-e2e` (extended) | ARMv7 QEMU: Manager → Bootstrap → Runtime → G13 → Manager. Then: kit readiness run inside the target (GET only); a **simulation-only fault injection** of the same record shape; Managed write blocked; mismatched close refused; close PASS; second close refused; Managed loopback resumes. The QEMU target Server now opens the same Runtime control socket as the Z2 unit | see PR |

## 5. Gate 2 maintenance procedure (NOT authorized by this document)

These steps run only after Gate 2 merge and a separate owner approval. They use the existing SSH/sudo channel and evidence conventions of the [P2A-1 runbook](../deployment/ppu-lom-p2a1-synchronized-deployment-runbook.md).

1. **Read-only re-gate**:
   - Z2 `/v1/status`: deployment `recovery_required`, `coordinator_result_unreconciled`, tx `370e51bc…`.
   - Journal `ppu-runtime` / `runtime_active`, `api_transaction_id` = tx. Record the Coordinator `transaction_id` (`2c544db1…`), `release_id` `0.2.1-7e90f95bceb6` and `artifact_sha256` (`6f2506a6…`).
   - Controller generation 1 `NORMAL`; no Job, seal or reload.
   - If anything differs, STOP.
2. **Refresh the Z2 Bootstrap** to the merged factory bundle (`--refresh-only`) and restart `plasma-bootstrap.service`. This is a script refresh only: the journal and the API record are untouched. The SWPC Manager/Console is deployed from the same merged SHA.
3. **One explicit close** from SWPC, run once:

   ```bash
   curl -X POST http://127.0.0.1:18280/api/registry/z2/bootstrap/deployment/reconcile \
     -H 'Content-Type: application/json' \
     -d '{"transaction_id":"370e51bc99fa43329e974ee43a8fd319","explicit_request":true,
          "expected":{"coordinator_transaction_id":"<from step 1>","release_id":"0.2.1-7e90f95bceb6",
                      "artifact_sha256":"<from step 1>"}}'
   ```

   - **409:** read the code; nothing was written; do not force.
   - **Transport error:** read `/v1/status` first. If the state is `reconciled`, stop. If it is still `recovery_required`, the call may be repeated.
4. **Post-check**:
   - status `reconciled` with the original error preserved;
   - evidence record present;
   - Managed PS loopback 200;
   - `plasma_program.py diagnose` no longer `BOOTSTRAP_DEPLOYMENT_BUSY`;
   - Active Set unchanged.
5. **Next step.** The Runtime kit fix takes effect at the **next** Runtime deployment. The installed Runtime is already `7e90f95bc` and is not redeployed by this procedure. Only after step 4 PASS: Engineering Ticket Enrollment and the real old-controller revocation acceptance.
