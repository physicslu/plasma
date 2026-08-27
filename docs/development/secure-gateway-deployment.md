# Secure Gateway Deployment

Status: opt-in rollout path implemented by PR #168; canonical `plasma-web.service` remains the default until the security drop-in is enabled.

## Purpose

The backend authorization model lives in `SecurePlasmaWebHandler`. The deployable launcher `plasma_web.secure_gateway_app` reuses the existing canonical Gateway, Batch runtime, Engineering Provider and Mock wiring, but substitutes the secure handler at process startup.

This keeps one REST implementation and makes rollback explicit: removing the systemd drop-in returns the service to `plasma_web.gateway` without deleting security configuration or audit state.

## Enable on SWPC / standalone PPU

From the Plasma repository:

```bash
chmod +x scripts/plasma-security-deploy
./scripts/plasma-security-deploy enable
```

On first enable the helper:

1. creates `~/.config/plasma/security.yaml` with mode `0600`;
2. generates a high-entropy `local-admin` Bearer token;
3. stores only the SHA-256 token digest in YAML;
4. prints the plaintext token once to the terminal;
5. configures `~/.local/state/plasma/security-state.sqlite3` as the durable command/audit store;
6. installs a `plasma-web.service.d/security.conf` user-systemd drop-in;
7. restarts `plasma-web.service` through `plasma_web.secure_gateway_app`.

The plaintext token is intentionally **not** written to the repository, deployment config, localStorage or sessionStorage.

Keep the displayed token in an appropriate credential manager. If it is lost, rotate the principal credential explicitly rather than trying to recover plaintext from the SHA-256 digest.

## Browser credential flow

The Web Console installs one security transport at the app shell. Click the bottom-right authentication control:

```text
AUTH OFF      no in-memory Bearer credential
AUTH READY    credential loaded in browser memory
AUTH REQUIRED Gateway returned HTTP 401
```

Paste the Bearer token when prompted. The token remains only in JavaScript memory and is cleared by a full browser reload.

For Plasma Gateway requests the browser transport:

- adds `Authorization: Bearer <token>` when a credential is loaded;
- adds `Idempotency-Key` to state-changing requests;
- preserves the same command identity across an ambiguous transport failure so an identical retry cannot issue a second physical command;
- never attaches the credential to arbitrary third-party URLs;
- converts protected Readback download links into authenticated `fetch()` downloads because normal `<a href>` navigation cannot carry the Authorization header.

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
./scripts/plasma-security-deploy status
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

1. load PMode or EMode without a token and confirm protected calls report authentication required;
2. load the local-admin token using the AUTH control;
3. confirm status, Batch and direct Job operations work;
4. perform one Read operation and download its BIN output through the authenticated download path;
5. reload the page and confirm the credential returns to `AUTH OFF` rather than being persisted.

## Roll back

```bash
./scripts/plasma-security-deploy disable
```

The helper removes only the systemd override and restarts `plasma-web.service` with the canonical Gateway entry point. It deliberately leaves these files intact:

```text
~/.config/plasma/security.yaml
~/.local/state/plasma/security-state.sqlite3
```

This prevents rollback from destroying credential configuration or audit/replay evidence.

## Security boundaries not included in this slice

The following remain separate follow-up work:

- Cloudflare Access / OIDC identity mapping;
- human login/session management beyond the local memory-only Bearer flow;
- UI controls that are proactively disabled from the resolved Principal permissions/roles;
- credential rotation/revocation UX;
- centralized multi-PPU identity management through Plasma Manager.
