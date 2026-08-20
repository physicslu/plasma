# Engineering Firmware and Operator Observability

Engineering Programming exposes one operator-visible audit stream. The log must let an engineer reconstruct **operator intent -> network/session activity -> firmware activity -> PPU activity -> batch/system outcome** without guessing which layer produced an event.

## Event category contract

Every exported Engineering log entry carries exactly one fixed-width first-level category before its functional tag:

```text
[USR]  explicit operator intent or UI action
[NET]  Gateway, session, Provider, reconnect, and network activity
[PPU]  PPU/Site command acceptance, cancellation, status/polling, and submission failures
[FW ]  firmware fingerprint/cache/upload transport activity
[BAT]  batch orchestration and aggregate batch outcomes
[SYS]  other local system/target state and fallback activity
```

All category fields are exactly three characters inside the brackets. `FW` is intentionally padded as `[FW ]` so log columns remain visually aligned.

Site presentation is also fixed width. `site_id` remains an integer in APIs and internal models, but operator-visible UI/log text renders the two-digit form:

```text
SITE 01
SITE 02
...
SITE 99
```

Plasma currently treats a PPU Site count above two digits as a product-specification change rather than silently expanding this presentation contract.

Examples:

```text
[USR] [TARGET] SELECT · mock-facility-02 / mock-facility-02-ppu-03
[USR] [SITE] SELECTION · SITE 01, SITE 03, SITE 05
[USR] [BATCH] EXECUTE · ERASE → PROGRAM → VERIFY · SITE 01, SITE 03, SITE 05

[NET] [SESSION] NEW · previous firmware cache cleared · 6cc11d63…
[FW ] [FIRMWARE] CACHE MISS · SHA256 fbbab289f7f9…

[PPU] [SITE 01] PROGRAM accepted · job-...
[PPU] [SITE 03] Cancel requested · job-...

[BAT] [BATCH] PARTIAL · success: SITE 01 · cancelled: SITE 03, SITE 05 · failed: —
```

The first category is intended to be machine-filterable. The second tag retains the functional meaning used by operator diagnostics.

The UI may filter categories for readability, but filtering is **view-only**. `Download .log` exports the complete retained session log, not only the currently visible categories. Engineering Programming retains up to 1000 newest-first events so normal acceptance flows do not silently lose their beginning.

## Firmware transport semantics

The canonical firmware fingerprint remains SHA-256.

```text
[FW ] [FIRMWARE] CACHE CHECK ... SHA256 ... fingerprint only
```

means the browser sent metadata/fingerprint only. No firmware binary is implied.

```text
[FW ] [FIRMWARE] CACHE MISS ...
[FW ] [FIRMWARE] UPLOAD START ...
[FW ] [FIRMWARE] UPLOAD COMPLETE ...
```

means the selected PPU session did not contain the firmware and the browser transferred the binary once.

```text
[FW ] [FIRMWARE] CACHE HIT ... reference only · no binary upload
```

means the selected PPU session already contains the same SHA-256 image and Program/Verify may reuse the in-memory firmware.

Every Engineering Connect/Reconnect creates a new logical session and reports one of:

```text
[NET] [SESSION] NEW · fresh connection
[NET] [SESSION] NEW · previous firmware cache cleared
```

A reconnect invalidates the prior session cache, so the first subsequent Program/Verify must upload the firmware again after a cache miss.

## Batch outcome semantics

Batch completion logs are aggregate batch outcomes rather than a generic `COMPLETE` marker:

```text
[BAT] [BATCH] COMPLETE · success: SITE 01, SITE 02 · cancelled: — · failed: —
[BAT] [BATCH] PARTIAL · success: SITE 01 · cancelled: SITE 02 · failed: —
[BAT] [BATCH] CANCELLED · success: — · cancelled: SITE 01, SITE 02 · failed: —
[BAT] [BATCH] FAILED · success: SITE 01 · cancelled: — · failed: SITE 02
```

These logs are observability evidence, not the authority for behavior. Server-side Provider rules remain authoritative for firmware cache scope, SHA validation, PPU-wide active-firmware lease enforcement, and Job state.
