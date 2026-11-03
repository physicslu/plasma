# PPU — One Asset Execution Layer (Python / Native C / FPGA)

**Gate 1 Host-only.** Authorization follows [Owner Operation Authorization](ppu-owner-operation-authorization.md) (replaces the PR #1251 per-Bundle Master allowlist). All execution callbacks are Host-only mocks in this PR. No Root/hardware operation is authorized.

## Shared execution contract

```text
Console chooses complete Asset Set (SHA) and explicit operation
   |
   v
B2 owner `bundle.admit` authorization for the exact Bundle SHA (no device allowlist)
   |
   v
B3 owner `bundle.install[-fpga-load]` authorization → immutable Install/Verify → Single Active Asset Set
   |
   v
One internal PPU Asset Execution Layer
   |  exact Active Set SHA, exact Package ID/version/kind/descriptor SHA
   |  fresh owner `asset.execute` authorization bound to device, Active Set,
   |  Package identity and Job ID; Job lease must match; no fallback
   |
   +-- python     → qualified Python runtime executor [NOT WIRED]
   +-- native-c   → qualified Native process executor [NOT WIRED]
   +-- fpga-image → existing Protected Root FPGA Loader [NOT WIRED]
```

The common control action is `execute`; the selected trusted adapter
interprets it for its resource kind. For FPGA, this means a distinct,
explicit Controller-directed **FPGA configure** request, not an automatic
side effect of B2, B3, changing Active Set, or issuing a PROGRAM Job.

## Current software implementation

The existing Bootstrap factory scripts now include
`scripts/ppu_asset_execution.py`. It exposes:

- `AssetExecutionRequest`: immutable Active Set SHA, Package ID, Version,
  Kind, exact canonical Package descriptor SHA, Runtime `job_id` and action
  `execute`. `OwnerCredential` (device ID + paired credential) is supplied
  by the trusted Runtime only.
- `prepare_asset_execution()`: rechecks full verified installed Active Set,
  exact Package identity and a fresh owner `asset.execute` authorization
  (B2/B3 receipts are never execute authority).
  `AUTHORIZED_NOT_EXECUTED` is a **selection result only**, never READY.
- `dispatch_asset_execution()`: a single typed dispatch seam for all
  supported executable kinds. It requires a **trusted Runtime owner/Job
  context** whose lease yields the authorized `job_id` (a busy PPU/Site
  raises) and a **registered, trusted Executor adapter** supplied by
  local code. It repeats source and Active checks INSIDE the held scope.
  Missing or forged Executor/lease and mismatched execution receipts are
  rejected. No default executable adapters exist; no HTTP user can select
  an executable module, shell command or Root operation.
- FPGA Executor will reuse the existing
  `pl/hil/fpga_image_root.py` + `fpga_image_guard.py` and the reviewed
  Active FPGA Handoff. ABI, FPGA Manager, current-boot Owner Admission,
  Golden recovery and Site idle conditions are checked **at execution time**
  by that existing hardware boundary, not by a second B2 trust registry.

The shared dispatch plan deliberately does **not** create a new Python
Code Loader or Native C Process Launcher; neither has been approved/
qualified for arbitrary uploaded code. Future adapters must use
separately qualified, sandboxed/product-controlled execution methods,
not import or run a Bundle File just because its hash matches.

## Stage C-1: Runtime Job lease adapter and Package resources (Host-only)

- `SiteManager.package_action_scope(job_id)` is the trusted `execution_scope`.
  It uses the SAME execution lock, PPU lease and Runtime quiesce as Site
  programming Jobs: PPU-exclusive owner `package_action:<job_id>`; raises
  `PPU_BUSY` while any Job, other Package Action or quiesce is active; while
  held, Site Jobs and Runtime/Asset-Set quiesce are refused; always released,
  including on executor failure. It yields `{job_id, owner_kind, site_ids}`
  (enabled one-based Sites) and grants no hardware access by itself.
- `plasma.ppu.package-resources.v1` (`config/plasma-package-resources.json`,
  required for `python` / `native-c` execution, absent for `fpga-image`):
  exactly `{schema, sites, max_runtime_s}`; `sites` sorted unique one-based
  IDs (≤ 8, empty = no programming hardware), `max_runtime_s` 1..3600. The
  file is part of the Package identity, so it is covered by the owner
  `asset.execute` authorization; the parsed bytes must match the verified
  SHA-256. Dispatch denies any declared Site outside the lease
  (`ASSET_EXECUTION_SITE_NOT_LEASED`).
- Planner adds a fixed `entrypoint` {path, sha256}: python = exactly
  `python/main.py`; native-c = the single executable under `bin/`
  (`ASSET_EXECUTION_ENTRYPOINT_INVALID` otherwise). No request argv/path.

## Stage C-2: non-root Package process executor (Host-only)

`scripts/ppu_package_launcher.py::make_package_executor()` is the python /
native-c `trusted_executors` adapter, called by the non-root Runtime inside
`package_action_scope`:

- Refuses to run as root; refuses Packages declaring any Site
  (`PACKAGE_SITE_TRANSPORT_NOT_WIRED`) until the Site Transport broker
  (C-3); never opens `/dev/mem`, `/dev/uio*`, FPGA Manager or MMIO.
- Re-hashes the planned entrypoint before spawn; argv is fixed
  (`<python> -I -B -S main.py` or the single `bin/` file).
- Child: own session/process group, clean env (PATH, LANG, HOME, job and
  package IDs only), private 0700 work dir (removed afterwards),
  stdin=/dev/null, close_fds, stdout/stderr captured and bounded to 64 KiB,
  rlimits CPU=max_runtime_s+1, AS 512 MiB, NOFILE 64, FSIZE 16 MiB, no core.
- `max_runtime_s` timeout and the Runtime cancel event SIGTERM then SIGKILL
  the whole process group (grandchildren included); reaping is verified.
- Durable journal `<state_root>/<job_id>.json`: `running` before spawn →
  `succeeded|failed|timeout|cancelled` (or `outcome_unknown`);
  `interrupted_actions()` lists non-terminal records after a restart. One
  launch per `job_id`. Receipt `plasma.ppu.package-action-receipt.v1`.
- **Deliberately not a root `systemd-run` unit** (rootless design step 5):
  dedicated per-Package UID, network namespace and syscall filter are
  `NOT_QUALIFIED` and need a privileged helper or the Z2 permission matrix
  (separate owner decision). Z2 / DUT: NOT_RUN.

## Host-only acceptance / outstanding

- All three kinds have identical authority/identity/dispatch rules.
- Positive tests use fake trusted local adapters under a held, bounded
  owner scope, never actual Shell, Python process launch or FPGA Manager.
- Negative tests cover missing owner, missing adapter, forged/stale digest,
  wrong Package Kind/ID/Version, forged / wrong-device / wrong-Job / wrong-
  Package / wrong-stage owner authorization, busy or foreign Job lease, changed staged
  bytes and untrusted execution receipts.
- Production Runtime adapter wiring, user-facing Console command,
  current-boot hardware checks and live Z2 execution remain **NOT_RUN /
  NOT_QUALIFIED**. No implementation here modifies Root Entry
  `download|test|restore` or clears the SWD v5 MMIO Owner problem.
- No merge, deployment, SWPC/Z2 access, FPGA loading or DUT operation.

## #1261 integration seam (not yet wired)

PR #1261 independently implements explicit HTTP B3 `fpga_load=true` with protected Root Entry, deployment.lock, Runtime Quiesce, image identity, `plasma.ppu.b3-deployment-receipt.v2`, and recovery/unknown-outcome handling. This Draft #1252 MUST NOT introduce a second FPGA Configuration Owner or a second FPGA Manager sysfs writer. A future FPGA executor adapter shall delegate to the already-qualified #1261 owner/transaction semantics after exact Active/Package identity and current authority checks; a Host-only Python callback is not HIL proof. The legacy #1252 internal `execute` request is a selector, not a second HTTP B3 deployment API. Asset dispatch receipt cannot replace the B3 receipt until a producer/consumer migration is qualified.

## Privilege design and open evidence

The shared typed action contract is cross-kind; OS process identity is not. Python/Native C should use qualified non-root processes; FPGA Manager writes remain mediated by the current Root Guard unless a Z2 read-only permission matrix and later explicit HIL prove a narrower non-root path. Keep `/root`-backed recovery and `ProtectHome` boundaries until a separate evidence-backed migration. See [rootless Package Action design](../architecture/ppu-rootless-package-action-gate1.md) (merged from #1262). The Z2 rootless FPGA feasibility audit, real executor adapters, journal harmonization and HIL all remain **NOT_RUN / UNQUALIFIED** in this Gate 1 PR.


## B3 FPGA receipt read-only binding (Host-only)

\`validate_fpga_b3_receipt()\` now reconciles a trusted #1261 B3 v2 receipt with
the **exact selected FPGA Package** from the existing Active Set. It checks
the B3 transaction's loaded state, installed Set SHA, identity PASS,
current Runtime Site re-admission requirement and re-derived staged BIN /
Manifest SHA and Image ID. It does **not** call Root, change the Active Set,
open FPGA Manager, or create another Load API. Host-only cross-PR tests
exercise the real #1261 Coordinator with injected fake Root/lease and
negative receipt mutations.

The returned \`RECEIPT_MATCHED_ONLY\` is **not** a second FPGA approval,
independent MMIO readback, non-root proof, Runtime ready status or an
indication that this validator is wired into the live #1261 API. Actual
typed Runtime Executor wiring and full cross-kind Journal/Receipt remain
separately unqualified.
