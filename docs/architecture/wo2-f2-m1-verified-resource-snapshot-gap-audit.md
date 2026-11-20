# WO-2 F2 M1 — Per-Cycle latency gap audit and Verified Resource Snapshot design (Gate 1)

Status: §1–§5 **M1 DESIGN** (no cache); §6 **M2 IMPLEMENTED** (Host-only verified, Z2 NOT_RUN)  
Baseline: `main` `b6a608c770df7959e7bfb395c515c88c021f043b` (includes M0 #1515 `d953506c`).  
Evidence: M0 merged Host-only instrumentation; owner-supplied Claude Host/Mock validation report (2026-11-20). M0 Mock timings are **not** Z2 timings or measured production savings.

## 1. Problem and unit of optimization

The observed terminal-to-next-job approximately **2.4 s** is a previous overall observation, **not** a measured M0 critical-path decomposition on Z2. A one-time Batch setup delay does not multiply with Cycle count. Per-Cycle repeated checks do. Count the repeated work by **Batch / Site / Cycle / Attempt / Job**, and only then use verified time spent to choose an optimization.

Current Manual `policy.repeat` is planned **Cycles per Site**, not a MES Work Order's global qualified-unit quantity. Do not claim MES quota scheduling exists. Preserve independent Site lanes and the existing physical safety constraints.

## 2. Read-only call-path audit (current implementation)

| Point | Current call chain and frequency | Evidence and authority |
| --- | --- | --- |
| Initial Batch Admission | `ProgrammingBatchCoordinator._run_cycle(first=True)` runs one PPU-wide leader `_platform_block` (followers await a `Future`) and each Site `_site_block`. The earlier M0 `manager_cycle_admission` begins only in the subsequent retry loop. | Code confirmed; first-stage event missing in M0. A follower's wait time includes leader work; it is not another Platform request. |
| Admission within a Cycle | `_admission_block` calls Platform and Site gates; `target_block` calls Bootstrap `assets` and `_readiness`. First Cycle's loop may only re-read Platform when `site_verdict_fresh`, whereas later retries re-read both. | Code confirmed. M0 `manager_admission` is a child of `manager_cycle_admission` when called; do **not** add both durations. |
| Plan | `workflow.plan` re-resolves Routes, calculates image SHA for Bundle cache key, and calls Bootstrap `status`, `assets`, plus Gateway `/api/status?site` for PPU Resource identity. Bundle build itself has an existing reuse cache. | Code confirmed; each Cycle creates a fresh Plan ID and durable Start record. |
| Preflight | `_execute_run` calls `_readiness` before `PREFLIGHT PASS`; it calls `_readiness` again immediately before Job submission. `_readiness` issues `GET /api/health/ready` and `GET /api/status?site`, evaluates Site/PPU lease, activation, interface. `_execute_run` also calls Bootstrap `assets` after any activation and before submit. | Code confirmed; M0 had no dedicated spans around these stages or GETs. |
| PPU Site Status | `SiteManager.status(site_id=...)` runs `active_resources_snapshot` -> `_resolve_active_resources` -> PPU Active Set resolver, which re-derives the actual Resource identity. Unscoped UI status does not execute this. | Code confirmed; M0 records `ppu_site_status` and its nested `ppu_site_resources` span, **not additive**. |
| Active Set SHA-256 | `read_active_resource_identity` calls `read_active` **twice** (before and after derivation); each `read_active` calls `verify_staged` -> `_digest` of manifest and every declared payload. `read_active` is also used for pinning and Job execution flows. | Code confirmed. The second `read_active` rechecks **content and generation**, not merely pointer identity. Do not skip it without a separately approved, proven equivalent. |
| PPU Job enqueue | `SiteManager.enqueue` reserves execution ownership; pins Active Set; re-derives and verifies Job Binding and route; writes state; queues Job. Additional execution-time verification remains distinct. | Code confirmed; Job safety decisions cannot be replaced by Manager's cached opinion. |

Owner-supplied **Host/Mock MEASURED** evidence: 4 `GET /api/status?site` and 3 `GET /api/health/ready` per Cycle in tested flow; two full Active Set reads per Site Status; 7 per Job (3 enqueue, 4 execute). **CODE_INFERRED**: 3 Bootstrap `/v1/assets` reads per Cycle may trigger additional full verification. The estimate **4×2 + 7 + 3 = ~18** Active Set verify invocations/Cycle mixes measurements and inference; it is **not** 18 hash operations total (each invocation can hash multiple files) nor a Z2 timing. Bootstrap `status` also may involve anonymous and authenticated requests. Counts vary with first Cycle, activation/reuse, error branches and polling.

## 3. M1 added observation contract (still `PLASMA_M0_TIMING=1`)

M1 extends existing best-effort `PLASMA_M0` stderr JSON: no new flags, files, REST wire fields, durable writes or admission rules.

| Event | Scope / correlation | Meaning |
| --- | --- | --- |
| `manager_initial_admission` | batch_id, cycle_id, ppu_alias, site_id, attempt=1, platform_leader | Full first-stage PPU leader wait plus per-Site admission, emitted also on blocked/failed path. **Not additive** to other gate spans. |
| `manager_readiness` | site_id and execution_owner_id when present | Whole `_readiness` including health/status GET and predicate evaluation; emitted on failure. |
| `manager_readiness_http` | site_id, endpoint=health_ready/site_status | One Gateway GET and response parsing, emitted on failure; child of `manager_readiness`. |
| `manager_preflight` | run_id, plan_id, ppu_alias, site_id | Readiness invocation for PREFLIGHT only; its subsequent journal step is **not** included. |
| `manager_presubmit_readiness` | run_id, plan_id, ppu_alias, site_id | Fresh readiness invocation before Resource confirmation and POST; the Resource comparison itself is outside this span. |
| `manager_bootstrap_read` | ppu_alias, operation=status/assets | Bootstrap Coordinator read (including authenticated status and assets network calls). Span is inclusive; no credentials or response body logged. During B3 polls multiple events may occur. |
| M0: `manager_plan`, `manager_cycle_admission`, `manager_submit_http`, `ppu_site_status`, `ppu_site_resources`, `ppu_asset_sha256`, `ppu_enqueue` | Existing fields and scopes | Reuse existing evidence. `manager_admission` and child spans overlap their enclosing timing; do not blindly sum. |

M1 does **not** add cross-host correlation to PPU Status or per-file SHA events because there is no authorized wire-level request identity. Correlate Manager `plan_id` -> `run_id` -> `submit_ack.job_id` -> PPU `enqueue.job_id` where present; same-host monotonic durations are reliable only within that host/process. Use recorded wall-clock/Job identity to align SWPC↔Z2 provisionally; do not subtract raw monotonic_ns between hosts. Bootstrap events use PPU alias, not exact Cycle ID; attribution to a Cycle must use same-host nesting and repeated-call evidence, never a claimed exact causal match.

Observability is not an audit authorization source. Diagnostics must be OFF by default, exception-safe, avoid image bytes, tokens and filesystem paths, and never affect outcomes when logging fails.

## 4. Proposed Batch-scoped Verified Resource Snapshot (future optimization **not implemented**)

### Candidate content / ownership

An immutable **Manager Batch view** may reference: `batch_id`, exact source/route/profile/ICPN and permitted operations, `image_sha256` and length, `resource_set_sha256`, expected `asset_set_sha256`, `generation`, `ppu_id` and paired device identity. A PPU-owned trusted verification result must separately bind the actual staged-file bytes, manifest, immutable generation, verified package/resource identity, storage trust and **which execution/activation fence protects that result**. A Manager-held hash or snapshot is a *comparison claim*, not PPU proof and never permission to Flash.

Snapshot must be versioned, bounded to the Batch and exact PPU/active generation, immutable to consumers, and rejected if incomplete or inconsistent. Its lifetime is not the same as a Job/lease lifetime. Persist/recovery must not silently reconstruct a previously qualified snapshot from untrusted metadata after a restart.

### Trusted invalidation prerequisites (fail closed)

Revalidate or refuse reuse after **any** change or uncertainty affecting:
- Active pointer, Asset Set digest or generation, B3 activation / rollback / recovery, Runtime or Bootstrap restart, paired controller/device identity, PPU config/route/profile/provider or FPGA paired-ABI identity.
- Staged payload/manifests, ownership, path traversal/symlink, directory or mount, permission, integrity or Root custody; unauthorized out-of-band edits and any storage mutability not covered by a trustworthy write/replace fence.
- In-flight or unknown B3, crash/restart, lost journal provenance, broken/external lease, inconsistent Manager↔PPU status, or inability to prove the exact cached bytes are still the bytes read by a Job.
- Expiry/retention of the evidence record, future revision of hashing/manifest schema and trusted validation implementation.

**File stat tuple `(inode,size,mtime_ns)` is not cryptographic identity.** Unchanged tuple does not prove unmodified content. Reuse a verified digest only when the trusted storage/ownership model makes mutation impossible or detects it synchronously and invalidates the result. Otherwise full read/hash is still required. A generation number that an adversary can leave unchanged is not a substitute for that protection. Preserve exact integrity check on the Job path unless a future Gate proves an equivalent trustworthy fence.

### Per-Cycle and per-Job non-cacheable boundary

Always preserve: current PPU/Root ownership, Site enabled/idle/queue and route, physical SAFE_OFF and Seal/recovery evidence, actual runtime quiescence, global/per-Site lease/reservation, exact Job Binding (PPU/Site/operation/ICPN/range/image digest and execution owner), fresh Job ID, single-submit durable journal and receipt provenance, `OUTCOME_UNKNOWN` no-blind-resend, bounded retries, actual Job terminal + SAFE_OFF before next Cycle. A prior Cycle's Ready/SAFE_OFF verdict is never evidence of the next Cycle's state. PPU remains authoritative for its staged bytes and execution admission.

## 5. Optimization candidates and gates

1. **Measure exact Z2 workload** under a *separately authorized* activation and controlled HIL; file size/count, SHA elapsed, Bootstrap network RTT, Status RTT and between-Job gap need real evidence. No M1 real-hardware authorization.
2. **Future M2 (separate Gate 1):** first evaluate safe elimination of redundant Manager-side immutable work/GETs, while preserving the pre-submit fresh check and independent PREFLIGHT receipt; justify each potential removed call by hazard, existing invariant and evidence.
3. **Future PPU reuse candidate (separate Gate 1):** require verified content immutability, privileged writer coordination and lossless invalidation BEFORE reducing `verify_staged` calls. Explicit negative tests: content mutation with unchanged stat, pointer/generation race, stale Batch, restart, B3 active switch, symlink/replacement, owner loss and per-Job Bindings.
4. **8-Site concurrency:** per-Site isolation is distinct from shared PPU resource identity, Root/FPGA/Power constraints. Never trade a PPU-wide unsafe side effect for latency.

Acceptance for **M1 only**: Host-only positive/negative test of enabled/disabled timing, first-cycle correlation, Bootstrap and Readiness error paths, required exact-HEAD CI. No claim of measured ~2.4 s improvement, no changes to decisions, caching, wire protocol, deployment, SWPC/Z2, PL or DUT.

## 6. M2 implemented: Batch-once preparation and Verified Resource Snapshot

Status: **Host-only verified; Z2 latency NOT_RUN / NOT_VERIFIED.** No wire, schema, journal or admission-rule change.

### 6.1 Per-Cycle call graph (Cycle ≥ 2, Resource reuse, no retry)

| Step | Before (M1 measured / code) | After (M2) |
| --- | --- | --- |
| Admission | Platform gate (Bootstrap `status`) → `target_block`: Bootstrap `assets`, `GET /api/health/ready`, `GET /api/status?site` | unchanged; `target_block` hands its passing `assets` + readiness to the next plan as single-use *evidence* |
| Plan | parse + base64-decode Image, load/resolve Routes, Image SHA-256 (Bundle cache key), Bootstrap `status` + `assets`, `GET /api/status?site` | Batch-once `_Prepared` (parse, Route, Image SHA, Bundle/Resource Set) reused; Bootstrap `status` still read; `assets` + Site status taken from evidence (same alias/Site, ≤ 2 s, else re-read) |
| Run | PREFLIGHT readiness, Bootstrap `assets`, pre-submit readiness + Resource identity, `POST /api/jobs` | unchanged |
| PPU `status?site` | 2 × `read_active` (full `verify_staged`) + derivation | 1 × full `verify_staged` + Snapshot hit |
| PPU enqueue | module re-exec + `read_active` (pin); 2 × `read_active` + derivation (Binding) | `read_active` (pin, helper loaded once); 1 × full verification + Snapshot hit (Binding) |

Host-only counted per Cycle (`test_per_cycle_call_counts_before_and_after`, Mock, no Platform gate in the rig): `status?site` 4 → 3, Bootstrap `assets` 3 → 2, Bootstrap `status` 1 → 1, health 3 → 3; Route loads `N` → 1 and Image decodes `1+N` → 2 per Batch. On a real Manager each Bootstrap `assets` is ≈ 4 HTTP (challenge, MACed status, challenge, assets), so the M1 18 Bootstrap HTTP/Cycle is expected to become 14 (code-inferred). PPU full Active Set verifications outside Job execution: Runtime 11 → 5 per Cycle (3 status + pin + Binding), Bootstrap 3 → 2 (code-inferred from the M1 model).

### 6.2 Batch-once preparation (Manager)

`BatchPreparation` lives in one Batch run (`_run_units`) and is shared by its lanes only; `_prepared_for` prepares under its lock, so concurrent first Cycles prepare once. It is reused only while the request (minus `site_id`) is equal **and** the SHA-256 over every Route file's name and bytes is unchanged (fingerprinted before loading); otherwise it prepares again. It holds no PPU state and is never persisted (Manager restart → the Batch is interrupted as before). Each Cycle still gets a fresh plan ID, journalled start, Job Binding (with live `ppu_id`), run ID and Job.

### 6.3 Evidence reuse — why each removed call is redundant

* **Plan Bootstrap `assets`**: the same authenticated read was done by `target_block` with no lane yield in between; plan re-applies `RECOVERY_REQUIRED` and Bootstrap↔Runtime Active Set consistency to it. The Run's pre-submit Bootstrap `assets` read is the fresh check and remains.
* **Plan `GET /api/status?site`**: plan used it only for `ppu_id` and the Resource report, which the admission readiness of the same Site just returned. The pre-submit readiness re-proves Site, lease, activation and `VERIFIED` Resource identity (`RESOURCE_IDENTITY_NOT_CONFIRMED` refuses the POST).
* **Retained with reasons:** Platform gate (fleet observation + recovery); plan Bootstrap `status` (only plan-time proof of `runtime_active` and MAC-authenticated pairing — the gate admits `runtime_absent`); PREFLIGHT readiness (independent receipt before any B1–B3 mutation); pre-submit Bootstrap `assets` and readiness (fresh pre-POST checks).

### 6.4 PPU Verified Resource Snapshot — trust and invalidation

No existing mutation fence (immutable attribute, fs-verity, read-only mount or a Root-owned write lease visible to the Runtime) proves the staged Set cannot change between Jobs. **Therefore full content verification is NOT cached**: every `status`, pin and Binding admission runs `verify_staged` (every file SHA-256, no symlink, no extra file). The Snapshot caches only the derivation keyed by `(product_root, asset_set_sha256, manifest_sha256)` that the same call verified, so:

| Change | Effect |
| --- | --- |
| Active Set switch / B3 activation / recovery | new `asset_set_sha256` or manifest → different key; `generation` always from the fresh read |
| File content change (even same size/mtime), unauthorised edit | `verify_staged` fails before any lookup |
| Symlink / path / staged-dir replacement | `verify_staged` / `_root` fail closed |
| Manifest swapped during a miss | manifest bytes re-hashed against the key; nothing stored |
| Runtime restart | process memory only; next call derives again |
| Snapshot vs Job Binding | `_admit_job_binding` still compares Binding, Provider/Profile, ICPN, PPU, Site, Image under the Job lease |

Remaining trust gap: removing the per-call full SHA/tree walk itself needs a storage mutation fence the PPU does not have today; it stays NOT IMPLEMENTED. The Snapshot authorises nothing and never bypasses Job admission.

### 6.5 Unchanged per-Job invariants

Site Ready/Enabled, PPU execution lease/ownership, Root Guard, SAFE_OFF/Seal/recovery, Job Binding verification, full Active Set integrity, fresh Plan/Run/Job identity, durable journals, `OUTCOME_UNKNOWN` no-blind-resend, terminal + SAFE_OFF before the next Cycle, B1/B2/B3 fences; independent Site lanes with no PPU-wide Cycle barrier (8-Site regression test).

## 7. WO-2 F2 M3 — Batch Resource Reservation

The Manager Batch ID is the PPU `rest_client` execution owner on each selected PPU. At Batch execution start the Manager reads that PPU's MACed Bootstrap `/v1/assets` once, reads the PPU verified Resource report, and acquires a PPU Runtime Reservation with the exact PPU ID, Active Set SHA-256, generation, Resource Set SHA-256 and Batch owner. Acquisition re-verifies the PPU Resource contents *under the same SiteManager `_execution_lock`* that guards Job admission and Runtime/Asset Set quiesce. A conflicting B3 activation is refused. One Reservation covers all Sites of that PPU; a multi-PPU Batch has one independent Reservation per PPU.

The PPU returns a random owner token and a fresh process epoch. The Manager keeps the token and Bootstrap asset snapshot only for the running Batch, never in the restart journal or a browser response. Each Job carries that token with its existing execution owner. PPU Job admission rejects a missing, foreign or expired token while a Reservation exists, and rejects a stale token after expiry. The Manager's existing Site status reads also check owner, PPU, epoch, Active Set, generation and Resource identity before Submit; the PPU still verifies the full staged bytes and Job Binding at admission. The Resource Snapshot remains a derived-data optimization, never integrity evidence.

The PPU Reservation TTL is 90 seconds. The Manager checks and renews it every 30 seconds while lanes are running or waiting for manual Continue; renewal re-verifies PPU contents. Normal Batch completion and Stop release it only after all lanes have ended and their last settled receipts confirm SAFE_OFF. An unknown outcome or unconfirmed SAFE_OFF does not issue Release; the PPU keeps active Jobs protected by their Job Lease independently of the Reservation TTL. A lost Release acknowledgement leaves the PPU TTL to expire. Manager restart closes interrupted Batches from the journal without resubmission and never reuses a former token. PPU Runtime restart changes the epoch and clears volatile Reservations, so the old Manager snapshot fails its next status check. Expiry can admit a later B3 only after all active Job leases end; the existing Site seal/Root Guard remains required for unsafe physical recovery.

The Batch start path requires an already Active, PPU-verified Resource Set matching the prepared Route. It fails closed when activation is required; this avoids performing B1/B2/B3 behind an unreserved Batch. The existing one-Job workflow still owns B1/B2/B3. Status/health GET remains independent of the Reservation. Reservation POST uses the Gateway's existing Controller Write Admission and is mapped to `site.job.submit`; the public Gateway offers only Acquire/Check/Release, and the PPU validates exact owner/token for Check/Release. The Manager calls it internally; it is not added to the managed browser relay allowlist.

Counted Host-only M3 path for one already Active PPU with N same-IC Cycles: Bootstrap assets `2N → 1` (the left side is the observed M2 call shape); Bootstrap status remains `N`; Site status `3N → 3N+1`; health `3N`; Reservation POSTs `2` (Acquire/Release) plus one Check per 30 seconds of Batch duration. There is no Check POST per Cycle. Each Site status and Job Binding still pays its full staged SHA-256 verification, so the cost of 30-second Check is additional and real net Z2 latency remains NOT_RUN. Job polling stays at 1000 ms. Host-only 8-Site overlap is software evidence, not a Z2 throughput claim.
