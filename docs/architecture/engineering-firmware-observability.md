# Engineering Firmware and Operator Observability

Engineering Programming exposes one operator-visible audit stream. The log must let an engineer reconstruct **operator intent -> transport activity -> PPU activity -> system outcome** without guessing which layer produced an event.

## Event category contract

Every exported Engineering log entry carries exactly one first-level category before its functional tag:

```text
[USER]       explicit operator intent or UI action
[TRANSPORT]  Gateway, session, Provider, and firmware transport activity
[PPU]        PPU/Site command acceptance, cancellation, status/polling, and submission failures
[SYSTEM]     local target activation, batch orchestration, and aggregate outcomes
```

Examples:

```text
[USER] [TARGET] SELECT · mock-facility-02 / mock-facility-02-ppu-03
[USER] [SITE] SELECTION · SITE 1, SITE 3, SITE 5
[USER] [BATCH] EXECUTE · ERASE → PROGRAM → VERIFY · SITE 1, SITE 3, SITE 5

[TRANSPORT] [SESSION] NEW · previous firmware cache cleared · 6cc11d63…
[TRANSPORT] [FIRMWARE] CACHE MISS · SHA256 fbbab289f7f9…

[PPU] [SITE 1] PROGRAM accepted · job-...
[PPU] [SITE 3] Cancel requested · job-...

[SYSTEM] [BATCH] PARTIAL · success: SITE 1 · cancelled: SITE 3, SITE 5 · failed: —
```

The first category is intended to be machine-filterable. The second tag retains the functional meaning used by existing operator diagnostics.

The UI may filter categories for readability, but filtering is **view-only**. `Download .log` exports the complete retained session log, not only the currently visible categories. Engineering Programming retains up to 1000 newest-first events so normal acceptance flows do not silently lose their beginning.

## Firmware transport semantics

The canonical firmware fingerprint remains SHA-256.

```text
[TRANSPORT] [FIRMWARE] CACHE CHECK ... SHA256 ... fingerprint only
```

means the browser sent metadata/fingerprint only. No firmware binary is implied.

```text
[TRANSPORT] [FIRMWARE] CACHE MISS ...
[TRANSPORT] [FIRMWARE] UPLOAD START ...
[TRANSPORT] [FIRMWARE] UPLOAD COMPLETE ...
```

means the selected PPU session did not contain the firmware and the browser transferred the binary once.

```text
[TRANSPORT] [FIRMWARE] CACHE HIT ... reference only · no binary upload
```

means the selected PPU session already contains the same SHA-256 image and Program/Verify may reuse the in-memory firmware.

Every Engineering Connect/Reconnect creates a new logical session and reports one of:

```text
[TRANSPORT] [SESSION] NEW · fresh connection
[TRANSPORT] [SESSION] NEW · previous firmware cache cleared
```

A reconnect invalidates the prior session cache, so the first subsequent Program/Verify must upload the firmware again after a cache miss.

## Batch outcome semantics

Batch completion logs are aggregate system outcomes rather than a generic `COMPLETE` marker:

```text
[SYSTEM] [BATCH] COMPLETE · success: SITE 1, SITE 2 · cancelled: — · failed: —
[SYSTEM] [BATCH] PARTIAL · success: SITE 1 · cancelled: SITE 2 · failed: —
[SYSTEM] [BATCH] CANCELLED · success: — · cancelled: SITE 1, SITE 2 · failed: —
[SYSTEM] [BATCH] FAILED · success: SITE 1 · cancelled: — · failed: SITE 2
```

These logs are observability evidence, not the authority for behavior. Server-side Provider rules remain authoritative for firmware cache scope, SHA validation, PPU-wide active-firmware lease enforcement, and Job state.
