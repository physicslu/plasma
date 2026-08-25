# Mock Runtime Foundation Implementation Notes

This temporary implementation note tracks the first code phase of the Mock Runtime v1.1 work.

## Phase A scope

- Immutable `MockProfile` and per-operation runtime parameters.
- Stable deterministic seed derivation for per-attempt Mock behavior.
- Content-addressed shared image Blob store with atomic creation and read-only mmap access.
- Sparse Site Flash state backed by immutable shared image references.
- Unit coverage proving identical content creates one Blob and 160 Sites can reference one image without materializing one full Flash `bytearray` per Site.

## Explicitly deferred

- Runtime Profile REST API and Engineering Mock settings UI.
- Server-side Batch Runtime, repeat rounds, Site retry policy and Batch stop thresholds.
- Job `ERROR` taxonomy and failure-source contract changes.
- Cross-process reference leases, TTL/LRU and Blob garbage collection.
- Cross-host Asset distribution.
- Scenario fault injection such as disconnect, progress stall and partial-write simulation.

## Approved subsequent Batch execution policy

The later Server-side Batch Runtime must keep execution policy separate from `MockProfile`.

- `repeat_count` repeats the selected E/P/V/R Site pipeline as complete rounds.
- `site_retry_limit` is the number of retries after the first failed attempt; maximum attempts are therefore `1 + site_retry_limit`.
- Retry exhaustion removes that Site from subsequent Batch rounds and classifies it as `FAULTED`, not operator-disabled.
- `failed_site_stop_threshold` is reached with `faulted_site_count >= threshold`; reaching it triggers a controlled Batch stop and Batch-level `ERROR` classification.
- Completed Job results remain truthful and immutable when the Batch later stops.
- Batch cancellation may still control Batch-level classification when it races terminal Job success, while the underlying Job result remains truthful as required by the repository execution contract.
- Attempt-level failure statistics and final-operation failure statistics must remain distinct so Retry does not hide the configured failure behavior.

This note is not the final architecture specification. The final v1.1 specification will replace or absorb it after the implementation phases are complete.
