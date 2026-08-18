# Batch cancel barrier regression intent

The browser regression in `batch-lifecycle.spec.ts` protects the safety invariant that once the batch cancellation barrier is observed, the next operation must not reach `POST /api/jobs`.

A request that was already dispatched before the cancellation event cannot be recalled. Such a request is represented as `SUBMITTING`; if it is accepted after cancellation, the lifecycle immediately requests cancellation for that job.

This distinction is intentional and matches the actual HTTP side-effect boundary.
