# Unified CLI Integration and Path 2 Load-Benchmark Retirement — Gate 1

**Status: Current Gate 1 record (2026-11-18).** Base: main
`7565ff0b11b897d5bd0c4809e3a9e01ca3689708`. Scope: host-only code, tests,
docs and CI. No merge, deployment, SWPC service restart, Z2/FPGA/SWD/DUT
operation or IC programming was performed. Canonical CLI documentation:
[`utilities/plasmactl/README.md`](../../utilities/plasmactl/README.md).

## 1. Caller / dependency inventory (main `7565ff0b1`)

| Item | Real callers found | Decision |
|---|---|---|
| `scripts/plasmactl` (Bash router) | installed `~/.local/bin/plasmactl` symlink; Z2 PS kit (`z2-ps-release.yml`, `ppu-bootstrap-kit.py` → Bootstrap runs `bash kit/scripts/plasmactl deploy z2-ps …`); Path 2 `CONTROL_STATION_OPERATOR_COMMANDS`; CI/tests | MIGRATE routing to `plasma_cli/operations.py`; keep a 30-line launcher (all callers unchanged) |
| `utilities/plasmactl` (#1476, read-only) | `scripts/plasmactl` | Canonical source; extended |
| `scripts/plasma_programming_load.py` (+ test, schema) | only Path 2 Work Orders and docs; no open Work Order depends on it | DELETE |
| Dispatcher `P2HW_*`, `p2hw-claim`, workflow `development-hardware-claim`, `PLASMA_P2HW_CLAIM_REF`, benchmark tarball | only the load runner | DELETE (dispatcher is byte-identical to pre-#1474) |
| `scripts/plasma_program.py` | Path 2 `artifact_source` Runtime-Kit route (`runtime-deploy`), docs | RETAIN (commissioning); Path 2 import removed |
| `ppu_path2_hardware_baseline.py` credential/transport | `plasma_program.py`, Path 2 preflights | EXTRACT to neutral `ppu_bootstrap_transport.py` (baseline re-exports) |
| `scripts/plasma_engineering_hil.py` | `plasmactl hil programming`, evidence doc | RETAIN (unique USB CDC verification) |
| `plasma_client/cli.py` (`plasma`) | PPU runtime/web/e2e scripts | RETAIN, documented as PPU-local debug client |
| `swpc-z2like` profile | kept by owner decision in #1481 | RETAIN |
| HIL-A2 claim, Z2 Root Guard | HIL-A2 Work Orders | untouched |

## 2. What changed

* **P0** `plasmactl program submit|status|receipt|reconcile|stop` over the
  existing canonical Manager routes (`/api/programming/starts`, `/batches`,
  `/starts/{id}`, `/starts/{id}/void`, `/batches/{id}/stop`). Multi-PPU,
  multi-Site Target Sets; Image, Bundle or erase range; Manager retry/stop
  policy passthrough; local exclusive submission journal before every POST;
  lost-answer reconciliation; no automatic resend; uniform exit codes.
  `test receipt` became `program receipt` (one name per operation).
* **P1** Profile routing for `install/deploy/verify/status/logs/restart` and the
  integration maintenance commands moved into the Python CLI. New backend
  operations: `logs`/`restart local-control-station`, `logs z2-ps` (read-only).
  `restart z2-ps` is refused: the Deployment Coordinator owns quiescence.
  The Z2 PS kit now ships the CLI package; CI runs the CLI tests under
  Python 3.10 (PYNQ System Python) and the kit launcher writes no bytecode.
* **P2** `plasma_program.py` uses `ppu_bootstrap_transport.py`; neither imports
  a Path 2 module. Validation, IP pin, device pin, request MAC and response
  proof are unchanged (code moved, not rewritten).
* **P3** Retired load runner, tests, schema, Path 2 hardware claim, workflow
  job/env/artifact paths; `plasma_hil_timing.py summarize` reads
  `plasmactl program` output. Historical claim refs, receipts and evidence are
  not deleted.

## 3. Before / After

| Metric | Before (`7565ff0b1`) | After |
|---|---|---|
| Implementations of the `plasmactl` command router | 2 (Bash router + Python read-only) | 1 (Python) + 30-line launcher |
| Manager-Batch programming entry points | 1 one-off two-Site runner (Path 2 only) | 1 generic `plasmactl program` |
| Programming-related operator entries | 4 (`plasma_program`, load runner, `hil programming`, `test receipt`) | 3 (`plasmactl program`, `plasma_program` commissioning, `hil programming`) |
| Python + shell files under `scripts/` and `utilities/` | 250 | 252 (−3 load/claim, +5 CLI/transport/tests) |
| Files deleted | — | 4 |
| Lines | — | +1,997 / −3,130, net **−1,133** (code/CI only: net −959) |
| Dispatcher P2HW branch | 140 LOC | 0 |

Removed duplicates: Bash and Python routing for the same commands; the
load runner's private Manager client, Start/journal/void logic and `/proc`
observer (now `plasmactl program` + `plasma_hil_timing.py proc-trace`); the
Path 2-only claim system; `plasma_program.py`'s subclass re-wrapping the
transport.

## 4. Eight-Site contract check (no Scheduler change)

The Manager admits up to 64 Sites/32 Targets per Batch and runs one bounded
lane per admitted Site (`programming_batch.py`); actual concurrency is bounded
by each PPU's `max_concurrent_jobs` (Z2 currently configured 2). No CLI
limit applies. Eight-Site concurrency has **no hardware evidence**. Known
separate issue (not changed here): Manager retains 32 Batches but 256 Start
records, which blocked a deploy preflight earlier.

## 5. Residual risk and NOT_RUN

* NOT_RUN: any physical programming, deployment, Z2 kit install with the new
  launcher, `logs`/`restart` on a real host. Mock/fake-Manager PASS is not a
  hardware PASS.
* The submission journal prevents duplicates within one workspace. Removing the
  P2HW claim restores the pre-#1474 Path 2 `operator-cli` behaviour: a workflow
  re-run of a hardware `operator-cli` Work Order is not blocked by a hosted
  claim. Any Work Order that runs `plasmactl program` through a dispatcher must
  rely on dispatcher Work Order admission; the CLI never treats a Runner as
  authority.
* First Z2 deployment after merge executes the new launcher on the Z2 under
  the Bootstrap Coordinator; covered host-only by the kit-layout test and the
  installed-Bootstrap (`783102b9e`) `verify_kit` compatibility test.
