# Engineering Programming Data and Operator Observability

Engineering Programming exposes one operator-visible audit stream. The log must let an engineer reconstruct **operator intent -> network/session activity -> programming data activity -> PPU activity -> batch/system outcome** without guessing which layer produced an event.

## Contract boundary

This document defines the **Engineering Programming observability/audit contract**. It is intentionally separate from Plasma Protocol v3.3 and Web REST v3.

Changing rendered audit grammar such as `[BAT] START` does not by itself require a Protocol or REST version change. Machine consumers must not treat rendered text as an application API; a future structured audit-event schema must be versioned explicitly.

## Event category contract

Every exported Engineering log entry carries exactly one fixed-width first-level category:

```text
[USR]  explicit operator intent or UI action
[NET]  Gateway, session, Provider, reconnect, and network activity
[PPU]  PPU/Site command acceptance, cancellation, status/polling, submission failures
[DAT]  Programming Asset validation/cache/transfer/assignment activity
[BAT]  batch orchestration and aggregate outcome
[SYS]  other local system/target state, restoration, fallback activity
```

A second bracket is used only when it adds information:

```text
[USR] [TARGET] ...
[USR] [SITE] ...
[NET] [SESSION] ...
[PPU] [SITE-01] ...
[DAT] [IMG] ...
[DAT] [KEY] ...
[DAT] [OPT] ...
[DAT] [SERIAL] ...
[SYS] [TARGET] ...
[SYS] [SITE] ...
[BAT] START ...
[BAT] COMPLETE ...
```

`BAT` is intentionally single-level. `[BAT] [BATCH]` is redundant and not part of the grammar.

`DAT` is broader than Image. Programming workflows may consume multiple Asset types and should not create a new first-level category for each one.

Data subtypes:

```text
[DAT] [IMG]     Image Asset / normalized Image-related activity
[DAT] [KEY]     security credential / provisioning key activity
[DAT] [OPT]     option / configuration activity
[DAT] [SERIAL]  per-device Serial Number activity
```

Serial Number is deliberately not classified as Key.

## Fixed-width Site presentation

`site_id` remains an integer in APIs/internal models. Operator-visible Engineering UI/logs render:

```text
SITE-01
SITE-02
...
SITE-99
```

A PPU Site count above two digits is treated as a product-specification change rather than silently expanding this presentation contract.

Examples:

```text
[USR] [TARGET] SELECT · mock-facility-02 / mock-facility-02-ppu-03
[USR] [SITE] SELECTION · SITE-01, SITE-03, SITE-05
[USR] [IMG] SELECT · application.bin · 1.00 MiB
[USR] [BATCH] EXECUTE · ERASE → PROGRAM → VERIFY · SITE-01, SITE-03, SITE-05

[NET] [SESSION] NEW · previous Programming Asset cache cleared · 6cc11d63…
[SYS] [TARGET] RESTORED · mock-facility-02 / mock-facility-02-ppu-03
[SYS] [SITE] RESTORED · SITE-01, SITE-03, SITE-05

[DAT] [IMG] CACHE MISS · SHA256 fbbab289f7f9…
[DAT] [IMG] UPLOAD COMPLETE · application.bin · 1.00 MiB · SHA256 fbbab289f7f9…

[PPU] [SITE-01] PROGRAM accepted · job-...
[PPU] [SITE-03] Cancel requested · job-...

[BAT] PARTIAL · success: SITE-01 · cancelled: SITE-03, SITE-05 · failed: —
```

UI filtering is view-only. `Download .log` exports the complete retained session log, not only visible categories. Engineering Programming retains up to 1000 newest-first events.

## Reconnect restoration evidence

Reconnect snapshots durable target identity and explicit Site selection before transport state is reset. After the new catalog arrives, restoration evidence is emitted only if the original target still exists:

```text
[SYS] [TARGET] RESTORED · <facility_id> / <ppu_id>
```

After first successful status poll:

```text
[SYS] [SITE] RESTORED · SITE-02, SITE-04, SITE-06
```

Explicit zero-Site selection is valid:

```text
[SYS] [SITE] RESTORED · none
```

`RESTORED` must not be emitted for fresh connection, deliberate target switch, or fallback because the original PPU disappeared.

## Image Asset transport semantics

Current `[IMG]` path uses Web REST v3 Programming Asset transport.

```text
[DAT] [IMG] CACHE CHECK ... SHA256 ... fingerprint only
```

means only Asset metadata/fingerprint was sent.

```text
[DAT] [IMG] CACHE MISS ...
[DAT] [IMG] UPLOAD START ...
[DAT] [IMG] UPLOAD COMPLETE ...
```

means the selected session/PPU did not contain that Image Asset and source data was transferred once.

```text
[DAT] [IMG] CACHE HIT ... reference only · no binary upload
```

means the same source Asset is already materialized in that session/PPU.

Every Connect/Reconnect creates a logical session and reports one of:

```text
[NET] [SESSION] NEW · fresh connection
[NET] [SESSION] NEW · previous Programming Asset cache cleared
```

A reconnect invalidates the previous session Asset cache.

## Asset cache vs execution Image authority

Operator logs must not imply that source Asset identity is always the PPU execution-resource identity.

```text
Asset SHA
    |
    | normalize
    v
Normalized Image SHA
    |
    v
PPU-wide active Image lease
```

Program/Verify concurrency authority is the Normalized Image SHA because it represents target-memory data. Different source files may later normalize to the same Image.

## Future Programming Assets

Future data paths extend the subtype layer:

```text
[USR] [SERIAL] SOURCE · MES
[DAT] [SERIAL] ASSIGN · SITE-01 · SN-000001
[DAT] [SERIAL] ASSIGN · SITE-02 · SN-000002

[USR] [KEY] SELECT · provisioning-key.pem
[DAT] [KEY] VALIDATE
[DAT] [KEY] ASSIGN · SITE-01

[USR] [OPT] SELECT · option.csv
[DAT] [OPT] VALIDATE
[DAT] [OPT] TRANSFER · SITE-01
```

The source may be file, MES/API response, database record, generated value, secure store or another Provider. `DAT` describes programming-data role rather than storage medium.

Programming Recipe activity, once implemented, should be designed as control-plane observability rather than misclassified as an Asset solely because a recipe may be serialized in a file.

## Batch outcome semantics

```text
[BAT] START ERASE → PROGRAM → VERIFY · SITE-01, SITE-02
[BAT] COMPLETE · success: SITE-01, SITE-02
[BAT] PARTIAL · success: SITE-01 · cancelled: SITE-02
[BAT] CANCELLED · cancelled: SITE-01, SITE-02
[BAT] FAILED · success: SITE-01 · failed: SITE-02
```

Rendered operator logs omit empty outcome groups. Machine-readable Batch results keep their complete structured fields; consumers must not infer schema from rendered text.

These logs are evidence, not behavioral authority. Provider/Server rules remain authoritative for Asset cache scope, SHA validation, Normalized Image lease enforcement, and Job state.
