# Engineering Firmware Observability Test Plan

Required browser regression coverage:

1. First Program with a firmware image emits SHA-256 fingerprint-only cache check, cache miss, binary upload start, and binary upload complete logs.
2. Concurrent selected Sites share one upload.
3. Reusing the same firmware in the same Engineering session emits cache hit/reference-only log and performs no additional binary upload.
4. Reconnect emits a new-session log that states the previous firmware cache was cleared.
5. An independent Site cancel inside a multi-Site batch produces a PARTIAL aggregate summary while unaffected Sites continue independently.

Network request counts remain the source of truth for whether a binary upload occurred; operator logs must agree with those counts.
