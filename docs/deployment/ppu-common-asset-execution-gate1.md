# PPU — One Asset Execution Layer (Python / Native C / FPGA)

**Gate 1 Host-only.** Depends on [B2 common Master authority PR #1251](https://github.com/physicslu/plasma/pull/1251), which is already merged into main. All execution callbacks are Host-only mocks in this PR. No Root/hardware operation is authorized.

## Shared execution contract

```text
Console chooses complete Asset Set (SHA) and explicit operation
   |
   v
Existing B2 Master approval (ONE whole-Bundle grant, all Package kinds)
   |
   v
B3 immutable Install/Verify → Single Active Asset Set (FPGA load only by explicit fpga_load=true in #1261)
   |
   v
One internal PPU Asset Execution Layer
   |  exact Active Set SHA, exact Package ID/version/kind/descriptor SHA
   |  current Master grant, no fallback, trusted Runtime owner/Job scope
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
  Kind, exact canonical Package descriptor SHA, and action `execute`.
- `prepare_asset_execution()`: rechecks full verified installed Active Set,
  exact Package identity and current device-local Master authorization.
  `AUTHORIZED_NOT_EXECUTED` is a **selection result only**, never READY.
- `dispatch_asset_execution()`: a single typed dispatch seam for all
  supported executable kinds. It requires a **trusted Runtime owner/Job
  context** and a **registered, trusted Executor adapter** supplied by
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

## Host-only acceptance / outstanding

- All three kinds have identical authority/identity/dispatch rules.
- Positive tests use fake trusted local adapters under a held, bounded
  owner scope, never actual Shell, Python process launch or FPGA Manager.
- Negative tests cover missing owner, missing adapter, forged/stale digest,
  wrong Package Kind/ID/Version, revoked Master approval, changed staged
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
