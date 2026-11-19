# Unified 8-Site Scheduler, Manual Repeat and Work Order Quantity — Architecture Contract v1

Status: **Owner-approved Gate 1 design freeze (2026-11-15); PLANNED, NOT IMPLEMENTED, NOT HIL-QUALIFIED.**
This contract freezes intended behavior, not an active REST schema, wire protocol, deployment, or claim of 2/8-Site hardware concurrency. No code, configuration, services, FPGA or DUT are modified by this document.

Related decisions: [Unified Programming Architecture v1](unified-programming-architecture-v1.md), [Manager Batch Retry/Stop v1](emode-batch-retry-stop-policy-v1.md), [ADR-0007 Site locks](../adr/0007-ppu-reload-fence-per-site-locking.md), [ADR-0010](../adr/0010-unified-site-scheduler-repeat-work-order.md), and the [development debt register](../development/todo.md).

## 1. Source of truth and scope

One **Manager-owned Scheduler**, **Repeat/Quantity Engine**, **Site Execution Lane**, **Job Lifecycle**, **durable Journal**, and **Fault Isolation** serve EMode and PMode. EMode selects one PPU with one or more Sites; PMode can select multiple PPUs and Sites. UI differences and the business origin of the quantity **must not produce two execution engines**. The Browser never submits per-Cycle Jobs, schedules repetitions or declares manufacturing PASS.

Manual and Automation are **execution intents** (business inputs), not different hardware/Provider paths:
- **Manual intent**: explicit Repeat Count per selected Site and operator-controlled next placement.
- **Automation intent**: an external MES/Work Order controls one global good-unit Target Quantity; machine/fixture controls physical presentation and readiness. The UI's Manual Repeat value is ignored, not copied or multiplied into Work Order quantity.

The Manager owns dispatch, accounting, recovery, concurrency and stop policy; each PPU owns Job admission, Site leases, actual Provider/FPGA operations and authoritative Job/SAFE_OFF observations. MES/PLC/fixture signals only establish eligible physical presentation. They never directly bypass Manager/PPU safety gates. Socket/fixture identity is distinct from one-based Site ID.

**Current implementation state:** `plasma_manager/programming_batch.py::_run_units` runs one bounded lane per Site (WP-01). Manual Repeat v1 (WP-02, PR #1501, Host-only; **not deployed, not HIL-qualified**) admits `policy.repeat` 1..10000 per Site with `replace_ic_before_next_cycle`; see §4.1. There is no Work Order / Automation quantity engine. A fresh Z2 install writes `max_concurrent_jobs: 1`, despite supporting up to eight Site identities; an upgrade or reinstall keeps the operator's existing `ppu.yaml` value. Older Gateway/Mock Batch `repeat_count` is **not** this future Manager contract. Preserve the working single-Site path and all existing Root/FPGA/PPU guards until independently qualified replacement.

## 2. Frozen conceptual intent (future versioned schema; not an active endpoint)

A Batch/production session has **exactly one** of these mutually exclusive inputs. These field names describe the future contract; no request using them is admitted by the current API.

```text
ExecutionIntent =
  Manual {
    repeat_count: integer [1, 10000],             # per selected Site
    replace_ic_before_next_cycle: boolean = true
  }
  | Automation {
    work_order_id: nonempty identity,
    work_order_revision: monotonic/revision identity,
    target_quantity: positive integer,             # total GOOD units, across all PPUs/Sites
    max_makeup_presentations: nonnegative integer = 0,
    product/ICPN, Programming Profile and Image identity,
    authorised PPU/Site pool, fixture/lot identity,
    stop/quality policy and authoritative MES issuer
  }
```

No per-Site multiplication of `target_quantity`; Automation does not derive quantity from `repeat_count` (or from a previous Manual UI state). A Work Order may span many scheduling windows/Batches but is one durable accounting domain, bound to an immutable revision and product/firmware identity. Modifying the target, allowed devices, image or material policy requires an explicit versioned Work Order amendment and idempotent reconciliation; never mutate an in-flight Job Binding.

**Interpretation fixed for v1:** `target_quantity` means the number of **qualified PASS physical units** required. A MES that means input pieces or total processed pieces must map that value to a distinct named field before admission; it must not silently reinterpret Target Quantity. Work Order quantity has no arbitrary Manual `10000` limit; validation shall use explicit system capacity/range limits when implemented.

## 3. The shared execution model

- **WorkOrder**: external business object / good-unit quota; only Automation binds one.
- **Batch / Session**: Manager-owned admission, target set and operation/resource identity; every Site uses the same canonical Manager execution path.
- **Site Lane**: the per-`(ppu_id, site_id)` sequential queue/owner; at most **one active Cycle/Job per Site**. Different healthy Sites run simultaneously up to demonstrated PPU resource and hardware capacity.
- **Presentation**: one physical DUT placement/fixture token. Never infer a different IC solely from a new Job or elapsed time.
- **Cycle**: one logical ordered E/P/V programming flow on one Site/Presentation, with a unique `cycle_id`, outcome and journal entry.
- **Attempt**: the initial Job or an authorised Retry **within the same Cycle**. Every attempt has a unique Job ID, plan/run identity and Receipt. No attempt ID or Job ID is ever reused for an otherwise separate Cycle.
- **Retry**: bounded, explicitly policy-eligible attempt on that same Cycle/Presentation. Never increments `completed_cycles` or processed/qualified physical-unit counts a second time.
- **Repeat / next Cycle**: a new logical Cycle only after the previous Cycle's terminal disposition, SAFE_OFF and subsequent placement/readiness requirements are satisfied. Each Cycle receives its own new Job ID and Receipt; retries inside it also receive new Job IDs/Receipts.

Execution is `Ready -> Reserve quota/lease -> Admit -> Journal intent -> Submit once -> Observe -> Reconcile -> Terminal -> SAFE_OFF verified -> Release/Unload -> Next Ready`. Journal-before-submit and reconciliation are mandatory. A submitted Job is never blindly repeated after response loss, timeout or restart.

The planned Scheduler must not weaken current `start_id` at-most-once semantics, ordered E/P/V, exact ICPN/route/Job Binding, Asset/Resource Set identity, per-Site owner/execution lease, FPGA reload fence, Seals, PPU maintenance gates or Root-controlled SAFE_OFF. FPGA Image/Active Set changes are PPU-wide; only jobs proven to share a qualified compatible Resource/Profile may overlap.

## 4. Manual Mode

`repeat_count` is applied **independently to each selected Site** (1..10000). No global round barrier: Site 2 may start its next cycle while Site 1 is still running an earlier cycle. The count is Cycle count **not** Retry count.

`replace_ic_before_next_cycle = true` (**default**):
1. The first Cycle requires an explicitly ready/qualified fixture and an authorised Start.
2. After any definite terminal PASS or FAIL, the Site must prove SAFE_OFF and release; the next Cycle waits for the operator's explicit **IC replaced + fixture ready** confirmation.
3. Confirmation creates a new presentation token associated with that Site/Cycle. Repeated click, stale tab or duplicate confirmation is idempotent and must not create duplicate Jobs.
4. Operator confirmation is human attestation, not cryptographic proof of a new chip; do not treat it as MES-grade unique-device traceability.

`replace_ic_before_next_cycle = false`:
1. After a definite terminal Cycle and all safety guards, the same presentation/IC may automatically enter the next Cycle; no unload/reload acknowledgement is required.
2. This is a **Debug/Burn-in** use case. Up to 10000 programming PASS Cycles against one IC are **not** 10000 qualified physical units. Present separate `pass_cycles`, `fail_cycles`, `attempts`, `unique_presentations`, and `physical_good_units` (not applicable to debug unless separately proven).
3. Unknown outcome, missing SAFE_OFF, Sealed Site, fixture fault, invalid/changed Resource or failed admission always override auto-continuation.

Definite operational FAIL may proceed to a new placement/cycle only if the configured Site/stop policy allows it and all safety checks succeed. Infrastructure ERROR is not a failed IC. Stop Queuing prevents future Cycle/Retry dispatch but does not fabricate cancellation of a submitted Job.

### Manual Repeat v1 owner decisions — 2026-11-19 (WP-02 Gate 1 clarification)

The following narrows **Manual v1** only. It does **not** authorise MES/Work Order features, 4/8-Site physical qualification, deployment, or hardware operation. It is a design/implementation contract, not evidence of a shipped feature.

- `repeat_count` is **1..10000 per selected Site in one Manual Session**, not a global Batch quota or the lifetime limit of the machine. For N selected Sites the nominal planned Cycle count is `N * repeat_count`, but no physical parallel-capacity claim follows. The limit is validated at the Manager admission boundary; avoid an arbitrary hardware/Provider hardcode.
- The requested count means **scheduled logical Cycles, not PASS units**. A Cycle with a trustworthy definitive final `FAIL` consumes exactly one position; e.g. when Cycle 37 fails in a 100-Cycle plan, the next planned Cycle is 38 and the total remains 100. Retry Attempts do not consume additional positions. An unsubmitted `BLOCKED` or unresolved `OUTCOME_UNKNOWN` is **not** a settled Cycle and cannot be silently skipped. Report planned, settled, PASS, FAIL, remaining and Retry Attempts separately.
- After a **definitive final FAIL**, and only after eligible Retry is exhausted, pause **that Site lane** by default; healthy independent Sites continue. Existing PPU-wide UNKNOWN latch, shared Root/Image/Power ownership, Journal failure and safety guards have higher precedence than site-local pause. A definite FAIL with missing verified SAFE_OFF may be counted as a failed Cycle but stays safety-blocked; never automatically release the Site.
- In default **replace-IC** mode, PASS and definite FAIL share **one** operator continuation flow. The UI shows the result (and additional diagnostic detail for FAIL); the operator physically replaces the IC and presses the **existing Start/Continue action once**. That action doubles as operator attestation of replacement/fixture preparation; no second checkbox, Reason Code, free-text field or second Start action is required. The Manager verifies authenticated operator/session/Site/cycle identity and authoritative readiness before accepting a new Job.
- Record an immutable operator action event: unique/idempotent action identity, authenticated actor, UTC time, Session/PPU/Site, previous Cycle/outcome and new Presentation identity. No operator-entered failure reason is required: trusted Job/Attempt/Receipt, operation errors, Job Binding, Resource Set and SAFE_OFF provide technical evidence. Operator acknowledgement alone **does not** prove a physical IC identity or actual Socket power-off.
- The normal continuation reuses the **existing Manager-owned Batch → Site Lane → Plan → Run → PPU Job → Receipt** execution path, with a fresh Cycle/Plan/Run/Job identity. It never creates another browser scheduler or a competing top-level Batch per Cycle. Each Start/Continue event is version-checked and idempotent; persist intent before at-most-once Job submission. Stale/duplicate clicks, restart, Stop, lost response and UNKNOWN must not trigger duplicate hardware work.
- In **same-IC Debug** mode (`replace_ic_before_next_cycle=false`), a definite PASS can automatically enter the next Cycle after all existing safety/admission gates. A final definite FAIL still pauses for explicit operator continuation on the same Presentation; its repeated PASS Cycles never count as distinct manufactured ICs.
- On final Cycle `repeat_count`, a trustworthy PASS or definitive FAIL plus completed safety/reconciliation obligations ends that Site without requiring another replacement. Report `COMPLETED_WITH_FAILURES` when all planned Cycles settled but at least one final Cycle FAIL; do not call it an all-PASS Session.
- The first release reuses the existing Console interaction and Manager Session/Batch; perform only necessary minimal UI/API changes. **No new human approval gate** is introduced. A shared manager-level `Stop Queuing` remains distinct from per-Site pause; Stop does not cancel an already submitted PPU Job. Journal/retention must be sufficient for 10000 Cycles and restart reconciliation, without orphaning consumed Start identities.

**Implementation evidence required:** focused Host-only/Mock tests of 1/10000 validation, initial `repeat=1` compatibility, PASS/FAIL counting and Retry separation, replacement acknowledgement, debug auto-continuation, 2-Site pause isolation, Stop-vs-dispatch race, duplicate/stale operator action, Journal failure, UNKNOWN/restart reconciliation, retention and per-Site progress. Include affected Console and BFF/Manager contract checks; only later owner-scoped HIL may prove real programming. Do not claim WP-02 complete from this documentation delta.

### 4.1 Manual Repeat v1 implementation (WP-02 Gate 1, Host-only)

Evidence class: Host-only / Mock tests and Console E2E with a scripted Manager. **No Z2, FPGA or DUT execution backs this section.**

- **One engine.** The Site lane of the existing Manager Batch loops over Cycles; each Cycle reuses the unchanged attempt loop (fresh plan → run → PPU Job → Receipt per attempt, Retry inside the Cycle). No second scheduler, Batch per Cycle or Browser loop.
- **Accounting.** Each Batch unit carries `cycle = {planned, index, cycle_id, state, disposition, settled, pass, fail, retry_attempts, continue_seq, continued_seq, wait_reason, last, last_continue}`; the view adds `remaining` per Site and Batch-level `cycles` totals. A one-Cycle Site reports its Cycle's own outcome/reason exactly as before. A multi-Cycle Site ends `PASS` (all PASS), `FAIL` (`COMPLETED_WITH_FAILURES` or a stopped session with a failed Cycle) or `PARTIAL` (Cycles remain); `OUTCOME_UNKNOWN` outranks everything and is never settled.
- **Pause / Continue.** After a settled Cycle the lane enters `AWAITING_CONTINUE` (`REPLACE_IC`, `FAIL_REVIEW`, or `NEXT_CYCLE_<reason>` when the next Cycle's admission was `BLOCKED` with nothing submitted). Same-IC Debug PASS skips the pause. `POST /api/programming/batches/{id}/continue {ppu_alias, site_id, continue_seq}` is the existing Start: the accepted `continue_seq` is answered idempotently (`duplicate: true`), any other value is `409 programming_continue_stale`, Stop wins (`409 programming_batch_stopping`), and the next Cycle still passes every dispatch/admission gate. A Cycle whose run lacks a trusted terminal state with verified SAFE_OFF is counted but ends the Site `SAFETY_BLOCKED`; it is never continued.
- **Which Site continues (Console).** START continues only the waiting Sites the operator marked "IC replaced"; while a Site waits, its existing Site checkbox (EMode row / PMode tile) is that mark, keyed to the exact pause `(alias, site, continue_seq)` so a new pause never inherits an old mark. A one-Site Session is unambiguous and START alone continues it. An unmarked waiting Site is never treated as replaced and gets no Job. With Sites waiting and none marked, START is disabled.
- **Release after a Cycle.** If the next Cycle's admission reads `SITE_NOT_READY_OR_BUSY` (the PPU has not yet released the Site it just finished), the lane re-reads the same gates every 0.5 s for at most `RELEASE_WAIT_S` (15 s), then falls back to the `NEXT_CYCLE_EXECUTION_SITE_NOT_READY_OR_BUSY` pause. Stop / latch / shared-control checks still run on every pass; nothing is submitted until admission passes.
- **Operator identity.** The Control Station BFF refuses a browser-supplied `actor` and injects `maintenance-capability:<digest>` derived from the HMAC-verified maintenance capability of that Site's PPU (there are no personal operator accounts). Direct Manager callers are recorded as `manager-api`.
- **Journal.** Settled Cycles, blocked dispatches and Continue events are appended (fsync) to the Batch's cycle segment `<journal>.v2.cycles/<batch_id>.jsonl` **before** the main record changes; the main record keeps counters plus the current Cycle only, so a 10000-Cycle session does not grow the record rewritten on every change. A crash between the two writes is recognised by `cycle_id` and counted once. The segment is pruned only together with its Batch (existing 32-Batch retention). `GET /api/programming/batches/{id}/cycles?offset&limit` pages it (Manager API; not exposed through the BFF). Workflow runs kept in memory now follow the journal's run retention (64 terminal + every active/UNKNOWN run).
- **Restart.** Plan bytes are not journalled, so a session is never resumed after a Manager restart: a paused Site ends `MANAGER_RESTARTED_SESSION_ENDED` with its counters; an in-flight Cycle follows the existing never-resend rule.
- **Known limits (Gate 2 / HIL inputs):** an active Repeat session holds its PPUs (another Batch on them is `409 programming_batch_in_progress`) until it ends or is stopped; `plasmactl program` still submits `repeat: 1` only; a Site still unreleased after the bounded wait pauses rather than waiting longer; EMode's top Batch Summary KPIs still count Sites, while Cycle counts appear per Site row and in the Log. PMode reports a Repeat Site's rounds as settled Cycles (PASS + FAIL) with PASS, FAIL and Retry separate, and relabels its IC KPIs as Cycles in same-IC Debug.

## 5. Automation Mode: global Work Order quota

The Work Order's `target_quantity` is a **global PASS quota**, not `target_quantity × site_count`. Scheduler allocates opportunities dynamically to any eligible Site and never requires every Site to run the same number of units.

**Canonical counters (unique physical Presentations, final dispositions only):**

```text
pass_units      = count(distinct presentation_id with final qualified PASS)
fail_units      = count(distinct presentation_id with final definitive IC FAIL)
processed_units = pass_units + fail_units
error_events    = infrastructure / transport / hardware failures (not IC FAIL)
unknown_units   = presentations whose physical disposition is unresolved
retry_attempts  = extra Jobs on existing Cycle/Presentation (not processed units)
cycle_pass/fail = diagnostic Cycle outcomes (not Work Order unit counters)
```

A definitive FAIL consumes one presented IC, **not** a good-unit quota slot. Recovery from FAIL by a qualified Retry on the same Cycle results in one final PASS physical unit, with failed attempts recorded separately. No double accounting after UI reload, Manager restart, receipt replay or MES reconnect.

**Quota reservation invariant:**

```text
pass_units + reserved_good_unit_slots <= target_quantity
```

Before dispatching any new physical unit the Manager journals an exclusive, idempotent quota reservation keyed by `(work_order_id, revision, presentation_id)`. A reservation stays occupied while the outcome is in-flight/unknown. On final PASS it is consumed into `pass_units`; on definitive FAIL it releases the good-unit slot and increments `fail_units`; an uncertain result never releases it automatically. This bounds simultaneous in-flight work near the target and prevents eight Sites finishing eight extra PASS units after only one good unit was still required.

**Make-up / shortage policy (v1):**
- Only a new, distinct fixture presentation may replace a **definitive FAIL** to fill remaining good-unit quantity; it is **not** a Retry and must pass normal Fixture Ready + Job/Resource admission again.
- Automatic replacement is permitted only within a Work Order-approved **`max_makeup_presentations` budget**, counted against extra distinct physical presentations beyond the first `target_quantity`. Default is **0 (NO_AUTO_MAKEUP)** if MES does not supply such an allowance; there is no invented percentage or unbounded replenishment.
- Within the allowance, Scheduler assigns the next eligible Site, not necessarily the Site that failed. Exhausted allowance, insufficient supply, no healthy Site, stop threshold, or ended shift/expiry transitions to **INCOMPLETE/SHORTAGE** or **PAUSED**, not fake COMPLETED.
- A MES-authorised, revisioned quantity/budget amendment can resume safely after outstanding reservations and start IDs are reconciled. No implicit restart of previously failed/unknown Jobs.
- The approved Work Order may separately define when an unqualified physical unit should be scrapped/reworked; a rework operation must not double count a presentation or evade its identity policy.

**Completion:** emit `COMPLETED` only if `pass_units == target_quantity`, no accepted/in-flight/unknown Cycle or quota reservation remains, all affected Site Jobs have terminal receipts and safe release evidence, and the final journal state is durable. Completion notification to MES uses a durable idempotency key; retrying **only the notification** must never dispatch a new Job. If PASS target is met but any unknown/release obligation exists, report **TARGET_MET_PENDING_RECONCILIATION**, not COMPLETED. STOP/PAUSE/SHORTAGE retain their own truthful state/reason.

## 6. Fixture / MES handshake (transport-agnostic future interface)

MES is authoritative for `work_order_id`, revision, target quantity, product and permitted production conditions. The automation controller/PLC is authoritative for **observable fixture events**, not hardware programming authority. The Manager is authoritative for quota, Job dispatch and accounting. Transport (authenticated API, fieldbus, GPIO bridge, industrial controller) remains implementation-specific; **no pins, voltage, signal polarity, timing bounds or REST paths are qualified or frozen by this document**.

Required logical events per Site:

| Event | Issuer -> consumer | Required invariant |
| --- | --- | --- |
| `WorkOrderAccepted` | Manager -> MES | Authorised immutable revision; target and product snapshot |
| `PresentationReady` | PLC/fixture -> Manager | Site, presentation token, fixture identity, monotonic sequence, qualified ready/interlocks |
| `CycleGranted` | Manager -> PLC | Unique token after quota and safety reservation; exact Work Order/Site binding |
| `JobStarted` | Manager -> PLC/MES | `cycle_id`, `job_id`, receipt correlation; one submission |
| `CycleTerminal` | Manager -> PLC/MES | Verified PASS/FAIL/BLOCKED/UNKNOWN and final per-Cycle evidence |
| `SafeToUnload` | PPU-observed via Manager -> PLC | **Only** after authoritative SAFE_OFF and lease release, not just HTTP success |
| `UnloadAcknowledged` | PLC/fixture -> Manager | Site, exact presentation, confirmed unloading/clearance |
| `NextPresentationReady` | PLC/fixture -> Manager | Fresh presentation token / readiness after unload |
| `SiteFault`, `StopQueuing` | Manager or authorised controller | Distinct fault domain/reason; no unsafe in-flight cancellation assumption |
| `WorkOrderTerminal` | Manager -> MES | Exactly-once business accounting, idempotent delivery |

Both sides must persist correlation IDs and reject duplicate, stale, out-of-order, replayed or mismatched Site/Work Order/presentation events; a level-high `ready` alone is **not** another Cycle. Lost ACKs are reconciled by read-only status and durable event identity; unknown submission is never retried. Disconnected PLC/MES prevents *new* automatic dispatch on impacted lanes but does not falsify the outcome of an already submitted Job. Physical E-stop/power removal and electrical interlocks remain owned by qualified hardware and must not depend on this software handshake alone.

## 7. Concurrency, isolation and safety

1. Each Site Lane is FIFO/ordered for Cycles; no overlapping same-Site Jobs or premature release. Different eligible Sites can execute concurrently up to **qualified** PPU capacity and resource locks, with no global cycle barrier.
2. Site-local definitive FAIL/fixture fault blocks only that Site or triggers the specified Work Order stop policy. Other healthy Sites continue and may receive remaining quota. If the fault affects shared PPU Image/Power/Root/FPGA resources, apply the verified PPU-wide boundary; if Manager shared journal/auth/scheduler safety is unavailable, stop new global dispatch. A failure is not arbitrarily localised.
3. `OUTCOME_UNKNOWN`, unverified SAFE_OFF or Sealed state prevents any automatic **next Cycle** on the affected Site. Preserve the current **PPU-wide unknown latch** wherever existing Manager/PPU guards require it; narrowing it to Site scope requires proven independent resource ownership and separate implementation/HIL acceptance, never a documentation-only bypass.
4. Retry is allowed only for definitive eligible FAIL with trusted terminal receipt, one initial submission, confirmed binding and SAFE_OFF, and after a new PPU readiness check. Failed or unknown stop/lease/recovery observations block retry and repeat.
5. `StopQueuing` forbids future dispatch/retry; an accepted Job is observed to a real terminal state. User requested cancellation and verified hardware cancellation must remain separate signals.
6. Only one globally authorised PPU Active Resource/Image state is eligible at a time; no cross-Site FPGA reload while an affected Site is active. Preserve per-Site exclusive owner, Root fence and declared electrical interface/voltage/power protections.
7. Fair scheduling: no permanent starvation; enforce bounded queues, owner/Work Order admission priority and per-PPU concurrency budgets. Do **not** hardcode `8` as a safe active-job limit merely because eight Site IDs exist.

## 8. Durable journal, identity and recovery

Journal is one authoritative Manager-owned transaction/accounting store (an evolved durable implementation of the canonical Manager Batch journal; not a second PMode/EMode ledger). Versioning and migration must preserve historical evidence and active Start reconciliation. Required records:
- Work Order ID/revision/issuer, target, quality and make-up budget, product/Resource/Image identity, mode and snapshot.
- Per-Site Lane, presentation token and source (operator assertion or PLC fixture), `cycle_id`, immutable Job Binding, initial/Retry attempt IDs, `start_id`, `batch_id`, Run/Job IDs.
- Pre-submit quota reservation, submission state, qualified Receipt, SAFE_OFF, seal/lease evidence, terminal unit/cycle disposition, policy decisions and MES ACK state.
- Idempotent event identity, monotonic sequencing, timestamps and a verifiable retention/reconciliation policy sized for 10000 Manual Cycles and production Work Orders.

On Manager/PPU restart, all possibly submitted nonterminal Jobs remain UNKNOWN until authoritative reconciliation; never convert silent timeout into definite FAIL, release its reservation, or resend. Operator/MES acknowledgement of an unknown is an audited reconciliation action, not a way to forge PASS/FAIL. Journals cannot be silently truncated such that consumed Start IDs outlive their proof; retention/compaction must preserve immutable terminal summaries or equivalent signed/verified identity binding. Existing Journal limits (e.g., 32 Batches/64 Runs/256 Starts) are **not** proof of enough long-run capacity.

## 9. Qualification matrix and delivery boundary

| Gate / scenario | Required acceptance |
| --- | --- |
| Contract only (this change) | Docs-only; no runtime changes, CI PASS is documentation-only |
| Host-only 1/2/8 Site | Simultaneous Job overlap on disjoint Sites, no same-Site overlap; bounded fairness/stop; correct per-Site isolation |
| Manual Yes | 1/10000 bounds, initial Ready, new presentation + explicit replace ACK per cycle, stale ACK rejected |
| Manual No | Same presentation, automatic next Cycle only after safe definite outcome, 10000 Cycles do not become 10000 good ICs |
| Automation | Global target 1 with 8 ready Sites, cap in-flight reservations; target 9 over 8 Sites, dynamic distribution, no multiplied quantity |
| Quality/compensation | PASS/FAIL/processed/ERROR/UNKNOWN separately; retry one Cycle not extra unit; FAIL make-up only within budget; shortage INCOMPLETE |
| Failure/recovery | UNKNOWN/SEALED/SAFE_OFF unverified, lost POST, duplicate PLC event, reboot at journal-before-submit, MES disconnect, Stop and shared-vs-local faults |
| Hardware (future) | First two actual DUTs on PMOD A/B concurrently, Site-local fault while peer succeeds, correct SAFE_OFF, SWD waveforms, latency and measured throughput |
| Eight-Site (future) | Qualified Site I/O/power/voltage, actual 8 independent channels, no starvation, per-Site evidence, P50/P95/P99, 1/2/4/8 scaling |

Delivery is **contract -> bounded implementation PR(s) -> Host-only proof -> owner-authorised 2-Site HIL -> measured 4/8-Site HIL**. No Gate 2 merge, deployment, hardware work, operational privileges or production qualification is granted by this document. Continue to use the existing one-Site working path until a future approved implementation and safety evidence explicitly supersede it.
