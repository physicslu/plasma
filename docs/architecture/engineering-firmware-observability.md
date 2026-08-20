# Engineering Firmware Observability

Engineering Programming distinguishes firmware fingerprint traffic from binary firmware transfer in the operator-visible Job Log.

The canonical firmware fingerprint remains SHA-256.

```text
[FIRMWARE] CACHE CHECK ... SHA256 ... fingerprint only
```

means the browser sent metadata/fingerprint only. No firmware binary is implied.

```text
[FIRMWARE] CACHE MISS ...
[FIRMWARE] UPLOAD START ...
[FIRMWARE] UPLOAD COMPLETE ...
```

means the selected PPU session did not contain the firmware and the browser transferred the binary once.

```text
[FIRMWARE] CACHE HIT ... reference only · no binary upload
```

means the selected PPU session already contains the same SHA-256 image and Program/Verify may reuse the in-memory firmware.

Every Engineering Connect/Reconnect creates a new logical session and reports one of:

```text
[SESSION] NEW · fresh connection
[SESSION] NEW · previous firmware cache cleared
```

A reconnect invalidates the prior session cache, so the first subsequent Program/Verify must upload the firmware again after a cache miss.

Batch completion logs are aggregate outcomes rather than a generic `COMPLETE` marker:

```text
[BATCH] COMPLETE · success: SITE 1, SITE 2 · cancelled: — · failed: —
[BATCH] PARTIAL · success: SITE 1 · cancelled: SITE 2 · failed: —
[BATCH] CANCELLED · success: — · cancelled: SITE 1, SITE 2 · failed: —
[BATCH] FAILED · success: SITE 1 · cancelled: — · failed: SITE 2
```

These logs are observability only; server-side Provider rules remain authoritative for firmware cache scope, SHA validation, PPU-wide active-firmware lease enforcement, and Job state.
