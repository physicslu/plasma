# Secure Gateway Deployment

Status: opt-in rollout path implemented by PR #168; canonical `plasma-web.service` remains the default until the security drop-in is enabled.

## Purpose

The backend authorization model lives in `SecurePlasmaWebHandler`. The deployable launcher `plasma_web.secure_gateway_app` reuses the existing canonical Gateway, Batch runtime, Engineering Provider and Mock wiring, but substitutes the secure handler at process startup.

This keeps one REST implementation and makes rollback explicit: removing the systemd drop-in returns the service to `plasma_web.gateway` without deleting security configuration or audit state.

## Enable on SWPC / standalone PPU

From the Plasma repository:

```bash
bash scripts/plasma-security-deploy enable
```

On first enable the helper:

1. creates `~/.config/plasma/security.yaml` with mode `0600`;
2. generates a high-entropy `local-admin` Bearer token;
3. stores only the SHA-256 token digest in YAML;
4. prints the plaintext token once to the terminal;
5. configures `~/.local/state/plasma/security-state.sqlite3` as the durable command/audit store;
6. installs a `plasma-web.service.d/security.conf` user-systemd drop-in;
7. restarts `plasma-web.service` through `plasma_web.secure_gateway_app`.

The launcher fails closed when the security config or an existing SQLite state/WAL/SHM file is not owned by the Gateway process user or is readable/writable by group/other users. Config and state paths must be different files.

The plaintext token is intentionally **not** written to the repository, deployment config, localStorage or sessionStorage.

Keep the displayed token in an appropriate credential manager. If it is lost, rotate the principal credential explicitly rather than trying to recover plaintext from the SHA-256 digest.

## Browser credential flow

The Web Console installs a passive security transport at the app shell. It does **not** add security headers to the existing canonical Gateway. A protected request must first receive the canonical secure-boundary response:

```text
HTTP 401 / E4101 AUTHENTICATION_REQUIRED
```

Only then does that browser page mark the selected Gateway as secure and show the bottom-right authentication control:

```text
AUTH REQUIRED secure boundary detected; no valid in-memory credential
AUTH READY    credential loaded in browser memory
```

This detection rule is part of the rollback boundary: an ordinary non-secure Gateway keeps its existing request/CORS behavior and does not receive `Authorization` or `Idempotency-Key` headers from this transport.

Enter the Bearer token through the masked password dialog. The token remains only in JavaScript memory and is cleared by a full browser reload.

Once secure mode has been detected, Plasma Gateway requests:

- add `Authorization: Bearer <token>` when a credential is loaded;
- add `Idempotency-Key` to state-changing requests;
- preserve the same command identity after an ambiguous network/transport failure;
- preserve the same command identity after `409 / E4104 COMMAND_IN_PROGRESS`;
- release the command identity after completed responses, authorization/input failures, `E4103`, `PPU_BUSY`, and other non-ambiguous `409` responses so a later legitimate retry can obtain a new command ID;
- never attach the credential to arbitrary third-party URLs;
- convert protected Readback download links into authenticated `fetch()` downloads because normal `<a href>` navigation cannot carry the Authorization header.

## CORS

Secure deployment allows the browser preflight headers required by the security boundary:

```text
Content-Type
Authorization
Idempotency-Key
```

The configured origin policy remains the same `--cors-origin` policy used by the canonical Gateway.

## Verify

After enable:

```bash
bash scripts/plasma-security-deploy status
systemctl --user status plasma-web.service
```

Expected REST behavior:

```text
GET  /api/health/live                       -> 200 without credential
POST /api/jobs                              -> 401 without credential
POST /api/jobs + valid token, no key        -> 400 / invalid argument
POST /api/jobs + valid token + valid key    -> authorized execution
Viewer execution permission                 -> 403
Out-of-scope Facility / PPU / Site           -> 403
Same key + identical completed request      -> persisted replay, no re-execution
Same key + changed request                   -> 409 E4103
Same key + in-progress/ambiguous command     -> 409 E4104
```

Browser smoke test:

1. load PMode or EMode without a token and confirm a protected call returns authentication required;
2. confirm the `AUTH REQUIRED` control appears only after that `E4101` response;
3. load the local-admin token using the masked AUTH dialog;
4. confirm status, Batch and direct Job operations work;
5. perform one Read operation and download its BIN output through the authenticated download path;
6. reload the page and confirm the credential is gone; the page redetects secure mode from `E4101` rather than from persisted browser state.

## Roll back

```bash
bash scripts/plasma-security-deploy disable
```

The helper removes only the systemd override and restarts `plasma-web.service` with the canonical Gateway entry point. It deliberately leaves these files intact:

```text
~/.config/plasma/security.yaml
~/.local/state/plasma/security-state.sqlite3
```

This prevents rollback from destroying credential configuration or audit/replay evidence.

After disabling secure mode, perform a full browser reload. Security detection and Bearer credentials are intentionally page-memory state; reload clears them and restores the canonical Gateway's original cross-origin header behavior.

## Security boundaries not included in this slice

The following remain separate follow-up work:

- Cloudflare Access / OIDC identity mapping;
- human login/session management beyond the local memory-only Bearer flow;
- UI controls that are proactively disabled from the resolved Principal permissions/roles;
- credential rotation/revocation UX;
- centralized multi-PPU identity management through Plasma Manager.
