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

The secure handler also treats unknown `/api` routes as denied rather than inheriting a newly-added canonical route without an explicit authorization rule. This prevents future Gateway route growth from silently creating an authentication/authorization bypass.

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

Each principal must declare one or more explicit scopes over:

```text
Facility
  └─ PPU
      └─ Site
```

Omitting `scopes` is a configuration error. The security config never turns a missing scope into an implicit global grant.

`*` means all resources at that level. Site scopes can be an explicit list.

Example:

```yaml
scopes:
  - facility_id: factory-a
    ppu_id: ppu-03
    site_ids: [1, 2, 3, 4]
```

The permission and resource scope must both pass.

Scopes are hierarchical. A Site-limited scope identifies its containing PPU as an addressable parent resource so the caller can use PPU-level metadata and shared resources required by its authorized Sites, such as the Programming Asset cache. This does **not** grant execution access to sibling Sites: every Site execution command is still checked against the exact normalized Site ID.

Any PPU-level response that contains Site-level state is filtered at the secure boundary. For example, `GET /api/status` may address the parent PPU, but a principal scoped to Sites 1 and 2 receives only Sites 1 and 2 in the returned Site list. Likewise, the Engineering target catalog is filtered to Facilities/PPUs that intersect the caller's scope.

Security resource parsing uses the same canonical Site parser as the inherited Gateway routes. Decimal string Site IDs such as `"3"` are normalized before authorization, so a caller cannot bypass Site scope by changing the JSON representation from integer `3` to string `"3"`.

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

The security state database uses SQLite with WAL and `synchronous=FULL` and records authenticated control-plane decisions such as:

- authenticated principal ID;
- authorization denial;
- admitted/replayed command action;
- method and path;
- resource context;
- Idempotency-Key command ID;
- command lifecycle and returned HTTP response.

Bearer tokens are never written to the audit database.

**Unauthenticated traffic is deliberately not written to the durable SQLite audit ledger.** Missing or invalid credentials return `E4101` and may be emitted as non-durable runtime diagnostics, but an unauthenticated remote caller must not be able to force one `synchronous=FULL` microSD write per bad request. This is an embedded DoS/write-amplification boundary, not an omission of authorization auditability.

Once a Principal has been authenticated, authorization denials and admitted command lifecycle events are durable-audited.

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
- unauthenticated failures do not trigger durable SQLite writes;
- SQLite durable writes occur at authenticated command/audit boundaries, not every progress update;
- an external identity provider may supply identity, but standalone PPU authorization must not depend on Plasma Manager or Internet availability.

## Deployment status

`SecurePlasmaWebHandler` currently composes and protects the canonical REST routes, but the existing `plasma_web.gateway` deployment entry remains unchanged in this backend slice.

The next security integration must provide:

- browser/session identity transport;
- local standalone Zynq credential flow;
- optional Cloudflare Access/OIDC identity bridge;
- CORS support for authentication/idempotency headers;
- `plasmactl` security configuration and state paths;
- owner-only filesystem permissions for security config/state and persisted Programming Image material;
- UI read-only indication and disabled write controls;
- deployment smoke tests proving unauthenticated/direct REST writes cannot bypass the secure handler.

Until that deployment wiring is merged and enabled, Remote Write Authentication / Authorization remains open architecture debt.
