# Plasma Web REST API Contract

## Scope

This document defines the browser-facing **Plasma Web REST API contract**. It is separate from:

- Plasma Protocol v3.3 / `PLASMA33`, the canonical PPU wire protocol;
- the Facility -> PPU -> Site domain contract;
- Engineering operator-log rendering and audit grammar;
- future Programming Recipe / Package semantics.

REST and wire contracts are versioned independently even when one architectural change intentionally updates both.

## Current contract version

The canonical Web REST contract is:

```text
rest_contract_version = "3"
```

`GET /api/node` publishes `rest_contract_version` independently from the fleet `contract_version`.

## Remote-write security contract

The backend secure REST boundary is implemented by `SecurePlasmaWebHandler`. Its deployment/browser activation is still pending; the current `plasma_web.gateway` entry point remains unchanged until identity transport and deployment configuration are completed.

When the secure boundary is active, protected requests authenticate a canonical Principal using:

```text
Authorization: Bearer <high-entropy-credential>
```

Authorization is permission-based and resource-scoped over Facility / PPU / Site. Role names such as `viewer`, `operator`, `engineer`, `admin`, and `service` are permission bundles rather than route-specific role checks.

Viewer is information read-only. In particular:

```text
GET status / Batch information = read-only information access
IC READ operation              = ppu.read execution permission
```

IC Read is not a Viewer permission because it drives hardware, consumes execution capacity, and can expose target contents.

State-changing requests under the secure boundary also require a durable command identity:

```text
Idempotency-Key: <command-id>
```

The server persists `principal_id + command_id` before execution. An identical completed retry returns the persisted HTTP response without executing the physical command again. Reusing the same key for a different request is rejected; a command whose admission remains in progress/ambiguous is fail-closed rather than blindly reissued.

Canonical security errors are:

```text
HTTP 401  E4101 AUTHENTICATION_REQUIRED
HTTP 403  E4102 AUTHORIZATION_DENIED
HTTP 409  E4103 COMMAND_REPLAY_CONFLICT
HTTP 409  E4104 COMMAND_IN_PROGRESS
```

Authentication must precede protected Provider/PPU resource lookup. Missing/invalid credentials do not create durable SQLite audit writes; this prevents unauthenticated traffic from turning `synchronous=FULL` audit persistence into microSD write amplification. Authenticated authorization denials and admitted command lifecycle events are durable-audited.

Browser CORS transport for `Authorization` and `Idempotency-Key`, standalone Zynq credential provisioning, optional Cloudflare/OIDC identity bridging, and deployment activation are intentionally deferred to the identity-integration slice. Until that wiring is active, the security boundary is not claimed as a deployed protection for the current Gateway entry point.

See [Remote Write Security Boundary](remote-write-security-boundary.md).

## Gateway communication settings

PMode and EMode share one persistent Gateway policy resource:

```text
GET  /api/settings/gateway
POST /api/settings/gateway
```

The writable POST body contains exactly:

```json
{
  "ppu_request_timeout_ms": 10000,
  "ppu_retry_count": 3
}
```

`revision` is server-owned. `ppu_response_budget_ms` is also server-owned, read-only, and derived from the configured attempt count plus Gateway communication backoff. Clients must not persist or POST the derived response budget.

Canonical GET semantics include:

```json
{
  "revision": 1,
  "ppu_request_timeout_ms": 10000,
  "ppu_retry_count": 3,
  "ppu_response_budget_ms": 47000
}
```

With the default policy, four 10-second attempts plus 1 s, 2 s, and 4 s backoff produce a 47-second Gateway response budget. The Browser may derive an outer HTTP transport watchdog from that response budget plus a transport margin; the Browser does not own a second PPU timeout/retry policy.

Each server-side Batch freezes the current persistent Gateway policy revision at START. Direct Engineering PPU status observations use the current Gateway settings for each request. Defaults, validation ranges, retry boundaries and failure containment are defined in [Gateway Communication and Recovery](gateway-communication-recovery.md).

## Engineering PPU status observation

Canonical status routes are:

```text
GET /api/engineering/targets/{facility_id}/{ppu_id}/api/status
GET /api/engineering/targets/{facility_id}/{ppu_id}/api/status?site={site_id}&job={job_id}
```

The Gateway owns the PPU request deadline, transient retry/backoff, stable communication error normalization, and response budget for these routes.

When transient PPU communication retries are exhausted, the Gateway returns:

```text
HTTP 503 Service Unavailable
E2001 CONNECTION_FAILED
or
E2002 CONNECTION_TIMEOUT
```

An HTTP 503 carrying one of these stable codes is proof that the Browser received a Gateway HTTP response. It is not evidence that the Gateway itself was unreachable. A Browser transport failure with no HTTP response is a different failure boundary and must not be collapsed into the same semantic state.

PPU-level status diagnostics distinguish provider completion from Gateway response writing. `engineering_ppu_status_ok` means the provider payload was obtained; `engineering_ppu_status_response_sent` means the Gateway handler response-write call returned. Neither event by itself proves end-to-end Browser receipt. See [Gateway Communication and Recovery](gateway-communication-recovery.md) for the diagnostic boundary and interpretation rules.

## Server-side Batch routes

```text
POST /api/batches
GET  /api/batches/{batch_id}
POST /api/batches/{batch_id}/cancel
POST /api/batches/{batch_id}/targets/{facility_id}/{ppu_id}/cancel
```

The browser-facing PMode and EMode action is whole-Batch ABORT. The PPU-target cancel route supports server/runtime containment and diagnostics; it must not be presented as permission to mutate Batch membership after START.

## Programming data model

Plasma separates source inputs from execution data.

```text
Programming Asset                    What data is supplied to the workflow?
    |
    +-- Image Asset
    +-- Key Asset
    +-- Option Asset
    +-- Serial Number Asset
    +-- Calibration Asset
    |
    v
Parser / normalizer
    |
    v
Normalized Image                    What bytes/sections are actually programmed to
                                    or verified against target IC memory?

Programming Recipe                  What should the PPU do?
                                    Separate control-plane concept; not an Asset.
```

A source file format is not the same thing as Asset semantics. For example, an Image Asset may eventually arrive as BIN, Intel HEX, S-Record or ELF. A Serial Number may arrive from a file today and from MES or an API later.

Current Asset types:

```text
image
key
option
serial_number
calibration
```

Declared Asset formats:

```text
binary
intel_hex
srec
elf
csv
text
json
pem
```

Only `asset_type=image` + `asset_format=binary` has an implemented normalizer today. Unsupported type/format combinations fail closed rather than pretending to be programmable Images.

## Engineering Programming Asset routes

For a selected Engineering target base:

```text
/api/engineering/targets/{facility_id}/{ppu_id}
```

REST v3 defines:

```text
POST .../api/programming-assets/check
POST .../api/programming-assets?session_id=...&name=...&type=...&format=...&sha256=...
```

The check request contains metadata/fingerprint only:

```json
{
  "session_id": "...",
  "asset_name": "target.bin",
  "asset_type": "image",
  "asset_format": "binary",
  "asset_size": 102400,
  "asset_sha256": "...64 lowercase hex characters..."
}
```

Canonical response:

```json
{
  "ok": true,
  "rest_contract_version": "3",
  "programming_asset": {
    "cache_hit": true,
    "asset_name": "target.bin",
    "asset_type": "image",
    "asset_format": "binary",
    "asset_size": 102400,
    "asset_sha256": "..."
  }
}
```

Binary/materialized Asset upload uses `application/octet-stream`. The endpoint's `type` and `format` query parameters describe semantics and serialization explicitly.

## Job submission

Engineering Program/Verify references a session-cached Asset:

```json
{
  "site_id": 1,
  "operation": "program",
  "session_id": "...",
  "asset_sha256": "..."
}
```

The Provider resolves that Asset, normalizes it into an execution Image, and sends the normalized Image over Plasma Protocol v3.3. Engineering Job submission does not resend cached Asset bytes.

Standalone/local inline Program/Verify may submit one materialized Asset directly:

```json
{
  "site_id": 1,
  "operation": "program",
  "asset_name": "target.bin",
  "asset_type": "image",
  "asset_format": "binary",
  "asset_sha256": "...",
  "asset_base64": "..."
}
```

The Gateway validates the Asset and normalizes it before creating the wire-level `JobRequest.image`.

A direct REST Job may declare an execution-owner token:

```json
{
  "site_id": 1,
  "operation": "erase",
  "execution_owner_id": "client-scoped-token"
}
```

The current Web `startJob()` client automatically supplies one random page-instance token and reuses it for direct Jobs issued from that loaded Browser page. This lets an existing direct multi-Site workflow express one logical execution owner while another Browser page or PC receives a different owner. A page reload creates a new token; it does not inherit ownership from Jobs that may still be active.

For Engineering routes the Gateway currently maps an explicit token to `execution_owner_kind=engineering_session`; for the standalone REST path it maps to `rest_client`. These names are execution-source labels only. The token is a concurrency label and is **not** an authenticated security identity or authorization credential.

If a raw REST Job omits `execution_owner_id`, the fixed Gateway process labels (`plasma-web`, `plasma-web-engineering`) are not trusted as client identity. The PPU fails closed by treating each such Job as a separate `rest_job` owner. Server-side PMode/EMode Batch execution uses immutable `batch_id` as its shared owner and does not depend on the Browser page token.

## PPU execution ownership conflict

The physical PPU is the backend admission authority. While one execution owner has submitting, queued, running or cancelling Jobs, a different owner cannot enter the same PPU.

Canonical conflict response:

```text
HTTP 409 Conflict
E4010 PPU_BUSY
```

The error payload includes `error_type=PPU_BUSY`, `recoverable=true`, and structured context containing the PPU identity plus active/requested owner identity. This is a control-plane admission conflict, not a manufacturing FAIL and not a Gateway reachability failure.

PPU STATUS exposes read-only operational ownership state under:

```text
ppu.execution.busy
ppu.execution.owner_kind
ppu.execution.owner_id
ppu.execution.active_job_count
```

See [PPU Execution Ownership](ppu-execution-ownership.md) for lease resolution and lifecycle semantics.

## Session and catalog fields

Canonical REST v3 fields include:

```text
GET /api/engineering/targets
  programming_asset_scope
  supported_asset_types
  supported_asset_formats
  implemented_normalizers

POST /api/engineering/session
  session.programming_asset_cache_scope
```

Current cache scope is:

```text
(connection session, facility_id, ppu_id)
```

A session/PPU may cache multiple Assets simultaneously. This is required for future workflows that combine an Image, Option data, credentials, Serial Number and calibration inputs.

## Concurrency authority

PPU execution ownership and Programming Image compatibility are separate constraints.

The primary control-plane invariant is:

```text
one PPU -> at most one active execution owner
```

Within one permitted execution owner, Program/Verify also enforces the existing shared-resource rule based on the **Normalized Image SHA**:

```text
Asset -> normalize -> Image SHA -> PPU-wide active Image lease
```

The execution-owner lease prevents unrelated Batch/client work from overlapping. The normalized-Image lease prevents multiple permitted Sites from concurrently programming different target Images while allowing Sites within one owner to share the same normalized Image.

## Serial Number

`serial_number` is a first-class Programming Asset type for per-device identity. It is distinct from security keys.

A Serial Number may eventually originate from MES, a database, API, generated allocation or operator input. It is normally per-device/per-Site and must not inherit PPU-wide Image-cache sharing semantics merely because both are Programming Assets.

Current Program/Verify does not consume Serial Number Assets directly; attempting to normalize a Serial Number as an Image is rejected.

## No legacy compatibility surface

Plasma is still in development and there is no external REST compatibility requirement. REST v3 therefore has one canonical vocabulary and does not preserve retired REST aliases.

New code must use Programming Asset fields/routes. The Gateway does not provide a second firmware-oriented REST contract or a Programming-Image REST alias layer.

## Contract boundaries

REST v3 does not change these domain invariants:

- Facility / PPU / Site identity;
- one-based `site_id`;
- Program = write-only semantics;
- selected Sites execute independently except for real shared-resource constraints;
- per-Site cancellation does not cancel unrelated Sites;
- Provider selection and hardware validation remain separate concerns.

Plasma Protocol v3.3 carries the **Normalized Image** execution representation using `image_size` and `image_sha256`; REST v3 carries the broader **Programming Asset** source/input representation.
