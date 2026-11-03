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

## Stage C-3: single-appliance Site Worker (Host-only)

Architecture: C-1 Job lease / authorization / quiesce → C-2 non-root Package
executor → **one local Site Worker** → replaceable Hardware Adapter → PL.
No broker framework, network service, session database, second Job engine,
journal, receipt or FPGA loader.

- `scripts/ppu_site_worker.py` (core): one Unix stream socket, one JSON line
  request/response, protocol `plasma.ppu.site-worker.v1`. Peer identity is
  `SO_PEERCRED` + kernel `/proc/<pid>/stat`, never a request claim.
  - Control (`open_session`, `close_session`, `status`): ONLY the trusted
    Runtime process (production: `plasma-server.service` MainPID), and
    `open_session` requires the C-1 lease to be held by that `job_id`
    (read-only Runtime control op `execution_lease`).
  - Transport: ONLY a peer in the registered Package process group with the
    same uid; a descendant that `setsid()`s out loses access. Request is
    exactly `{protocol, op, site}`; `op` must be in the adapter allowlist;
    the Site must be in the session, supported and not sealed; the lease is
    re-checked; one in-flight operation per Site (`SITE_BUSY`).
  - One session at a time (the C-1 Package Action lease is PPU-exclusive);
    sessions are in memory only, so a Worker crash invalidates them.
  - Fail-closed: adapter `TransportUnknown`, any adapter exception, timeout,
    Runtime cancel (`close_session`) during an operation, or an FPGA identity
    change during an operation **seal** the Site (persisted
    `<seal_dir>/site<N>.sealed`, survives Worker restart, never auto-retried;
    clearing is a separate operator recovery, not an IPC operation). An
    identity change between operations invalidates the session. Startup
    seals Sites with a leftover admission record, or all Sites while any
    OpenOCD runs.
- `scripts/ppu_site_adapter_abi5.py` (Hardware Adapter, Sites 1/2, op
  `probe`): existing root Site admission → PS-local OpenOCD `plasma_swd`
  (`dap init` + `dpreg 0`, fixed argv; no target/flash/erase/program/reset)
  → revoke (always). **Single hardware owner**: the adapter never maps MMIO
  or takes the ADR-0007 locks; OpenOCD's ps_owner does, as today. Refuses
  while another OpenOCD or admission record exists, or the Root journal is
  not `IMAGE` of the expected Image. SAFE_OFF not verified, kill, revoke
  failure or uncertain admission → `TransportUnknown`.
- C-2 wiring: `make_package_executor(..., site_worker=None)`. Default stays
  `PACKAGE_SITE_TRANSPORT_NOT_WIRED`. With a Worker client, the session is
  opened for (job, declared Sites, child process group, uid, max_runtime_s)
  right after spawn (the Package retries `NO_SESSION_FOR_PEER` briefly) and
  always closed; a refused session kills the Package (`FAILED`); a sealed
  Site sets receipt `hardware: UNKNOWN_SITE_SEALED`.
- Residual risk: Package and Runtime share uid `plasma` (C-2 dedicated UID
  NOT_QUALIFIED), so a hostile Package could still attack the Runtime process
  itself (e.g. ptrace, its control socket). Not deployed; no Z2/OpenOCD/DUT
  execution; Sites 3–8 not qualified; no SPI/I²C.

## Stage C production integration candidate (Host-only)

**Two-identity model.** Runtime = `plasma` (existing `plasma-server.service`,
unchanged unit + drop-in). Package Actions = `plasma-package`. Site Worker =
root (Site admission + PS-local OpenOCD need root; the Worker maps no MMIO).

- **UID switch** (`ppu_package_units.py`, renderers only; installer untouched):
  a non-root process cannot switch uid or signal another uid, so the Package
  runs in the fixed template `plasma-package@<32hex>.service`: `User=` /
  `ExecStart=` / sandbox are in the root-owned unit (NoNewPrivileges, empty
  capability set, PrivateDevices, PrivateNetwork + AF_UNIX only, ProtectSystem
  strict, ProtectHome, InaccessiblePaths over Runtime / Bootstrap / Root /
  Worker-control resources, syscall filter, cgroup kill, Tasks/Memory/AS/NOFILE
  limits). The Runtime manages those instances **only** through the
  fixed-purpose root helper `ppu_package_unit_helper.py`
  (`plasma-package-control.service`, socket
  `/run/plasma-package-control/helper.sock` root:plasma 0660, same pattern as
  the existing `plasma-runtime-activation` helper): peer must be the
  `plasma-server` MainPID with uid `plasma`; ops `start|stop|show|kill|list`
  only; the helper builds every systemctl argv itself from a 32-hex job_id
  (no unit name, path, property or command from the caller); `kill` allows
  SIGTERM/SIGKILL only; `start` requires the Runtime-owned job spec (regular,
  not group/other-writable). `HelperSystemctl` is the Runtime-side drop-in for
  `SystemdUnitSpawner(systemctl=...)`. No sudoers, no polkit grant. (A polkit
  JS rule was rejected: Z2 runs polkit 0.105, `.pkla` only, which cannot
  restrict `manage-units` by unit name — read-only matrix 2026-11-03.)
- **C-2 unchanged in substance:** `make_package_executor(..., spawner=)` only
  swaps the process primitive. `LocalProcessSpawner` (default) is the exact
  C-2 behaviour; `SystemdUnitSpawner` writes a job spec
  (`plasma.ppu.package-unit-spec.v1`) into the Runtime-owned world-readable
  `/run/plasma-package-specs`, starts the unit, polls / kills / stops it and
  reads output from the unit RuntimeDirectory. Identity validation, timeout
  and cancel decisions, journal and receipt stay in the C-2 launcher.
- **Fixed entry** `ppu_package_entry.py` (runs as plasma-package): re-validates
  the spec (exact fields, not group/other-writable), the entry (regular, no
  symlink component, inside `/opt/plasma/assets/staged/<sha>/payload/packages/<id>/`,
  `python/main.py` or one `bin/` file, SHA-256 match), clean env, no inherited
  fds, records exit status so the unit stays `active (exited)`.
- **Worker** (`ppu_site_worker_service.py`): `control.sock` root:plasma 0660
  accepts only control ops; `transport.sock` root:plasma-package 0660 accepts
  only transport ops. A Runtime restart (new MainPID) ends the open session.
- **Runtime composition** `plasma_server.package_actions.PackageActionRuntime`:
  C-1 scope → dispatch → C-2 executor (+ systemd spawner, + optional Worker
  client); `reconcile_on_start()` stops leftover Package units and lists
  interrupted journals. No public API endpoint added.
- **Seal Operator Recovery** `ppu_site_recovery.py` (root CLI, not IPC):
  `diagnose` (read-only) and `recover --operator` require: well-formed seal
  marker, Worker stopped, no active Runtime lease (or Runtime down), no
  OpenOCD / admission record, Root journal `IMAGE` of the expected Image, then
  adapter `verify_safe_off` and an unchanged re-check. Every attempt writes a
  0600 evidence record; success MOVES the marker into evidence; any failure
  leaves the Site sealed.

NOT_QUALIFIED until Z2: `plasma-package` account, unit-control helper,
systemd sandbox and cgroup behaviour, Runtime control socket DAC against the
Package uid, Worker capability needs, Root Guard interplay, real OpenOCD /
DUT. Not installed, enabled or deployed.

## Stage C Runtime trigger (Host-only)

Z2 Runtime release `296a0265` predates C-1, and nothing called
`PackageActionRuntime`; the Worker and unit helper trust only the
plasma-server MainPID, so a trigger inside the Runtime is required.

- **Root operator CLI** `ppu_package_action.py run --request R --authorization A`
  (root only, local, no network API): verifies the owner `asset.execute`
  authorization with the paired Bootstrap credential against THIS device
  (`/etc/machine-id` derivation), the requested Active Set, Package identity
  and `job_id`; mints a one-time random credential; re-issues the same claims
  under it; sends `{operation: package_action, request, authorization,
  ephemeral_credential, device_id}` to `/run/plasma-server/control.sock`.
  The Runtime never receives the Bootstrap token.
- **Runtime control op `package_action`**: disabled unless plasma-server is
  started with `--package-actions-config` (`plasma.ppu.package-actions-config.v1`:
  control_plane, product_root, state_root, python, package_user,
  helper_socket, site_worker_control_socket|null). Accepted only from a root
  peer (`SO_PEERCRED` uid 0); exact fields; runs
  `PackageActionRuntime.run_control` (C-1 scope → dispatch → C-2 executor with
  `SystemdUnitSpawner` via `HelperSystemctl`, optional Worker). Disconnecting
  the operator cancels the action. One launch per `job_id` (C-2 journal).
- **Readable Active identity**: `assets/active.json` and staged
  `b3-install.json` are now written root-owned **0444** (were 0600) so the
  non-root Runtime can re-verify the Active Set; they hold only SHA/
  generation metadata, like the existing 0444 `manifest.json`. Root
  `protected()` still accepts them (no group/other write). Existing Z2 Sets
  keep 0600 until the next B3.
- **Delivery**: the Stage C control-plane scripts ship in the factory
  Bootstrap kit (`/opt/plasma/bootstrap`, root-owned code, SHA256SUMS);
  unit renderers point there. Units / account / drop-in are still installed
  only by a separately approved Z2 Gate.

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
