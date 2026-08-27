# Remote Write Security Boundary

Status: backend security boundary implemented in `SecurePlasmaWebHandler`; deployment/browser activation remains pending

## Security invariant

A Plasma state-changing command must not reach a Batch runtime or PPU unless all of the following are true:

```text
caller identity authenticated
        ↓
requested action authorized
        ↓
Facility / PPU / Site inside principal scope
        ↓
command has durable Idempotency-Key identity
        ↓
command admitted to audit/replay ledger
        ↓
execution
```

PMode and EMode are workflow/UI concepts. They are not authorization boundaries. A caller using direct REST or curl must receive the same authorization decision as a browser.

## Principal and permission model

The backend authorizes permissions, not role-name branches. Roles are only predefined permission bundles.

Current bundles are:

- `viewer`
- `operator`
- `engineer`
- `admin`
- `service`

A principal may also receive explicit permissions in addition to role bundles.

### Viewer / read-only contract

`viewer` is information read-only. Its default permissions are:

```text
status.read
batch.read
catalog.read
settings.read
programming_asset.read
```

Viewer does **not** receive any execution permission.

In particular:

```text
HTTP GET /api/status    = information read
IC operation READ       = ppu.read execution
```

These are deliberately different. IC Read drives hardware, occupies PPU/Site execution capacity, and may expose target contents, so it is not granted to Viewer.

Programming/readback output files are also protected separately by `job.output.read` and are not part of the default Viewer bundle.

## Execution and write permissions

Current executable/write permissions include:

```text
batch.start
batch.cancel
job.cancel
ppu.erase
ppu.program
ppu.verify
ppu.read
programming_asset.write
engineering.session.write
settings.gateway.write
settings.mock.write
```

Batch authorization is two-dimensional:

1. the principal must have `batch.start`;
2. the principal must also have the permission for every operation in the Batch and scope access to every target Site.

A principal that may start Batches but lacks `ppu.program` cannot use Batch as a bypass around Program authorization.

## Resource scopes

Each principal has one or more scopes over:

```text
Facility
  └─ PPU
      └─ Site
```

`*` means all resources at that level. Site scopes can be an explicit list.

Example:

```yaml
scopes:
  - facility_id: factory-a
    ppu_id: ppu-03
    site_ids: [1, 2, 3, 4]
```

The permission and resource scope must both pass.

## Authentication credential boundary

The backend security config accepts high-entropy Bearer credentials. The configuration stores only SHA-256 token digests, not plaintext tokens.

This SHA-256 design is for random API/service tokens with sufficient entropy. It is **not** a password storage algorithm and must not be reused for human passwords.

Credential comparison uses constant-time digest comparison.

The first backend slice does not yet define the browser login/session flow or Cloudflare/OIDC bridge. Those are deployment/identity integration concerns and must map their authenticated identity into the same canonical Principal model.

## Idempotency and replay protection

Every state-changing request handled by the secure boundary requires:

```text
Idempotency-Key: <command-id>
```

The durable security SQLite store keys command identity by:

```text
principal_id + command_id
```

and records the request digest, method, path, action and resource context before execution.

The rules are:

```text
new key + authorized command
    -> durable state = started
    -> execute once
    -> persist HTTP result as completed

same key + identical completed command
    -> return persisted response
    -> DO NOT execute again

same key + different request/resource
    -> E4103 COMMAND_REPLAY_CONFLICT / HTTP 409

same key + command still started or requiring reconciliation
    -> E4104 COMMAND_IN_PROGRESS / HTTP 409
    -> fail closed; DO NOT issue another physical command
```

No TTL is used to steal an in-progress command identity. Long hardware operations can be valid; time alone is not proof that replay is safe.

## Audit ledger

The security state database uses SQLite with WAL and `synchronous=FULL` and records:

- authenticated principal ID;
- authorization decision;
- action/permission;
- method and path;
- resource context;
- Idempotency-Key command ID;
- command lifecycle and returned HTTP response.

Bearer tokens are never written to the audit database.

The audit ledger records control-plane decisions. It does not replace Batch/Job execution truth or PPU authoritative state.

## HTTP errors

Security-specific REST semantics are:

```text
401 / E4101 AUTHENTICATION_REQUIRED
403 / E4102 AUTHORIZATION_DENIED
409 / E4103 COMMAND_REPLAY_CONFLICT
409 / E4104 COMMAND_IN_PROGRESS
```

Authentication failure and authorization denial are intentionally distinct.

## Zynq / embedded constraint

The design is intentionally embedded-grade:

- no Keycloak/PostgreSQL/Redis requirement on the PPU;
- token verification is local and lightweight;
- authorization is an in-memory permission/scope check;
- SQLite durable writes occur at command/audit boundaries, not every progress update;
- an external identity provider may supply identity, but standalone PPU authorization must not depend on Plasma Manager or Internet availability.

## Deployment status

`SecurePlasmaWebHandler` currently composes and protects the canonical REST routes, but the existing `plasma_web.gateway` deployment entry remains unchanged in this backend slice.

The next security integration must provide:

- browser/session identity transport;
- local standalone Zynq credential flow;
- optional Cloudflare Access/OIDC identity bridge;
- CORS support for authentication/idempotency headers;
- `plasmactl` security configuration and state paths;
- UI read-only indication and disabled write controls;
- deployment smoke tests proving unauthenticated/direct REST writes cannot bypass the secure handler.

Until that deployment wiring is merged and enabled, Remote Write Authentication / Authorization remains open architecture debt.
