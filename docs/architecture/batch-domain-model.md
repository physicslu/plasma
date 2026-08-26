# Plasma Batch Domain Model

Status: canonical architecture synthesis

## Purpose

This document consolidates the Batch domain model that is already defined across Plasma architecture documents and executable code. It is not a new execution design and it does not introduce a second vocabulary.

The authoritative sources remain:

1. [`ppu-facility-sites.md`](ppu-facility-sites.md) for Facility / PPU / Site identity and ownership.
2. [`engineering-programming-workspace.md`](engineering-programming-workspace.md) for Engineering provider, Programming Asset and Normalized Image semantics.
3. [`server-side-batch-runtime.md`](server-side-batch-runtime.md) for Batch state, policy, concurrency, statistics and REST execution contract.
4. [`pmode-factory-console-v2.md`](pmode-factory-console-v2.md) for Production UI ownership, Batch selection, KPI, and operator-facing state semantics.
5. `software/python/plasma_core/batch.py` and `software/python/plasma_web/batch_runtime.py` for the current executable model.

If this document conflicts with executable code or those canonical contracts, follow the repository source-of-truth priority in `AGENTS.md` and fix this document.

## Canonical topology

Plasma has one deployment topology:

```text
Plasma System
└── Facility
    └── PPU (Plasma Programming Unit)
        ├── SITE 1
        ├── SITE 2
        └── ... SITE N
```

Canonical durable Site identity is:

```text
(facility_id, ppu_id, site_id)
```

`site_id` is one-based. There is no canonical `SITE 0`.

`Factory`, `Programmer`, and `Channel` are not additional canonical hierarchy levels. Retired Programmer/Channel vocabulary must not be reintroduced into current runtime contracts.

A PPU remains an autonomous local execution node. Plasma Manager is optional and must not become a hidden dependency for healthy local PPU operation.

## Batch is an aggregate, not a topology level

A Batch is not a child of one Site and it is not the physical execution resource. A Batch is a server-owned aggregate that binds a fixed execution snapshot:

```text
Batch
├── targets: (Facility, PPU, Site)[]
├── operations: E / P / V / R
├── execution policy
├── Programming Asset provenance when required
└── per-Site runtime state
```

Each selected Site owns an independent execution pipeline:

```text
Batch
├── SITE A pipeline: Erase -> Program -> Verify -> next round
├── SITE B pipeline: Erase -> Program -> Verify -> next round
└── SITE C pipeline: Erase -> Program -> Verify -> next round
```

There is no global round barrier. A Site that finishes one round may enter its next round while another Site is still executing the previous round.

This is the architectural meaning of "different Sites do not wait for each other".

## Current domain objects

### `BatchTarget`

`BatchTarget` identifies one selected execution target:

```text
facility_id
ppu_id
site_id
```

The current key is derived from that tuple. Sites are not flattened into a global integer namespace.

### `BatchExecutionPolicy`

The immutable Batch policy is:

```text
repeat_count
site_retry_limit
failed_site_stop_threshold
```

Semantics:

- `repeat_count` repeats the complete selected operation sequence.
- `site_retry_limit` is retries after the first attempt.
- `failed_site_stop_threshold = null` disables the circuit breaker.
- the failure threshold is inclusive: `faulted_site_count >= failed_site_stop_threshold`.

The Batch layer does not implement a second retry engine. It passes retry policy into the canonical Job retry contract.

### `BatchRecord`

The current server runtime stores one in-memory `BatchRecord` containing the immutable execution snapshot plus mutable aggregate runtime state.

Conceptually it owns:

```text
batch_id
operations
execution policy
targets
per-Site runtime state
Programming Asset snapshot when required
read parameters
Batch state
cancellation state
active Job references
statistics
```

Persistence and restart recovery are not part of the current model.

### `BatchSiteRuntime`

`BatchSiteRuntime` is the current per-target runtime projection. It is not a separate public topology entity and should not be renamed to a speculative `SiteExecution` or `BatchJob` abstraction without a separate architecture decision.

It tracks facts such as:

```text
current_round
completed_rounds
current_operation
current_job_id
progress_percent
total_attempts
retry_count
final_failures
faulted_round
faulted_operation
last_failure_source
operation statistics
```

The underlying PPU still executes canonical Jobs through `SiteManager` / `SiteWorker`.

## State model

Batch and Site states are intentionally different layers.

### Batch state

Canonical current `BatchState` values are:

```text
QUEUED
RUNNING
STOPPING
SUCCESS
PARTIAL
ERROR
CANCELLED
```

### Batch Site state

Canonical current `BatchSiteState` values are:

```text
READY
RUNNING
SUCCESS
FAULTED
ERROR
STOPPED
CANCELLED
```

The distinctions are operationally important:

- `FAULTED`: the Site executed a manufacturing operation, exhausted the retry budget and did not pass. This is a yield/execution failure and increments `faulted_site_count`.
- `ERROR`: infrastructure or control-plane failure prevented a reliable manufacturing result. It is not an IC yield failure.
- `STOPPED`: Batch policy stopped work before the Site produced a final manufacturing result.
- `CANCELLED`: operator intent cancelled the work.

Do not collapse these states into a generic `FAIL` result.

## Operation model

The canonical Batch operation set today is:

```text
ERASE
PROGRAM
VERIFY
READ
```

The canonical order is E -> P -> V -> R for the subset selected by the client.

Additional operations such as blank check, secure, OTP or lock are possible future product capabilities, but they are not part of the current Batch contract. Adding them requires an explicit contract and implementation change rather than pre-declaring them here.

`Program` means write only. Verify is a separate selected operation.

## Programming data model

Plasma separates source/input data from target-memory execution data:

```text
Programming Asset
└── Image Asset
      |
      | parser / normalizer
      v
Normalized Image
```

The operator-facing term **Programming Image** maps to an Image-type Programming Asset. `Image` is the short UI/domain term for that source asset. `Shared Image` describes the case where multiple selected Sites use the same Batch Image; it is not a second file object type.

Execution identity is still the **Normalized Image SHA**, because that represents the actual target-memory data being programmed or verified.

Current implemented constraints:

- only `image + binary` normalization is implemented;
- a Program/Verify Batch binds at most one Programming Asset snapshot;
- the browser supplies that Asset once when creating the Batch;
- the provider caches/materializes it for participating PPUs;
- per-Site Jobs reference the cached Asset rather than re-uploading source bytes;
- concurrent Sites on one PPU may share the same active Normalized Image lease;
- a different Normalized Image cannot silently replace the active PPU-wide Program/Verify resource.

This is the concrete implementation behind the Shared Image requirement.

## Execution ownership

The Production execution path is:

```text
Production UI
    |
    | Web REST v3
    v
Plasma Web REST Gateway
    |
    v
BatchRuntimeManager
    |
    v
EngineeringPPUProvider-compatible execution boundary
    |
    v
PPU Plasma Server
    |
    v
SiteManager / SiteWorker
    |
    v
Interface / Handler
```

The Production browser owns selection and operator intent. It does not own scheduling semantics.

Browser responsibilities:

```text
FPS target selection
operation selection
Programming Image selection
BatchExecutionPolicy input
Batch submission
Batch polling
Batch / PPU-scoped cancel requests
operator presentation
```

Server Batch Runtime responsibilities:

```text
Batch ID
immutable operation order
immutable Asset provenance
repeat rounds
retry policy
per-Site state transitions
failed-Site circuit breaker
terminal Batch classification
statistics
```

The browser must not create a second execution engine with `Promise.all`, per-Site retry loops, round barriers or duplicated failure-threshold logic.

## Production and Engineering relationship

Production Mode and Engineering Mode use the same canonical Facility / PPU / Site and Job model, but they expose different workflow scopes.

```text
                    Facility / PPU / Site domain
                              |
             +----------------+----------------+
             |                                 |
      Production Mode                   Engineering Mode
      server-owned Batch                direct engineering workflow
             |                                 |
             +---------------+-----------------+
                             |
                       canonical PPU Jobs
```

Production uses server-side Batch orchestration for multi-target execution.

Engineering Programming can operate directly against a selected PPU/Site through the Engineering provider boundary. This does not justify a second Site identity, operation vocabulary, Image model or hardware execution stack.

## Cancellation scopes

Current Batch runtime supports:

```text
Batch cancel
PPU-scoped cancel within a Batch
underlying active Job cancellation
```

Cancellation must preserve truthful already-terminal results. A completed `SUCCESS` or `FAULTED` Site must not be rewritten merely because the Batch later receives a cancel request.

Batch policy stop and operator cancellation are also distinct causes and must remain distinguishable in state and audit data.

## Statistics model

Statistics separate logical executions from physical attempts because retries can recover an operation while still revealing contact/intermittent failures.

Per operation the current model records:

```text
logical_executions
attempts
retries
successful_executions
failed_executions
error_executions
cancelled_executions
failed_attempts
error_attempts
cancelled_attempts
attempt_failure_rate
```

This distinction is required for meaningful production quality analysis. Final PASS rate alone is insufficient.

## REST boundary

Canonical current server-side Batch endpoints are:

```text
POST /api/batches
GET  /api/batches/{batch_id}
POST /api/batches/{batch_id}/cancel
POST /api/batches/{batch_id}/targets/{facility_id}/{ppu_id}/cancel
```

The browser submits one Batch snapshot and then polls the Batch resource. It does not submit and sequence every Site Job itself.

## Manager and multi-PPU boundary

Plasma Manager remains optional and read-only in the current architecture. It is not the current Batch command router or central scheduler.

The existing multi-PPU Batch runtime uses a provider-shaped execution boundary; the current multi-PPU implementation is backed by the Engineering Mock Provider.

A future real fleet execution adapter may implement the same provider boundary, but that work must not:

- move Batch policy back into the browser;
- make Manager mandatory for standalone PPU operation;
- silently convert the current read-only Manager into an unauthenticated write proxy;
- change Facility / PPU / Site identity.

## Current implementation map

| Domain concern | Current authority |
|---|---|
| Facility / PPU / Site identity | `docs/architecture/ppu-facility-sites.md`, `PPUConfig`, `SiteConfig` |
| Batch target | `plasma_core.batch.BatchTarget` |
| Batch policy | `plasma_core.batch.BatchExecutionPolicy` |
| Batch states | `plasma_core.batch.BatchState`, `BatchSiteState` |
| Batch orchestration | `plasma_web.batch_runtime.BatchRuntimeManager` |
| Per-Site Batch projection | `plasma_web.batch_runtime.BatchSiteRuntime` |
| Underlying execution | `JobRequest` -> `PlasmaServer` -> `SiteManager` / `SiteWorker` |
| Programming source data | `ProgrammingAsset` |
| Target-memory execution data | `NormalizedImage` |
| Production client contract | `docs/architecture/pmode-factory-console-v2.md` |
| Batch execution contract | `docs/architecture/server-side-batch-runtime.md` |

## Explicit non-models

Do not introduce the following as parallel canonical concepts without an approved architecture change:

```text
Factory -> Facility -> Programmer -> Channel
BatchJob
SiteExecution as a second public execution object
browser-owned Batch scheduler
zero-based SITE identity
implicit Program+Verify operation
firmware_file / program_file / flash_file as competing Image concepts
```

`Factory` may become a future business/organizational concept, but it is not part of the current executable topology and must not be inserted into identity contracts prematurely.

## Known gaps and deferred architecture work

The Batch core model is already implemented. The remaining architectural gaps are not a reason to redesign it from scratch.

Current deferred work includes:

1. Real multi-PPU / fleet execution adapter beyond the Engineering Mock Provider.
2. Persistent Batch storage and Gateway restart recovery.
3. Cross-host Programming Asset distribution, lifecycle and garbage collection.
4. Authentication / authorization for future remote write control.
5. Final alignment of operator-facing `Programming Image` terminology with lower-level `ProgrammingAsset` source semantics without losing the Asset / Normalized Image distinction.
6. Additional programming operations only when their semantics, retry behavior and hardware support are defined.

Each item should be handled by a separate architecture or implementation PR. None requires introducing a second Batch domain model.

## Architectural conclusion

The current Plasma architecture already has the essential Batch model:

```text
Facility / PPU / Site topology
        +
fixed Batch target set
        +
immutable BatchExecutionPolicy
        +
server-owned independent per-Site pipelines
        +
Programming Asset -> Normalized Image data path
        +
truthful Site / Batch failure taxonomy
```

The next implementation work should therefore be gap-driven, not model-replacement-driven. Changes should preserve these contracts unless a concrete requirement proves that one of them is insufficient.
