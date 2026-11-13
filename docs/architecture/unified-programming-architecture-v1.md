# Unified Programming Architecture v1 — one engine, two Target Scopes

Status: **Gate 1 contract freeze (owner decisions 2026-11-12). Not implemented. No hardware
evidence.** Every statement about Z2, FPGA, DUT or real IC programming below is a contract, not a
result. See "Qualification" at the end.

Depends on [OPF Programming Operations v1](opf-programming-operations-v1.md) and
[EMode Batch Retry / Stop Policy v1](emode-batch-retry-stop-policy-v1.md).
Gap analysis that produced this contract:
[Gate 1 read-only audit](../development/handoff/2026-11-12-unified-programming-architecture-gate1-audit.md).
Retirement scope and per-consumer disposition:
[PR-F Retirement Inventory](../development/handoff/2026-11-12-legacy-gateway-batch-retirement-inventory.md).

## 1. Principle

EMode and PMode differ **only** in Target Selection Scope and UI presentation. They share one
Programming Engine, one Manager Batch Orchestrator, one Programming Route Admission, one Job,
one Receipt, one Policy and one Recovery path.

| | Target Scope |
| --- | --- |
| EMode | one PPU, one or more Sites |
| PMode | one or more PPUs, one or more Sites |

There is no mode-specific execution engine, no Browser-owned batch and no second programming
route. A Console decides **what to offer and when to dispatch**; it never executes.

## 2. Owner decisions (2026-11-12)

| | Decision |
| --- | --- |
| D-1 | PMode moves to the `operations[]` model **immediately**. `flash_cycle` is retired, not kept as a parallel default. |
| D-2 | The legacy direct-Gateway batch path retires through a **PR-F Retirement Inventory** that judges each consumer delete / migrate / keep. No bulk deletion. |
| D-3 | PMode gains Retry. `failedSiteStopThreshold` becomes the unified `stop_policy` object. |
| D-4 | **Generic Device Personalization** (§8). PR-A freezes generic responsibilities and the extension boundary only. |
| D-5 | Stop Policy `threshold` widens to `1..N`; the default stays `{"kind": "never"}`. |
| D-6 | Journal retention limits are tuned from measurement during PR-B; this contract does not freeze the numbers. |

**D-2 corollary (normative):** until PR-F lands, no document, UI string, PR description or report
may state that the legacy Gateway Batch path is retired.

## 3. Target Set

```jsonc
{
  "targets": [
    { "ppu_alias": "<alias>", "site_ids": [1, 2, 3] },
    { "ppu_alias": "<alias>", "site_ids": [2] }
  ],
  "icpn": "<ICPN>",
  "operations": ["erase", "program", "verify"],
  "image_base64": "...",          // or bundle_base64, or address/length for erase-only
  "policy": { "repeat": 1, "retry_limit": 0, "stop_policy": { "kind": "never" } }
}
```

Normative:

1. `icpn` and the Programming Image / Bundle are **Batch-level**, never per Site. One programming
   run writes one firmware Image to one MCU type across every Target. A request that varies them
   per Site is refused; the schema must not be able to express it.
2. EMode is admitted only with `len(targets) == 1`; PMode has no such limit. The restriction is
   enforced in the Manager, not only in the Console.
3. `site_ids` is a set: repeats and a Site the PPU does not report are refused.
4. This replaces the current single `site_id` (`plasma_manager/programming_batch.py` `PLAN_KEYS`)
   and removes the `threshold == 1` restriction in `parse_policy`.

Because the Image is identical across the Batch, `image_asset_sha256` is identical for every
Target. Only `ppu_id` and `site_id` differ between Job Bindings, so the Bundle v3 build and the
Resource Set comparison are computed **once per PPU** and reused for that PPU's Sites.

## 4. Programming Operations

Unchanged from [OPF Programming Operations v1](opf-programming-operations-v1.md):

| Job kind | Selector | Scope |
| --- | --- | --- |
| `programming` | `operations: [...]` in erase → program → verify order | one Job per Site, one Binding, one receipt |
| `read` | `operation: "read"` + `address` / `length` | an independent per-Site Job, **never part of a Batch** |

`flash_cycle` is retired under D-1. Two implementation consequences are in scope and must land
with the switch, not after it:

* `plasma_server/execution_router.py` admits the OPF Package Provider route only for
  `Operation.FLASH_CYCLE`. That constraint is lifted to the `programming` Job kind.
* `plasma_handlers/programming.py` dispatches `Operation.PROGRAMMING` to
  `interface.run_operations(...)`. `plasma_interfaces/openocd.py` overrides it;
  `plasma_interfaces/mock.py` did not, and so inherited the generic composition that
  `BaseInterface.run_operations` provides. **That was a divergence, not a refusal**: the inherited
  default writes at offset 0 instead of the Binding's address, erases the whole simulated device
  instead of the Image's window, and returns no step evidence at all. A Mock Site is kept (D-2),
  so it gains its own `run_operations` with read-back evidence **before** the switch (PR-B1).

Retiring `flash_cycle` changes the Programming Profile, therefore the Resource Set SHA256,
therefore every PPU needs one B1/B2/B3 reactivation. See §8.6 for why this must happen once.

## 5. Manager-owned Batch

One Batch spans many PPUs and many Sites. It is owned, scheduled, journalled and recovered by the
Manager. The Browser observes it and may request a stop; it never schedules, retries or decides a
result.

### 5.1 Identity

```text
batch_id    Manager-issued, 32 hex
start_id    one per Batch; the sole idempotency token
job_key     (batch_id, ppu_alias, site_id, attempt_number)
plan_id     one per attempt
run_id      one per attempt
```

### 5.2 Scheduling

Sequential (§7). The orchestrator walks the Target Set, and for each Site produces an ordinary
plan + run + single PPU Job. An attempt is journalled **before** it is submitted.

### 5.3 Admission and idempotency

A Batch start carries a Manager-issued `start_id` obtained first
(`plasma_manager/programming.py` `issue_batch_start` → `consume_batch_start`). It is admitted at
most once; an unknown, used, voided or expired ID is refused with `409` and nothing is submitted.

Admission separates **validity** from **readiness**, and they are refused differently.

- A malformed request, an unknown or unauthorised Target, or a caller without the operation
  authority refuses the **whole** Batch. Nothing is journalled and the `start_id` is **not**
  consumed, so the operator may correct the request and resend the same token.
- A Target that is valid but not ready — Platform `BUSY`, `RECOVERY_REQUIRED`, or an idle state
  that cannot be proven — does not refuse the Batch. That Target alone is admitted `BLOCKED` with
  its specific reason recorded, and no Job is submitted for it (§5.7).

A resend never reprograms. A used `start_id` stays a `409`, and the sender recovers the Batch's
identity and state through the read-only reconciliation of §5.4. No path re-submits a Target that
already completed or one sitting at `OUTCOME_UNKNOWN`, which continues to require operator
reconciliation (§6). Partial admission does not weaken this: a Batch admitted with some Targets
`BLOCKED` has consumed its `start_id`, so those Targets are restarted under a **new** `start_id`,
never by replaying the old one.

### 5.4 Disconnection and recovery

The Console may disconnect at any point. Reconnecting re-reads the Batch by `batch_id`; a Console
that never saw the start answer reconciles read-only by `start_id`. After a Manager restart
nothing is resubmitted: an interrupted attempt that may have reached a PPU ends `OUTCOME_UNKNOWN`,
one that provably did not ends `BLOCKED`. This extends the existing per-Batch rule to a per-Site
judgement.

The journal carries that judgement across the restart, so its schema change is part of this
contract. It moves from a single `site_id` with a flat attempt list to `targets[]` keyed by
`job_key` (§5.1), and the Batch record version moves with it. A journal written by the previous
schema is **migrated on read** into a single-Target Batch; it is not refused. The reason is the
interrupted attempt itself: that record is exactly what this section must judge, and refusing to
load it would silently discard an `OUTCOME_UNKNOWN` the safety contract exists to preserve.

The migration reshapes and never reinterprets. It invents no attempt, promotes no outcome, and
leaves an interrupted attempt interrupted for §5.4 to judge under the same rule it would have
received before the upgrade. It is also read-only in the strict sense: the stored journal is
normalised in memory and is never rewritten, truncated or re-signed. The original evidence stays
exactly as the interrupted Manager left it. The compatibility read is a dated item, not a
permanent one: it may be removed once no deployed Manager can still hold a journal of the old
schema, and until that is shown, it stays.

The v2 journal commits durably, with evidence good enough to recover from a crash rather than
merely to describe one. An attempt is journalled before it is submitted, and the record survives a
process that dies at any point between the two. A judgement that this evidence cannot support is
not made. In particular `BLOCKED` requires positive proof that no Job was submitted: an attempt
that cannot be proven unsent is `OUTCOME_UNKNOWN`, never `BLOCKED`, and no shortage of evidence
may be read the other way.

### 5.5 Stop

`request_stop` means **stop queuing**. It never cancels a submitted Job, releases a lease, resets a
PPU or clears recovery state. A running attempt is observed to its end.

### 5.6 Aggregate outcome

A Batch reports an **execution status** and an **outcome**, and they are two separate fields. The
outcome is derived from the Targets, never recorded independently of them, by the priority

```text
OUTCOME_UNKNOWN > FAIL > PARTIAL > PASS
```

1. Any Target `OUTCOME_UNKNOWN` makes the Batch `OUTCOME_UNKNOWN`. Safety outranks everything
   below it; no number of passing Targets dilutes it.
2. With no `OUTCOME_UNKNOWN` present, any Target `FAIL` makes the Batch `FAIL`.
3. With neither present, a Batch in which **no** Target executed reads `BLOCKED`, and a Batch in
   which some executed and at least one did not — `BLOCKED`, `SKIPPED` or `NOT_RUN` — reads
   `PARTIAL`.
4. `PASS` requires every scheduled execution unit to have completed **and** every one of them to
   have passed. An unfinished Target can never let a Batch read `PASS`; that Batch is `PARTIAL`.
5. Execution status is separate from outcome. `STOPPED`, `NOT_RUN` and `SKIPPED` are statuses;
   none of them may be reported as `FAIL` or as `OUTCOME_UNKNOWN`.
6. The Batch outcome authorises nothing. Retry eligibility, recovery and the no-auto-resend rule
   stay per Site and are decided from that Site's own receipt under the §6 safety contract.
7. Every Target keeps its own Job, run, receipt, SAFE_OFF evidence and Resource Set identity. The
   aggregate reads them; it never merges, rewrites or stands in for them.
8. A single-Target Batch reduces to the present behaviour: the Batch outcome is that Target's
   outcome, field for field.

PR-B carries positive and negative tests for mixed results, early stop, unknown outcomes, a Target
Set mixing `READY`, `BUSY` and `RECOVERY_REQUIRED` PPUs, readiness that changes between admission
and execution, restart reconciliation and single-Target compatibility.

### 5.7 Per-Target isolation and the Platform gate

One unready PPU does not stop the others. A Batch is admitted partially (§5.3) and every Target is
judged on its own.

1. Admission reads the authority and the Platform readiness of **every** Target PPU.
2. A Target that is not ready is admitted `BLOCKED` with its specific reason. No Job is submitted
   for it and no retry budget is spent on it.
3. Every `READY` Target still executes. An unrelated PPU's state never blocks them.
4. Readiness read at admission does not authorise a mutation that happens later. **Each PPU is
   re-checked immediately before it is operated.** A Target that was ready at admission and is not
   ready when reached becomes `BLOCKED` at that point, and the walk continues.
5. A `BLOCKED` Target is not a definite failure. By default it does not count toward a
   `failed_sites` stop threshold (§6); only a policy that asks for it may make it count.
6. Scheduling stays sequential (§7) and there remains exactly one Manager Batch engine. Per-Target
   isolation changes what a Target's state means to its neighbours, not how many run at once.
7. A Target's guard protects more than that Target. Before it runs, the Manager must still hold
   mutual exclusion on its PPU, a valid lease on it, and isolation from any other Batch executing
   there. Isolation narrows what one PPU's state means to another PPU; it never narrows what must
   be true about the PPU being operated.
8. Isolation applies to Target state, not to the machinery that judges it. If the shared safety
   infrastructure fails — the journal cannot be committed, admission cannot be read, the Platform
   gate cannot be evaluated — the **whole Batch fails closed**. One PPU being unready is isolated;
   being unable to tell whether a PPU is ready is not.
9. Bundle v3 and the Resource Set comparison are computed once per PPU and reused across that
   PPU's Sites (§3). What is reused is the computation, not its authorisation: before each Site is
   operated, the Platform gate, that PPU's Active Generation and the Resource Identity are
   re-validated. A reused computation whose preconditions no longer hold is discarded, and the
   Target does not proceed on it.

### 5.8 API surface and its retirement

The Batch is owned by the Manager, not by a PPU, so its canonical resource does not sit under one.

| Endpoint | Status |
| --- | --- |
| `POST /api/programming/batches` | Canonical. Carries the Target Set (§3) and may span many PPUs. Read and stopped at `/api/programming/batches/<batch_id>[/stop]`. |
| `POST /api/registry/<alias>/bootstrap/programming/batches` | Short-term compatibility entry. Equivalent to a single-Target Batch on that alias, and it reads only such a Batch. |

(An earlier revision of this section wrote the compatibility entry as
`/ppus/<alias>/programming/batches`. That shorthand came from the Gate 1 audit and is not a path
the Manager serves; the table above is the implemented one.)

Both are doors into the **same** Manager Batch engine. Exactly one scheduler, one journal, one
outcome policy, one recovery path and one retry engine stands behind them. A second implementation
behind the compatibility entry is forbidden, and so is a second set of semantics: a Batch admitted
through either door is judged by §5.3, §5.6 and §5.7 identically.

PR-B adds the canonical resource and keeps the compatibility entry. PR-B does not change
`software/web`.

The compatibility entry retires in **PR-C**, not PR-F. PR-F retires the legacy direct-Gateway
batch path (§11), which is a different path; the alias-scoped route belongs to the Manager-owned
path and is superseded by the canonical resource rather than judged as legacy.

PR-C may remove it only after all of:

1. a Consumer Inventory covering EMode, PMode, the Console BFF, CLI and scripts, API clients,
   tests and fixtures, and the deployed SWPC Control Station;
2. every consumer migrated for Batch start, status and query, stop, reconcile, and error and
   outcome handling;
3. host-only regression, an API contract check and Console E2E passing against the canonical
   resource;
4. a stated deployment order, because a Manager that has dropped the entry breaks a Control
   Station that has not yet shipped.

Console source having switched is **not** evidence that a deployed consumer has. Any consumer that
cannot be confirmed is a blocking item and the entry stays.

## 6. Batch Policy

| Field | Default | Range |
| --- | --- | --- |
| `repeat` | `1` | `1` only; anything else is `400 repeat_not_supported` |
| `retry_limit` | `0` | `0..5` |
| `stop_policy` | `{"kind": "never"}` | `never`, or `{"kind": "failed_sites", "threshold": 1..N}` where N is the Batch's Site count |

The same object applies to both modes (D-3). The legacy
`{repeat_count, site_retry_limit, failed_site_stop_threshold}` triple retires with the legacy path.

**Non-negotiable safety contract.** These are existing, implemented guarantees; this document
freezes them rather than introducing them.

1. `OUTCOME_UNKNOWN` is **never** retried, consumes no retry budget, and latches the PPU until an
   operator reconciles and acknowledges it.
2. `BLOCKED` (nothing submitted) ends the Batch for that Target and is not a FAIL. It does not
   count toward a `failed_sites` threshold unless the policy asks for it (§5.7).
3. Only a definite `FAIL` is retry-eligible, and only when the receipt proves exactly one
   submitted Job in a terminal state, SAFE_OFF verified, and a confirmed Job Binding.
4. Before any retry, the PPU must read as released (Site idle, no Job, no held lease, no recovery
   required). Any state that cannot be read blocks the retry.
5. Stop is stop-queuing only.

An `OUTCOME_UNKNOWN` on one PPU latches that PPU and skips its remaining Sites. Other PPUs in the
same Batch continue.

## 7. Concurrency

**Sequential execution is retained.** One in-flight run at a time across the whole Batch.
The Target Set changes the scheduling data structure, not the execution concurrency.

| Level | Status |
| --- | --- |
| one Site | qualified on Site 2 (historical HIL) |
| many Sites on one PPU | not implemented, not qualified |
| many PPUs in parallel | not implemented, not qualified |

The PPU Runtime can hold several Site Jobs under one execution lease and bounds them with
`max_concurrent_jobs`, but no cross-Site hardware mutual exclusion for FPGA, SWD or power was
found in the source, and no bounded starvation or latency measurement exists. **Eight-channel
concurrency must not be claimed, enabled by default, or implied in any UI.** Raising concurrency
is a separate Gate 1 with its own hardware acceptance.

## 8. Device Personalization (D-4)

Generic contract only. This section freezes **responsibilities and the extension boundary**; it
does not commit every MCU to one wire schema or one write command.

### 8.1 Separation of concerns

A Site's work is two independently verified domains aggregated into one Site Receipt:

| Domain | Content | Verification |
| --- | --- | --- |
| Firmware | the Batch-level Image written by the `operations` list | existing per-step evidence: range, bytes, `readback_sha256` against the Image SHA256 |
| Personalization | the per-Site unique data | its own evidence, on its own range or vendor-defined channel |

### 8.2 Address disjointness (normative)

**The firmware region and the personalization region must not overlap.** Firmware verification
compares the readback of `[address, address+length)` against the SHA256 of the single Batch Image;
per-Site bytes inside that window would make the expected SHA256 per-unit and destroy the
Batch-level Image identity fixed in §3.

"Image Patch" in this generic contract therefore means *writing into a personalization region the
firmware reserved*, not *modifying bytes inside the firmware Image*. An MCU that genuinely
requires the latter is a **per-MCU extension** that must declare it and explicitly carry per-Site
Image identity, with its own plan, Job Binding and expected readback per Site. It is out of scope
for v1.

### 8.3 Serial Source

Four sources, all Manager-resolved:

| Source | Manager behaviour |
| --- | --- |
| `sequential` | allocates the next value from a persisted counter |
| `manifest` | consumes the next unused entry from an operator-supplied list |
| `external_api` | requests the value from an external system |
| `device_uid` | **reads** the device's own unique ID; writes nothing |

`device_uid` is a read-and-record source, not a write. It produces a Receipt field and may be
reported outward; it adds no write step and no personalization region.

### 8.4 Allocation, locking and persistence

Per-Site personalization data is allocated, locked and journalled by the Manager **before** the
Site's Job is submitted. This is the same problem as Start Outcome Reconciliation — a value leaves
the Manager and its fate may be unobservable — so it reuses that mechanism
(`plasma_manager/programming.py` issue / consume / void / reconcile) rather than inventing a
second one, with one added state:

```text
ISSUED      allocated, not yet submitted           → may be voided
CONSUMED    submitted with a known definite result → spent
VOIDED      never admitted                          → returned to the pool
QUARANTINED outcome unknown                         → neither reusable nor returned
```

`QUARANTINED` is required: a serial whose Job ended `OUTCOME_UNKNOWN` may already be on a device.
Reissuing it risks duplicates in the field; returning it to the pool is the same risk. It is held
until an operator reconciles it explicitly.

### 8.5 Write method

The write method is declared by the exact MCU Programming Profile and executed by the OPF
Provider. The generic contract admits four classes and binds none of them to a shared wire format:

* image patch into a reserved region (§8.2),
* plain memory write,
* vendor-specific factory command,
* OTP / one-time-programmable write.

OTP and vendor factory commands are **irreversible**. They are Fail-Closed: the step is attempted
once, never retried, and an unknown outcome quarantines the value and latches the Site.

### 8.6 Profile and Resource Set impact

Declaring personalization capability in the Programming Profile changes the Resource Set SHA256,
which forces a B1/B2/B3 reactivation across the fleet — the same cost already incurred by retiring
`flash_cycle` (§4).

**Normative sequencing:** the personalization Profile schema is fixed in the same Profile revision
as the `flash_cycle` retirement, so the fleet reactivates **once**. Implementation of
personalization may land much later; the schema may not.

## 9. Programming Route Admission

Admission is evaluated per `(ppu_alias, site_id, icpn, operations[])`:

```text
for each target, for each site:
    routes  = load_routes(ppu_alias)        # per PPU; never the first PPU's routes for all
    matched = resolve_routes(routes, icpn, site, operations)
    len(matched) == 0 → 422 operation_not_in_profile
    len(matched)  > 1 → 409 programming_route_ambiguous
```

The Manager already implements this per plan. The gap is in the Console, which loads one PPU's
Routes and uses them to gate every PPU (`software/web/app/fleet/factory-console-v2.tsx`). The
Console must load and apply Routes per PPU.

## 10. Receipt and Recovery

The Receipt v3 fields are unchanged. A Batch adds a per-Target aggregation and must **not**
re-decide a result: PASS requires both the Batch outcome and each Site run's own receipt passing
on its own terms (single submission, SAFE_OFF verified, Job Binding and Resource Set confirmed,
readback matching when the list verifies, and the personalization evidence when §8 applies).

Recovery, reconnection and the read-only `start_id` reconciliation are unchanged in meaning and
extended per Site.

## 11. Legacy retirement boundary

The legacy direct-Gateway batch path retires in PR-F, per consumer, per the Inventory. Four
constraints are normative now:

1. Read Memory's functional contract and its valid tests are **kept**; execution moves to the
   Manager-owned Read Job.
2. Mock/CD is **kept** and migrated onto the unified engine (§4).
3. No file is deleted merely because it belongs to the legacy path; each is judged
   delete / migrate / keep.
4. Nothing may claim the legacy path is retired before PR-F lands.

The alias-scoped Manager Batch API is **not** in this scope. It is part of the Manager-owned path,
it is superseded rather than legacy, and it retires in PR-C under the conditions in §5.8.

## 12. Delivery order

| PR | Content | Depends on |
| --- | --- | --- |
| PR-A | this contract | — |
| PR-B1 | mock `run_operations` + per-step evidence | PR-A |
| PR-B | Manager Batch Orchestrator on `targets[]` | PR-A |
| PR-C | EMode multi-Site Console; consumers migrated off the alias-scoped Batch API and that entry removed (§5.8) | PR-B |
| PR-D | PMode shared engine, `operations[]` switch, execution-route constraint lifted | PR-B, PR-B1, PR-C |
| PR-E | host-only tests and E2E | PR-B..PR-D |
| PR-F | legacy retirement, per the Inventory | PR-D |
| PR-G | Device Personalization implementation | PR-A, PR-B |

PR-C and PR-D are not parallel: both change the shared managed-programming module.

## Qualification

Nothing in this document is hardware evidence.

* No Z2, FPGA, DUT or real IC programming was executed to produce it.
* Multi-Site and multi-PPU scheduling are **NOT_RUN**.
* Eight-channel concurrency is **NOT_VERIFIED** and is explicitly out of scope.
* The `flash_cycle` retirement and the Profile revision in §4 and §8.6 require their own Site 2
  HIL acceptance before the fleet is migrated.
* Device Personalization has no implementation and no hardware acceptance.

Merging this document authorizes no deployment and no hardware operation. Each following PR
carries its own Gate 2.
