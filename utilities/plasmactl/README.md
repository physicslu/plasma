# PLASMA Unified CLI (`plasmactl`)

Canonical source of the one PLASMA operator CLI. It is independent of the
development execution path: Path 2, Path 3 and a production Controller run the
same code, and none of them is required by it. GitHub Runner identity is never
programming authority.

* **Programming / diagnosis** use only existing Manager APIs. The Manager owns
  the Batch engine (Target admission, per-Site lanes, retry, stop policy,
  SAFE_OFF evidence, durable journal). There is no second scheduler here.
* **Deployment / maintenance** delegate to the existing platform backends
  (installer, Bundle v3/Bootstrap, Deployment Coordinator, Root Guard,
  rollback). The CLI core never calls systemd, sudo, SSH or a Z2 directly.

`scripts/plasmactl` is only the repository launcher (it sets the backend
directory) and ships with this package in the Z2 PS kit. The package is
Python 3.10-compatible (stock PYNQ System Python) and has no dependencies.

```bash
python3 -m pip install ./utilities/plasmactl     # standalone: programming + diagnosis
scripts/plasmactl help                           # checkout: also deployment profiles
```

## Commands

| Command | What it does | Writes |
|---|---|---|
| `diagnose --target PPU:S[,S] … \| --all` | Manager Fleet / PPU / Site observation | none |
| `program submit --target … --icpn … (--image \| --bundle \| --operations erase --address --length) --journal NEW` | one Manager start ID + exactly one Batch; observes to the end unless `--no-wait` | one `POST /api/programming/starts`, one `POST /api/programming/batches` |
| `program status --batch-id ID [--wait]` | Manager Batch record, per-Site progress | none |
| `program receipt --batch-id ID [--target …]` | PASS only for a finished, journal-persisted Batch with every Site PASS | none |
| `program reconcile --journal F \| --start-id ID` | Start Outcome Reconciliation (`GET /api/programming/starts/{id}`) | none |
| `program stop --batch-id ID` | existing `STOP_QUEUING`; running Jobs finish, nothing is cancelled | one stop POST |
| `deploy status --ppu A [--ppu B]` | Manager Bootstrap pairing/deployment/runtime state | none |
| `install\|deploy\|verify\|status\|logs\|restart PROFILE` | existing backend of `integration`, `local-control-station`, `swpc-z2like`, `z2-ps` | backend-owned |
| `update\|test\|web-restart\|start\|stop\|ports\|update-and-restart` | integration-host maintenance | backend-owned |
| `bootstrap-sites swpc-z2like`, `hil programming …` | retained engineering backends | backend-owned |

`logs` exists for `integration`, `local-control-station` and `z2-ps`;
`restart` for `integration` and `local-control-station`. `restart z2-ps` is
deliberately absent: the Deployment Coordinator owns quiescence and Root Guard.

Output is one JSON object on stdout (progress lines on stderr); errors are JSON
on stderr. Exit codes are the same for every command:

| Code | Meaning |
|---|---|
| 0 | PASS (Manager-reported), accepted, or observed |
| 1 | FAIL, PARTIAL, BLOCKED, NOT_VERIFIED, or backend failure |
| 2 | invalid input / contract error — nothing was submitted |
| 3 | `OUTCOME_UNKNOWN` — reconcile read-only, **never resend** |
| 4 | refused by the Manager, or the start provably never admitted |
| 5 | still in progress (wait ended; the Batch keeps running) |

## Programming safety

* The submission journal is created exclusively **before** any POST; an
  existing journal refuses a second submission. A lost Batch answer is
  reconciled by its start ID; a still-admissible start is voided (the Manager
  serializes void vs. admission) and reported `NOT_ACCEPTED`; anything
  unprovable stays `OUTCOME_UNKNOWN`. Nothing is ever resent automatically.
* One Site's FAIL or `OUTCOME_UNKNOWN` never makes the CLI stop, retry or
  resend anything; per-Site isolation and retry eligibility are the Manager's.
* The journal guards one workspace. A dispatcher that can re-run a job in a
  fresh workspace must keep its own replay guard (Work Order admission); the
  Manager start ID only makes each admitted start single-use.
* A PASS is the Manager-persisted Batch outcome, not an independent electrical
  or HIL qualification. Host-only tests use a fake Manager.

## Legacy entry points (Gate 1, 2026-11-18)

| Former entry | Status | Now |
|---|---|---|
| `scripts/plasmactl` Bash profile router (310 LOC) | MIGRATE | `plasma_cli/operations.py`; launcher kept (Z2 kit, installed symlink, Path 2 `CONTROL_STATION_OPERATOR_COMMANDS`) |
| `plasmactl test receipt` | MIGRATE | `plasmactl program receipt` (single name) |
| `scripts/plasma_programming_load.py`, `specs/programming-loading-benchmark-v1.schema.json`, Path 2 `p2hw-*` claim | DELETE | `plasmactl program` + `scripts/plasma_hil_timing.py` |
| `scripts/plasma_program.py` | RETAIN | single-PPU Bundle commissioning (B1/B2/B3, Runtime Kit, one-Site diagnostic flash); not the formal programming entry; uses neutral `ppu_bootstrap_transport.py` |
| `scripts/plasmactl-*` backends | RETAIN | platform-owned operations behind the CLI |
| `scripts/plasma_engineering_hil.py` (`hil programming`) | RETAIN | Blue Pill A/B + USB CDC verification harness (unique CDC check) |
| `software/python/plasma_client/cli.py` (`plasma`) | RETAIN | PPU-local Gateway debug client; not a Controller CLI |
| `scripts/plasma_ppu.py` | RETAIN | read-only SWPC→PPU deployment doctor (direct PPU observation, no Manager) |
