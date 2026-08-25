# Plasma Mock Runtime v1.1

Status: implemented software contract; SWPC capacity acceptance and physical hardware acceptance remain separate gates.

This document is the canonical Mock Runtime v1.1 specification. It replaces the earlier working notes and uses the actual implementation names in the repository.

## 1. Purpose

Mock Runtime exists to validate Plasma control-plane, Batch, Programming Asset, retry, cancellation, statistics, and operator workflows without claiming real PPU, Z2, FPGA, socket, or IC validation.

It is intentionally realistic enough to exercise timing, deterministic failures, concurrency, repeated rounds, retries, failure thresholds, shared Programming Assets, and data integrity. It is not a hardware performance model.

## 2. Canonical invariant

```text
One Batch
One immutable Programming Asset snapshot, when Program or Verify is selected
One immutable Mock Profile snapshot
One resolved Mock Seed
One immutable Batch Execution Policy snapshot

Many Facilities
Many PPUs
Many Sites
Independent Site execution
Independent Site round progression
Shared read-only image data
Real Job state transitions
Bounded Verify working memory
```

Within one Site, selected operations execute in canonical order:

```text
Erase -> Program -> Verify -> Read
```

Across Sites and PPUs there is no global round barrier. A Site that completes one round may immediately enter its next round without waiting for other Sites.

## 3. Implemented topology

The Engineering Mock Provider is implemented by `MockEngineeringPPUProvider` and `SharedImageMockEngineeringPPUProvider`.

Topology:

- 8 Facilities.
- 4 PPUs per Facility.
- PPU Site counts: 2, 4, 6, 8.
- 32 PPUs total.
- 160 Sites total.
- Site IDs are one-based.

Each virtual PPU is an in-process `PlasmaServer` runtime backed by `MockInterface`.

The separate Mock CD baseline also retains its standalone Mock PPU scenarios. A PASS in Mock Runtime must never be described as physical PPU or hardware validation.

## 4. Actual implementation boundaries

Primary v1.1 implementation files:

- `software/python/plasma_core/mock_profile.py`
  - immutable Mock profile model;
  - validation;
  - deterministic seed derivation;
  - failure draw;
  - size-aware duration calculation.
- `software/python/plasma_core/mock_image_store.py`
  - content-addressed immutable shared Blob storage;
  - local read-only mmap access.
- `software/python/plasma_core/mock_flash.py`
  - sparse per-Site logical Flash state;
  - shared backing regions;
  - copy-on-write overlay;
  - bounded chunked Verify.
- `software/python/plasma_web/mock_runtime_settings.py`
  - authoritative mutable settings;
  - persistence;
  - revision handling;
  - auto/fixed seed resolution;
  - immutable execution snapshots.
- `software/python/plasma_web/shared_image_mock_provider.py`
  - Mock-aware Engineering PPU adapter;
  - shared-image Programming Asset execution;
  - per-Batch Mock execution context.
- `software/python/plasma_web/mock_batch_runtime.py`
  - Mock-aware adapter around generic `BatchRuntimeManager`;
  - freezes Mock context when a Batch ID is allocated;
  - exposes immutable Mock provenance in Batch snapshots.
- `software/python/plasma_web/batch_runtime.py`
  - generic server-side Batch orchestration;
  - not Mock-specific.
- `software/web/app/engineering/mock-runtime-settings.tsx`
  - Engineering -> Mock operator settings UI.
- `software/web/app/mock-runtime-api.ts`
  - browser contract for server-owned Mock settings.

Generic Batch Runtime must remain usable by future real PPU/Manager execution adapters without depending on MockProfile.

## 5. Mock Profile contract

The authoritative profile contains:

```text
profile_id
revision
enabled
default_image_size_bytes
operations.erase
operations.program
operations.verify
operations.read
seed
```

Every operation has exactly these fields:

```text
error_rate_per_mille
base_time_ms
throughput_bytes_per_second
jitter_ms
```

Validation:

- `error_rate_per_mille`: integer `0..1000`.
- Operator UI displays this as percent with 0.1% resolution.
- `base_time_ms`: non-negative integer.
- `throughput_bytes_per_second`: positive integer.
- `jitter_ms`: non-negative integer.
- `default_image_size_bytes`: 64 KiB through 4 MiB, in 64 KiB increments.
- `revision`: positive integer and server-owned.

The update API does not accept client-selected `profile_id` or `revision`. An accepted update increments the current revision by one.

## 6. Default profile

Canonical product defaults are intentionally non-zero to exercise error handling:

| Operation | Error rate | Per-mille | Base time | Throughput | Jitter |
|---|---:|---:|---:|---:|---:|
| Erase | 0.1% | 1 | 1000 ms | 2 MiB/s | +/-200 ms |
| Program | 5.0% | 50 | 500 ms | 512 KiB/s | +/-200 ms |
| Verify | 2.0% | 20 | 300 ms | 1 MiB/s | +/-100 ms |
| Read | 0.5% | 5 | 200 ms | 1 MiB/s | +/-100 ms |

Default image size is 256 KiB.

CI is not allowed to depend on these probability draws. Persistent Mock browser acceptance therefore uses a dedicated fixed-seed, zero-error, short-timing profile. The CI profile is test infrastructure and does not change product defaults.

## 7. Timing model

For one operation attempt:

```text
duration_ms = max(
  0,
  round(base_time_ms + data_size_bytes * 1000 / throughput_bytes_per_second + jitter)
)
```

`jitter` is a deterministic pseudo-random integer in `[-jitter_ms, +jitter_ms]` for the resolved execution seed.

Timing is a software test model only. It must not be interpreted as Z2, FPGA, socket, or IC programming throughput.

## 8. Seed and deterministic execution

Seed settings are:

```text
mode = auto | fixed
fixed_seed = null | integer
```

Rules:

- `auto`: `fixed_seed` must be null; a 63-bit seed is resolved when the execution snapshot is frozen.
- `fixed`: `fixed_seed` is required and must be in `0..2^63-1`.
- One server Batch freezes one resolved seed before any Site Job is submitted.
- Editing Mock Settings while a Batch is running cannot alter that Batch.
- Direct Engineering Jobs receive their own immutable execution snapshot at submission.

Per-attempt deterministic seed derivation uses SHA-256 over:

```text
resolved Batch seed
batch_id
facility_id
ppu_id
site_id
round_index
operation
attempt
profile_revision
```

Python `hash()` is never used for this purpose.

Changing any listed field intentionally changes the pseudo-random stream. A Retry therefore receives a distinct deterministic attempt seed.

## 9. Error injection semantics

For an operation attempt:

```text
should_fail = rng.randrange(1000) < error_rate_per_mille
```

An injected failure is an operation-level failure, not an infrastructure error.

Program injected failure is atomic in v1.1: the prior logical Flash state remains unchanged.

Verify data mismatch is distinct from injected failure and reports `failure_source = data_mismatch` with mismatch address information where available.

Infrastructure failures remain separate from programmed Mock yield failures.

## 10. Shared image and Mock Flash memory model

A 4 MiB Programming Asset must not become one persistent 4 MiB bytearray per Site.

The execution model is:

```text
Programming Asset
  -> normalized image
  -> content-addressed shared Blob
  -> local_mock_blob ExecutionImageRef
  -> read-only mmap when bytes are needed

Per Site
  -> MockFlashState
     -> BackingRegion references shared image SHA-256
     -> SparseOverlay for copy-on-write regions
```

`MockFlashState` stores logical backing references instead of full per-Site Flash copies.

Read resolution is logically:

```text
overlay
then latest backing region
then older backing regions where not superseded
then 0xFF
```

Full Erase clears logical backing and overlay state. Partial Erase is represented by a `0xFF` overlay for the erased range.

Verify against a shared image is performed in 64 KiB chunks. The expected 4 MiB image stays mmap-backed and is not materialized as another full expected-image byte array for every concurrently executing Site.

## 11. Programming Asset execution contract

Program and Verify require one Programming Asset snapshot for the Batch.

The browser may upload the binary once to the Gateway. Mock same-host execution then resolves it into shared local image storage. Per-Site Jobs use `ExecutionImageRef(scheme = local_mock_blob)` rather than retaining the full binary in JobRegistry.

The real/non-Mock PPU inline-binary protocol path remains valid and is not replaced by local Mock references.

A Batch that does not include Program or Verify must not carry a Programming Asset.

## 12. Server-owned Mock Settings API

When the Shared Image Mock Engineering Provider is enabled:

```text
GET  /api/mock/runtime
POST /api/mock/runtime
```

GET returns the server-applied profile, revision, and seed settings.

POST accepts exactly:

```json
{
  "enabled": true,
  "default_image_size_bytes": 262144,
  "operations": {
    "erase": {
      "error_rate_per_mille": 1,
      "base_time_ms": 1000,
      "throughput_bytes_per_second": 2097152,
      "jitter_ms": 200
    },
    "program": {
      "error_rate_per_mille": 50,
      "base_time_ms": 500,
      "throughput_bytes_per_second": 524288,
      "jitter_ms": 200
    },
    "verify": {
      "error_rate_per_mille": 20,
      "base_time_ms": 300,
      "throughput_bytes_per_second": 1048576,
      "jitter_ms": 100
    },
    "read": {
      "error_rate_per_mille": 5,
      "base_time_ms": 200,
      "throughput_bytes_per_second": 1048576,
      "jitter_ms": 100
    }
  },
  "seed": {
    "mode": "auto",
    "fixed_seed": null
  }
}
```

Unknown or missing fields fail closed.

Persistent settings default to:

```text
<engineering-mock-root>/mock-runtime.yaml
```

or the explicit `--engineering-mock-profile` path.

## 13. Server-side Batch policy

The immutable Batch policy is:

```text
repeat_count
site_retry_limit
failed_site_stop_threshold
```

Limits:

- `repeat_count`: `1..10000`.
- `site_retry_limit`: `0..20`.
- Maximum attempts for one logical operation = `1 + site_retry_limit`.
- `failed_site_stop_threshold`: null or positive integer not greater than selected Site count.

A Site progresses independently through all selected operations and rounds.

Retry is implemented by the existing Job retry contract. Batch Runtime does not create a second independent retry loop.

## 14. Site and Batch state semantics

These definitions are contractual and must be reused by the UI, statistics, logs, Operator Guide, User Manual, and future localized documentation.

### Site states

| State | Meaning | Yield treatment |
|---|---|---|
| `READY` | Selected Site has not started Batch work. | Not counted. |
| `RUNNING` | Site is executing a Batch operation. | Not terminal. |
| `SUCCESS` | All required rounds and operations completed successfully. | Pass. |
| `FAULTED` | An operation reached terminal failed/timeout after its allowed retries. The Site is removed from later rounds. | Product/Site failure; counts in yield denominator and fault threshold. |
| `ERROR` | Infrastructure/control-plane/runtime failure prevents a trustworthy DUT result. | Excluded from programmed yield failure. Batch enters ERROR. |
| `STOPPED` | Site was prevented from continuing because Batch policy stopped future work, for example after the FAULTED-Site circuit breaker or infrastructure error. | Not a DUT failure by itself. |
| `CANCELLED` | Operator Batch/PPU cancellation stopped this Site. | Not a programmed DUT failure. |

The essential distinction is:

```text
FAULTED = execution produced a trustworthy failed DUT/Site result after retry policy.
ERROR   = Plasma cannot reliably determine DUT success/failure because the system path failed.
```

`FAILED` remains a Job/operation-level state. `FAULTED` is the Batch Site isolation state after terminal operation failure.

### Batch states

| State | Meaning |
|---|---|
| `QUEUED` | Batch exists but execution has not started. |
| `RUNNING` | At least one Site may be executing. |
| `STOPPING` | Controlled stop/cancel is in progress. |
| `SUCCESS` | Every participating Site ended SUCCESS. |
| `PARTIAL` | Mixed non-infrastructure terminal outcomes, such as SUCCESS plus FAULTED/CANCELLED where no Batch error circuit breaker was triggered. |
| `ERROR` | Infrastructure failure, runtime exception, or configured FAULTED-Site threshold stopped the Batch. |
| `CANCELLED` | Operator cancelled the Batch, or all Sites ended cancelled. |

Completed Job results remain truthful and immutable when Batch classification changes.

## 15. FAULTED-Site circuit breaker

If `failed_site_stop_threshold` is enabled:

```text
faulted_site_count >= failed_site_stop_threshold
  -> Batch STOPPING
  -> cancel active work
  -> pending/future non-faulted Sites become STOPPED
  -> Batch ERROR
```

Canonical error code:

```text
BATCH_SITE_FAILURE_THRESHOLD_EXCEEDED
```

Example: threshold `3` tolerates two FAULTED Sites; the third FAULTED Site trips the Batch circuit breaker.

## 16. Infrastructure failure behavior

An infrastructure or control-plane failure causes:

```text
trigger Site -> ERROR
Batch -> STOPPING
other unfinished Sites -> STOPPED when the stop disposition is observed
Batch -> ERROR
```

Canonical Batch infrastructure error code:

```text
BATCH_INFRASTRUCTURE_ERROR
```

Infrastructure ERROR must not be silently converted into a DUT failure.

## 17. Statistics contract

Batch snapshots expose per-operation aggregated statistics and per-Site statistics.

Important counters:

- `logical_executions`
- `attempts`
- `retries`
- `successful_executions`
- `failed_executions`
- `error_executions`
- `cancelled_executions`
- `failed_attempts`
- `error_attempts`
- `cancelled_attempts`
- `attempt_failure_rate`

Per Site snapshots additionally include:

- current/completed round;
- current operation and Job ID;
- total attempts;
- retry count;
- final failure count;
- faulted round/operation;
- last failure source;
- terminal error details.

Statistics must distinguish logical operation executions from physical attempts. A retry increases attempts/retries but does not create a second logical operation execution.

## 18. Yield semantics

For Mock production statistics, infrastructure/cancellation outcomes are not programmed DUT failures.

A basic programmed yield is therefore:

```text
Yield = SUCCESS Sites / (SUCCESS Sites + FAULTED Sites)
```

Example:

```text
SUCCESS  970
FAULTED   25
ERROR      5

Yield = 970 / (970 + 25) = 97.49%
```

The 5 ERROR Sites must be reported separately as system/infrastructure quality, not hidden inside DUT yield.

Production reporting should eventually show both product yield and system availability/error quality instead of compressing them into one percentage.

## 19. Cancellation truthfulness

Cancellation is intent plus timing, not retrospective rewriting.

If an operation has already reached terminal SUCCESS before the cancellation is accepted, its Job result remains SUCCESS.

If cancellation reaches an active Job first, the affected Site may become CANCELLED.

PPU-scoped cancellation affects only the selected PPU inside the Batch. Other PPUs continue independently.

This race is covered by persistent real-stack browser acceptance using deterministic timing so the cancellation is deliberately issued while the target Site is RUNNING.

## 20. Validation layers

Current software validation layers are:

```text
Python / PL unit-source tests
Web source / SSR contract tests
Playwright browser E2E
Mock CD
Persistent Mock CD Browser Runtime Acceptance
```

The v1.1 software contract requires all relevant layers to PASS before merge-ready status.

These layers do not replace:

- SWPC deployment acceptance;
- 4 MiB x 60 Site capacity measurement;
- human operator acceptance;
- Z2/FPGA/electrical validation;
- real IC validation.

## 21. SWPC capacity gate

The release acceptance procedure for the 4 MiB x 60 Site case is defined in:

`docs/development/mock-runtime-operator-guide.md`

The purpose is to measure actual RSS/peak RSS on SWPC after explicit deployment approval. No GitHub/Mock CI result may be substituted for that measurement.

The architectural objective is to demonstrate that one 4 MiB Programming Asset is shared rather than retained as sixty independent persistent 4 MiB Flash/image copies.

## 22. Deferred items

Not part of v1.1:

- cross-host Blob distribution;
- persistent Batch database across Gateway process restart;
- shared Blob TTL/LRU/lease garbage collection policy;
- real Manager multi-host execution adapter;
- real PPU Mock Profile semantics;
- hardware timing/performance modeling;
- automatic yield control based on manufacturing process limits beyond the configured FAULTED-Site threshold.

These items must not be implied by the v1.1 UI or documentation.

## 23. Non-claims

A v1.1 Mock PASS means the software orchestration contract behaved as specified under Mock execution.

It does not mean:

- Z2 is validated;
- FPGA logic is validated;
- an electrical interface is validated;
- socket/contact integrity is validated;
- a real IC algorithm is validated;
- Mock timing predicts real production throughput.
