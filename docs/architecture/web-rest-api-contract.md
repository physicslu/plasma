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

Source Asset SHA is the cache identity. It is not necessarily the final PPU execution-resource identity.

Program/Verify concurrency is controlled by the **Normalized Image SHA**:

```text
Asset -> normalize -> Image SHA -> PPU-wide active Image lease
```

This prevents two Sites on one physical PPU from concurrently programming different target Images while allowing multiple Sites to share the same normalized Image.

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
