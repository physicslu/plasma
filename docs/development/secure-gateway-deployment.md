# Secure Gateway Deployment

Status: opt-in rollout path implemented by PR #168; PR #169 adds an initial entry identity/profile flow. Canonical `plasma-web.service` remains the default until the security drop-in is enabled.

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
6. tightens existing Gateway output / Programming Image / readback material so group/other permissions are removed;
7. installs a `plasma-web.service.d/security.conf` user-systemd drop-in;
8. restarts `plasma-web.service` through `plasma_web.secure_gateway_app`.

The launcher fails closed when the security config or an existing SQLite state/WAL/SHM file is not owned by the Gateway process user or is readable/writable by group/other users. Config and state paths must be different files.

The secure launcher keeps process `umask 077` for the Gateway lifetime so newly-created Programming Image material, Readback files, logs and security state are private by default. The deployment helper also hardens already-existing output material before secure mode starts.

The plaintext token is intentionally **not** written to the repository, deployment config, localStorage or sessionStorage.

Keep the displayed token in an appropriate credential manager. If it is lost, rotate the principal credential explicitly rather than trying to recover plaintext from the SHA-256 digest.

## Browser credential flow

The Web Console installs a passive security transport at the app shell. It does **not** add security headers to the existing canonical Gateway. A protected request must first receive the canonical secure-boundary response:

```text
HTTP 401 / E4101 AUTHENTICATION_REQUIRED
```

The `/demo` entry probes `GET /api/security/me`. On a secure deployment an unauthenticated probe receives `E4101`, activates the secure browser transport and shows the entry Security Profile flow. On a canonical non-secure Gateway the endpoint is absent and the existing landing-page behavior remains unchanged.

The entry offers four **expected test profiles**:

```text
Viewer
Operator
Engineer
Admin
```

Selecting a profile never grants authority. The user then enters a Bearer token and the browser calls:

```text
GET /api/security/me
Authorization: Bearer <token>
```

The backend returns the authenticated Principal's ID, roles, permissions and Facility / PPU / Site scopes. The entry displays those backend results and warns if they do not match the profile the user selected. All navigation gating is derived from the returned permissions, not from the selected profile.

`/demo` is the sole credential-input owner while the user is at the entry. The bottom-right `AUTH REQUIRED` / `AUTH READY` control remains available on PMode, EMode and other secured routes after leaving the entry. This avoids two competing credential inputs while preserving the #168 in-workspace recovery control.

The Bearer token remains only in JavaScript memory and is cleared by a full browser reload.

The external security store exposes a stable browser snapshot. Loading, replacing or clearing a credential advances an in-memory credential revision. Engineering sessions are bound to that revision, so a new credential cannot inherit the previous Principal's Engineering session. When a valid token is entered after `E4101`, Engineering initialization is retriggered automatically rather than requiring a manual Retry or page reload.

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
GET  /api/security/me                       -> 401 E4101 without credential
GET  /api/security/me + valid token         -> Principal / roles / permissions / scopes
POST /api/jobs                              -> 401 without credential
POST /api/jobs + valid token, no key        -> 400 / invalid argument
POST /api/jobs + valid token + valid key    -> authorized execution
Viewer execution permission                 -> 403
Out-of-scope Facility / PPU / Site           -> 403
Same key + identical completed request      -> persisted replay, no re-execution
Same key + changed request                   -> 409 E4103
Same key + in-progress/ambiguous command     -> 409 E4104
```

Entry/profile smoke test:

1. load `/demo` without a token and confirm the four expected profiles appear after `E4101` detection;
2. choose Viewer, Operator, Engineer or Admin and paste that test Principal's token;
3. confirm the displayed Principal, Role and Scope come from `/api/security/me`;
4. deliberately choose a profile that does not match the token and confirm the UI warns but does not alter backend permissions;
5. confirm Viewer cannot enter Engineering, while Operator/Engineer/Admin are gated according to their returned permission set;
6. confirm clearing identity returns the secure entry to `AUTH REQUIRED` without persisting the token or selected profile.

Workspace smoke test:

1. authenticate at `/demo` and enter PMode or EMode;
2. confirm status, Batch and permitted direct Job operations work;
3. perform one Read operation and download its BIN output through the authenticated download path;
4. replace the credential using the in-workspace AUTH control and confirm Engineering creates a fresh credential-bound session rather than reusing the previous Principal's session;
5. reload the page and confirm the credential is gone; the page redetects secure mode from `E4101` rather than from persisted browser state.

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
- permission-aware disabling inside every PMode / EMode control (the entry is permission-aware, but the backend remains authoritative for all direct REST access);
- credential rotation/revocation UX;
- centralized multi-PPU identity management through Plasma Manager.
