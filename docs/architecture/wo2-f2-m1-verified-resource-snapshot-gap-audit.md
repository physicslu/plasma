# WO-2 F2 M1 — Per-Cycle latency gap audit and Verified Resource Snapshot design (Gate 1)

Status: **DESIGN ONLY / NO CACHE OR SAFETY DECISION CHANGE**  
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
