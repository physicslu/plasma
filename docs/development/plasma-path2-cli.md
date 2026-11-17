# PLASMA Path 2 — SWPC CLI Execution Contract

**Status: Normative route-specific contract.** Root [AGENTS.md](../../AGENTS.md) governs approvals, Git, security and evidence; [Embedded](plasma-embedded.md) governs Z2 recovery, and [Common](plasma-development-common.md) covers shared programming and execution zones. This document specifies only Path 2 differences. Do not load the Path 3 contract for ordinary Path 2 tasks.

## 1. Scope and execution boundary

Path 2 is ChatGPT → owner-authorized GitHub Actions / existing trusted Dispatcher → SWPC self-hosted Runner → reviewed deterministic native CLI/Python commands → real result and evidence. Choose it when SWPC execution is required and bounded commands suffice. ChatGPT Direct is the default for source/docs/host-only work; Path 3 is for autonomous Codex diagnosis and iterative implementation. Path 2 **does not delegate execution to Codex**. Keep existing Path 2 identifiers for receipts and compatibility.

### Deterministic Host-only observation (no Codex tokens)

Before selecting Path 3 for an exact, non-interpretive SWPC query such as
`hostname`, prefer the **existing Path 2 `cpu-only` route**. The reviewed
`scripts/plasma_host_observe.py` accepts only one of `hostname`,
`kernel-release` or `python-version`; it never launches a shell,
Codex, SSH, network or device APIs. It runs under the existing Bubblewrap
`--unshare-all` sandbox; observations describe that process's namespace,
which must not be conflated with a privileged or global machine audit.

For an owner-authenticated Issue #981 dynamic Work Order, use:
`execution_path: "path2-cli"`, `capability: "cpu-only"`,
`scope: "host-only"`, `script: "scripts/plasma_host_observe.py"`,
`argv: ["hostname"]`, `verification: "exit-code"`, and a bounded
`timeout_seconds`. Retain the normal `schema`, `objective` and
`acceptance` fields. The code is source-pinned by the existing Dispatcher;
no new workflow, task registry, runner or privilege is introduced.

Exit code 0 verifies command completion, **not the factual correctness of
stdout**: check the stored Path 2 stdout/stderr/process receipt and record
the observed hostname as evidence separately. For an exact predictable
stdout, the existing `stdout-sha256` verification remains available.
GitHub-hosted mocks only prove the routing/sandbox contract; real SWPC
observation is NOT_RUN until separately authorized and executed.

## 2. Gate 1 Work Order and source binding

Use the existing Owner-approved, bounded Work Order and trusted dispatcher. Bind the exact owner PR HEAD / source SHA, scoped commands, capability, acceptance, environment, and evidence. Issue #981 Development Dispatcher can admit the exact HEAD of an open same-repository owner PR while its trusted entrypoint remains on main. A user-supplied SHA alone does not authorize work. No per-task Workflow, Registry task ID, third approval Gate, new Runner or Stage/Profile layer is implied. After Gate 1, execute the authorized test/fix/retest loop; Gate 2 is only for merging a PR.

## 3. Capabilities and permissions

- `cpu-only`: intentionally OS-sandboxed, no network/hardware; accepts source-pinned Python scripts under `scripts/`.
- `operator-cli` with `scope: guarded-hardware`: exact owner-approved, source-pinned Python script **or the existing `scripts/plasmactl` Bash entrypoint** on the **non-root** SWPC Runner, under actual DAC/ACL rights. Bash routing is limited to exactly `deploy local-control-station`, `verify local-control-station` and `status local-control-station`; it is not general shell execution. `install`, `--dev-fresh-state`, other deployment profiles, sudo and free-form shell commands are not authorized by this route. Existing `plasmactl` deployment preflight, clean committed source, Manager/PPU idle verification, user-systemd authority and rollback constraints still apply. The Runner must prove it owns the real installed Control Station; changing the interpreter does **not** grant that ownership. Exit 69 for unavailable prerequisites or 77 for permission denial **before operation** may be classified as NOT_RUN; a command that already attempted an operation cannot be relabeled NOT_RUN.
- Vivado host build: require the existing reviewed project-owned build contract, exact PR HEAD/source binding, verifier and real host-build evidence; a project ID alone is not qualification.
- The separate protected Z2 FPGA Image Root Entry accepts only `operation + source_sha` for its reviewed lifecycle/recovery operations. Never turn it into arbitrary root shell access or infer sudo/SSH/MMIO permission from Path 2.

Path 2 and Path 3 may share the existing SWPC Runner/account where approved scope and Linux rights permit; no automatic privilege escalation or separate SW/HW Runner. Preserve device ownership, electrical safety, verified Golden recovery, Root source/manifest checks and current state. Do not invent a per-device adapter or extra approval stage.

## 4. Execution, evidence and failure

Execute real SWPC acceptance **before Gate 2** if the task requires it. Record actual Runner/Run/Job, source SHA, commands, exit status, expected/observed result, hashes and relevant recovery. Use PASS/FAIL/NOT_RUN only for observed conditions. A GitHub-hosted mock is not SWPC/Z2/DUT evidence. Reuse valid existing results, fix only demonstrated gaps and rerun affected tests. An unavailable dispatcher, denied privilege or unsafe device state is an explicit blocker, never PASS. Never deploy or touch hardware beyond the Owner-approved Gate 1 scope.

## 5. Shared clauses retained by reference

Read [AGENTS.md](../../AGENTS.md) for Development Mode, source-of-truth, two-Gate, Git/CI and security; read [Embedded](plasma-embedded.md) for Z2 credentials, hardware ownership, protected Root and recovery.

## Programming loading benchmark (bounded two-Site development measurement)

Reviewed source: `scripts/plasma_programming_load.py`; data contract:
`specs/programming-loading-benchmark-v1.schema.json`
(`plasma.programming.loading-benchmark.v1`). This composes Manager plans,
Start/Batch and PPU Job receipts; it adds no programming engine or deployment.

On the existing non-root SWPC Runner, within an authenticated Work Order:

```bash
python3 scripts/plasma_programming_load.py measure --ppu z2 --sites 1,2 \
  --baseline-sec 15 --interval-ms 250 --recovery-sec 15 --timeout-sec 180 \
  --config /approved/loading.json --config-sha256 CONFIG_SHA256 \
  --output .plasma-path3-evidence/loading-benchmark --run-batch
```

The hash must be the SHA256 of the exact private JSON configuration bytes.
Without `--run-batch`, this command reports NOT_RUN without network or DUT I/O.
Use a **new** output directory for each owner-authorized measurement. An existing
submission journal always refuses another submission; never delete a journal to
retry an ambiguous operation. Reconcile its recorded `start_id` through
`GET /api/programming/starts/{start_id}`. A new output name is not permission
for another Batch under the same bounded Work Order.

**Cross-Run exactly-once.** `--run-batch` refuses (`HARDWARE_CLAIM_REQUIRED`,
before any configuration, Manager, Z2 or DUT I/O) unless the trusted Dispatcher
passes `PLASMA_P2HW_CLAIM_REF` equal to
`refs/heads/plasma-engineering-claims/981/p2hw-<work_order_sha256>`. That
protected ref is created atomically once per Work Order digest before execution
and can never be updated or deleted; a re-run, a re-posted identical Work Order
or a concurrent independent Run is denied. Creating it consumes the
authorization whatever the outcome. A workflow re-run (`GITHUB_RUN_ATTEMPT` != 1)
is additionally refused. A new physical attempt requires a new owner Work Order.

**Lost responses.** A lost Start response is recorded `start_issuance:
UNKNOWN` (random ID nobody holds; it expires) and no Batch is posted. A lost
Batch response is reconciled read-only; a still-admissible Start
(`ACCEPTANCE_PENDING`) is voided through `POST
/api/programming/starts/{id}/void`. The Manager serializes void and admission:
either the Start becomes `NOT_ACCEPTED` (reported NOT_RUN, never resent) or the
void is refused and the admitted Batch is tracked. Anything else stays
OUTCOME_UNKNOWN. `hardware_trace` (Start/Batch/per-Site physical result) and
`measurement_trace` (observer/benchmark result) are reported separately; a
measurement failure never rewrites a known Batch outcome to OUTCOME_UNKNOWN.

Example owner Issue #981 comment (replace the candidate PR/HEAD and configuration
hash; for merged main omit `pr_number`/`source_sha`, which are event-pinned):

```text
/plasma-dispatch work-order 981
{"schema":"plasma.development.work_order.v1","objective":"Measure one admitted two-Site Z2 E/P/V Batch with same-run idle and recovery baselines","acceptance":"Retain CSV/JSON/SHA256, exact Start/Batch/Job receipts and truthful physical outcome; no resend, install or merge","execution_path":"path2-cli","capability":"operator-cli","scope":"guarded-hardware","pr_number":1234,"source_sha":"REPLACE_WITH_REVIEWED_40_HEX_PR_HEAD","script":"scripts/plasma_programming_load.py","argv":["measure","--ppu","z2","--sites","1,2","--baseline-sec","15","--interval-ms","250","--recovery-sec","15","--timeout-sec","180","--config","/approved/loading.json","--config-sha256","REPLACE_WITH_CONFIG_SHA256","--output",".plasma-path3-evidence/loading-benchmark","--run-batch"],"verification":"exit-code","timeout_seconds":300}
```

Configuration fields (all required; identities describe the **current accepted
installed route**, never a static Engine version allowlist):

```json
{
  "manager": "http://127.0.0.1:18280",
  "image": "/approved/plasma-blue-pill-cdc-v0.2.bin",
  "image_filename": "plasma-blue-pill-cdc-v0.2.bin",
  "image_sha256": "REPLACE_WITH_64_HEX",
  "device_id": "REPLACE_WITH_ENROLLED_DEVICE_ID",
  "deployed_sha": "REPLACE_WITH_INSTALLED_SOURCE_SHA",
  "asset_set_sha256": "REPLACE_WITH_ACCEPTED_ACTIVE_SET_SHA256",
  "generation": 25,
  "resource_set_sha256": "REPLACE_WITH_RESOURCE_SET_SHA256",
  "route_id": "z2-site2-stm32f103c8t6-operations",
  "profile": "stm32f103c8t6-site2-operations",
  "fpga_image_id": "REPLACE_WITH_SAME_BOOT_ACCEPTED_IMAGE_ID",
  "fixture": ["REPLACE_CDC_SERIAL_1", "REPLACE_CDC_SERIAL_2"],
  "z2_python": "/opt/plasma/python/3.12.13/bin/python3"
}
```

The fixture field is the observed two-board CDC serial **pair**, not an inferred
CDC-to-Site association. The accepted physical Site wiring is reused; both
Site targets, route, profile, image, active set and loaded ABI-v5 identity must
still match. Serial symlinks are observed without opening USB/TTY. A live SWPC
OpenOCD process blocks the benchmark to avoid simultaneous ST-LINK driving.
The existing enrolled SSH helper retains its pinned host key and owner-only
credential store; existing installed Root/Engine guards and the Site Worker
retain lease, admission, UNKNOWN, recovery and SAFE_OFF authority. No sudoers,
Runner, service, route, profile, firmware or Bundle is changed.

One Z2 PS-local sampler runs unprivileged as `xilinx`, reading `/proc` only.
The controller uses the existing enrolled SSH transport for metadata and
bounded ephemeral staging; it never runs live OpenOCD on SWPC. READY includes
an actual first sample. The controller waits for at least 15 seconds of idle
samples, rechecks admission, issues one Start, journals intent **before** its
single Batch POST (repeat=1/retry=0), and observes exact-ID Batch/Job receipts.
Lost POST answers reconcile by Start ID; no branch retries POST. A lost Start
answer also stops without retry. Unsupported Batch collection GETs are unused.
Recovery begins after both terminal Jobs and observed OpenOCD exits, and lasts
at least 15 seconds. Existing post-program `reset run` is accepted for this
measurement; this is **not** no-reset or analog electrical qualification.

CSV contains UTC and Z2 monotonic time, PID/starttime/PPID, exact `plasma_swd`
Site mapping, CPU/RSS, host CPU and memory, observer overhead and scan duration.
JSON includes raw frames, lifecycle events, missed samples, phase n/duration,
mean/nearest-rank P95/peak, same-run idle deltas (CPU and RAM percentage points),
headroom, per-PID CPU/RSS, sampled overlap with uncertainty, bytes/elapsed,
readback and SAFE_OFF receipts, source and deployed identities. Host CPU uses
all-core capacity; PID CPU uses single-core capacity. RAM used is MemTotal minus
MemAvailable. Sample means are arithmetic, not time-weighted. Host load includes
sampler and SSH/control observation overhead; the baseline uses the same method.
Pre-POST and terminal boundaries use the last Z2 sample observed at each event;
uncertainty includes sampling gaps and scan time. No scaling to eight Sites.
Sparse phases are INSUFFICIENT_SAMPLES; absent overlap is NOT_OBSERVED. Separate
historic idle results remain illustrative NON_COMPARABLE evidence.

Output is private (0700 directory/0600 files), CSV + JSON + receipt files and
SHA256SUMS; stdout contains only a small bounded receipt (well below 64 KiB).
Use `.plasma-path3-evidence/` for the existing engineering artifact collector;
Path 2 packages the dedicated output as
`RUNNER_TEMP/plasma-path2-loading-benchmark.tar.gz` plus SHA256 through the
existing CLI artifact upload (no new evidence service). No credentials or raw
SSH transcript are stored. Each remotely collected file is capped at 64 MiB.
SIGINT/SIGTERM/timeout stops future Batch queueing through the supported exact-ID
stop API, observes already running Jobs for a bounded grace period and stops
only the sampler's verified PID/starttime. The Worker owns in-flight SAFE_OFF;
unconfirmed cleanup is OUTCOME_UNKNOWN, never NOT_RUN or a blind retry.

Historical source/evidence reused: observer Run 43890273943 / Artifact
14235919788 (PID-safe sampling), dual-Site HIL Run 44014287054 / Artifact
14298761141 (existing route and receipts). Those are prior evidence, not a new
execution of this CLI. Offline checks: `python3
scripts/tests/test_plasma_programming_load.py` and existing operator CLI tests.
