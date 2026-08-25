# Engineering Programming Image Observability Test Plan

This focused plan is part of the cross-layer operator contract defined in [`operator-acceptance-test-matrix.md`](operator-acceptance-test-matrix.md), primarily `OAT-FW-*`, `OAT-BATCH-*`, and `OAT-LOG-*`. The historical `OAT-FW-*` identifier is retained as a stable test ID; current prose uses Programming Image terminology.

Required browser regression coverage:

1. First Program with a Programming Image emits SHA-256 fingerprint-only cache check, cache miss, binary upload start, and binary upload complete logs.
2. Concurrent selected Sites share one upload.
3. Reusing the same Programming Image in the same Engineering session emits cache hit/reference-only log and performs no additional binary upload.
4. Reconnect emits a new-session log that states the previous Programming Asset cache was cleared.
5. An independent Site cancel inside a multi-Site batch produces a PARTIAL aggregate summary while unaffected Sites continue independently.

Network request counts remain the source of truth for whether a binary upload occurred; operator logs must agree with those counts.
