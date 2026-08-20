# Plasma Web REST API Contract

## Scope

This document defines the browser-facing **Plasma Web REST API contract**. It is separate from:

- Plasma Protocol v3.2 / `PLASMA32`, which is the PPU wire protocol;
- the Facility -> PPU -> Site domain contract;
- Engineering operator-log rendering and audit grammar.

A REST shape or semantic change may therefore require a REST contract migration without changing Plasma Protocol v3.2.

## Current contract version

The canonical Web REST contract is:

```text
rest_contract_version = "2"
```

`GET /api/node` publishes `rest_contract_version` independently from the existing fleet `contract_version`.

Engineering catalog and session responses also publish the REST contract version so browser diagnostics can establish the active HTTP contract without inferring it from route behavior.

## Programming Image terminology

REST v2 uses **Programming Image** for binary data consumed by Program/Verify operations.

This is intentionally narrower than the observability category `[DAT]`, because future programming data may also include keys, options or configuration records. Those data types are not represented as binary programming images merely for naming convenience.

Canonical REST v2 terminology:

```text
Programming Image
image_name
image_size
image_sha256
image_base64
programming_image_scope
programming_image_cache_scope
```

The current Provider and Plasma Protocol v3.2 may still use internal `firmware` names. That internal compatibility vocabulary is not the canonical Web REST surface.

## Engineering Programming Image routes

For a selected Engineering target base:

```text
/api/engineering/targets/{facility_id}/{ppu_id}
```

REST v2 defines:

```text
POST .../api/programming-images/check
POST .../api/programming-images?session_id=...&name=...&sha256=...
```

The check request contains only the fingerprint:

```json
{
  "session_id": "...",
  "image_name": "target.bin",
  "image_size": 102400,
  "image_sha256": "...64 lowercase hex characters..."
}
```

The canonical response contains `programming_image`:

```json
{
  "ok": true,
  "rest_contract_version": "2",
  "programming_image": {
    "cache_hit": true,
    "image_name": "target.bin",
    "image_size": 102400,
    "image_sha256": "..."
  }
}
```

The binary upload uses `application/octet-stream`. Query parameters `name` and `sha256` remain generic because the route already establishes Programming Image semantics.

## Job submission

Canonical REST v2 job bodies use Programming Image field names.

Engineering Program/Verify references a session-cached image:

```json
{
  "site_id": 1,
  "operation": "program",
  "session_id": "...",
  "image_name": "target.bin",
  "image_sha256": "..."
}
```

Standalone/local inline Program/Verify uses:

```json
{
  "site_id": 1,
  "operation": "program",
  "image_name": "target.bin",
  "image_base64": "..."
}
```

Engineering job submissions must not resend cached image bytes.

## Session and catalog fields

Canonical REST v2 fields are:

```text
GET /api/engineering/targets
  programming_image_scope

POST /api/engineering/session
  session.programming_image_cache_scope
```

The current scope remains:

```text
(connection session, facility_id, ppu_id)
```

## Compatibility aliases

REST v2 is a compatibility migration rather than a flag-day break.

The Gateway temporarily accepts and returns the prior firmware vocabulary:

```text
/api/firmware/check
/api/firmware
firmware_name
firmware_size
firmware_sha256
firmware_base64
firmware_scope
firmware_cache_scope
```

These names are **legacy REST aliases**, not canonical fields for new code.

Rules:

1. The Plasma Web client must emit only REST v2 Programming Image routes and fields.
2. Legacy clients may continue using firmware aliases during the compatibility window.
3. If one request supplies both canonical and legacy names with different values, the Gateway rejects the request rather than guessing which value wins.
4. REST v2 responses may include the legacy aliases during migration, but machine consumers must prefer the canonical Programming Image fields.
5. Removal of legacy aliases is a future explicit compatibility decision and must not happen silently.

## Contract boundaries

This REST migration does **not** change:

- Plasma Protocol v3.2;
- `JobRequest.firmware` or other protocol/internal compatibility fields;
- Facility / PPU / Site identity;
- one-based `site_id`;
- Program = write-only semantics;
- PPU-wide same-image concurrency rules;
- Provider selection or hardware behavior.

The purpose of REST v2 is to stop exposing a firmware-specific browser contract while preserving the stable PPU execution protocol beneath it.
