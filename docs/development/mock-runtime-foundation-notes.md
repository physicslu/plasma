# Mock Runtime Foundation Implementation Notes

This temporary implementation note tracks the first code phase of the Mock Runtime v1.1 work.

## Phase A scope

- Immutable `MockProfile` and per-operation runtime parameters.
- Stable deterministic seed derivation for per-attempt Mock behavior.
- Content-addressed shared image Blob store with atomic creation and read-only mmap access.
- Sparse Site Flash state backed by immutable shared image references.
- Unit coverage proving identical content creates one Blob and 60 Sites can reference one image without materializing one full Flash `bytearray` per Site.

## Explicitly deferred

- Runtime Profile REST API and Engineering Mock settings UI.
- Server-side Batch Runtime, repeat rounds, Site retry policy and Batch stop thresholds.
- Job `ERROR` taxonomy and failure-source contract changes.
- Cross-process reference leases, TTL/LRU and Blob garbage collection.
- Cross-host Asset distribution.
- Scenario fault injection such as disconnect, progress stall and partial-write simulation.

This note is not the final architecture specification. The final v1.1 specification will replace or absorb it after the implementation phases are complete.
