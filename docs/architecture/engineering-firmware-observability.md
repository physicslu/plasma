# Engineering Programming Data and Operator Observability

Engineering Programming exposes one operator-visible audit stream. The log must let an engineer reconstruct **operator intent -> network/session activity -> programming data activity -> PPU activity -> batch/system outcome** without guessing which layer produced an event.

## Event category contract

Every exported Engineering log entry carries exactly one fixed-width first-level category before its functional tag:

```text
[USR]  explicit operator intent or UI action
[NET]  Gateway, session, Provider, reconnect, and network activity
[PPU]  PPU/Site command acceptance, cancellation, status/polling, and submission failures
[DAT]  programming data validation/cache/transfer activity
[BAT]  batch orchestration and aggregate batch outcomes
[SYS]  other local system/target state and fallback activity
```

All first-level category fields are exactly three characters inside the brackets.

`DAT` is deliberately broader than firmware. Plasma programming jobs may consume multiple data assets over time, and those assets must not be forced into a firmware-only category.

The second-level data subtype identifies what kind of programming data is involved:

```text
[DAT] [IMG]  programming image / binary image
[DAT] [KEY]  serial, license, security, or provisioning key data
[DAT] [OPT]  option or configuration data
```

`IMG`, `KEY`, and `OPT` are presentation/observability subtypes. Internal protocol or Provider field names do not need to be renamed merely to match the operator log vocabulary.

## Fixed-width Site presentation

`site_id` remains an integer in APIs and internal models. Operator-visible Engineering UI and logs render Site identities with a fixed two-digit suffix:

```text
SITE-01
SITE-02
...
SITE-99
```

Plasma currently treats a PPU Site count above two digits as a product-specification change rather than silently expanding this presentation contract.

Examples:

```text
[USR] [TARGET] SELECT · mock-facility-02 / mock-facility-02-ppu-03
[USR] [SITE] SELECTION · SITE-01, SITE-03, SITE-05
[USR] [IMG] SELECT · plasma.bin · 1.00 MiB
[USR] [BATCH] EXECUTE · ERASE → PROGRAM → VERIFY · SITE-01, SITE-03, SITE-05

[NET] [SESSION] NEW · previous firmware cache cleared · 6cc11d63…
[DAT] [IMG] CACHE MISS · SHA256 fbbab289f7f9…
[DAT] [IMG] UPLOAD COMPLETE · plasma.bin · 1.00 MiB · SHA256 fbbab289f7f9…

[PPU] [SITE-01] PROGRAM accepted · job-...
[PPU] [SITE-03] Cancel requested · job-...

[BAT] [BATCH] PARTIAL · success: SITE-01 · cancelled: SITE-03, SITE-05 · failed: —
```

The first category is intended to be machine-filterable. The second tag retains the functional or data-subtype meaning used by operator diagnostics.

The UI may filter categories for readability, but filtering is **view-only**. `Download .log` exports the complete retained session log, not only the currently visible categories. Engineering Programming retains up to 1000 newest-first events so normal acceptance flows do not silently lose their beginning.

## Programming image transport semantics

The current `IMG` path is backed by the existing firmware-image transport implementation. The canonical image fingerprint remains SHA-256.

```text
[DAT] [IMG] CACHE CHECK ... SHA256 ... fingerprint only
```

means the browser sent metadata/fingerprint only. No image binary is implied.

```text
[DAT] [IMG] CACHE MISS ...
[DAT] [IMG] UPLOAD START ...
[DAT] [IMG] UPLOAD COMPLETE ...
```

means the selected PPU session did not contain the image and the browser transferred the binary once.

```text
[DAT] [IMG] CACHE HIT ... reference only · no binary upload
```

means the selected PPU session already contains the same SHA-256 image and Program/Verify may reuse the in-memory image.

Every Engineering Connect/Reconnect creates a new logical session and reports one of:

```text
[NET] [SESSION] NEW · fresh connection
[NET] [SESSION] NEW · previous firmware cache cleared
```

The session message preserves the existing server/cache vocabulary. A reconnect invalidates the prior image cache, so the first subsequent Program/Verify must upload the image again after a cache miss.

## Future programming data

Future data paths should extend the subtype layer rather than create new first-level categories for every artifact. For example:

```text
[USR] [KEY] SELECT · serial-keys.csv
[DAT] [KEY] VALIDATE · 100 records
[DAT] [KEY] ASSIGN · SITE-01 · record 000001

[USR] [OPT] SELECT · option.cfg
[DAT] [OPT] VALIDATE
[DAT] [OPT] TRANSFER · SITE-01
```

The actual source may be a file, MES/API response, database record, generated value, or another provider. `DAT` therefore describes the programming-data role rather than the storage medium.

## Batch outcome semantics

Batch completion logs are aggregate batch outcomes rather than a generic `COMPLETE` marker:

```text
[BAT] [BATCH] COMPLETE · success: SITE-01, SITE-02 · cancelled: — · failed: —
[BAT] [BATCH] PARTIAL · success: SITE-01 · cancelled: SITE-02 · failed: —
[BAT] [BATCH] CANCELLED · success: — · cancelled: SITE-01, SITE-02 · failed: —
[BAT] [BATCH] FAILED · success: SITE-01 · cancelled: — · failed: SITE-02
```

These logs are observability evidence, not the authority for behavior. Server-side Provider rules remain authoritative for image cache scope, SHA validation, PPU-wide active-image/firmware lease enforcement, and Job state.
