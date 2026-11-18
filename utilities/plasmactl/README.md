# PLASMA Unified CLI — first read-only diagnostic slice

Source of the portable CLI utility: this directory only. The existing
`scripts/plasmactl` profile router and `plasma_client.cli` remain unchanged
until the complete migration is proven. They are **not** replacement implementations
of PPU programming, provisioning or privileged recovery.

## Install on an engineering host or a future Controller

```bash
python3 -m pip install ./utilities/plasmactl
plasmactl diagnose --manager-url http://127.0.0.1:18280 --target z2:1,2
plasmactl diagnose --manager-url https://manager.example.org --target ppu-a:1,3 --target ppu-b:2
plasmactl diagnose --all
plasmactl test receipt --batch-id 0123456789abcdef0123456789abcdef --target z2:1,2
```

The Manager URL is configurable; localhost is only the SWPC Control Station
default. Run this as a **separate test environment** until the old `plasmactl`
router is retired. There is no requirement for a Git checkout at runtime.

Data is read exclusively through Manager's existing `GET /api/fleet`.
Site IDs are validated against live Fleet topology, never a hard-coded Site2
or eight-Site list. The diagnostic may report OBSERVED/NOT_VERIFIED, not
a physical programming or electrical PASS. Invalid or missing Targets
fail closed. It performs no POST, hardware operations, deployment or DUT I/O.

## Migration boundary

Future phases must move the legacy `diagnose/deploy/test` command semantics
into this one utility and migrate **all** callers/tests/CI before retiring
`scripts/plasmactl`. Deploy and programming operations must use existing
Manager/PPU APIs, Owner authorization, durable receipts and local safety
guards. Never implement a second Batch scheduler or programming engine.

Current scope: read-only `diagnose` and `test receipt` only. `test receipt` reads
Manager's canonical `GET /api/programming/batches/{batch_id}` and checks the
Target-Set/Unit identity. It reports the **Manager-reported whole-Batch PASS**,
not an independent hardware or electrical qualification. It never issues Start,
POST or retries. `deploy` and execution-oriented `test programming` are
**NOT IMPLEMENTED**.
Do not install this candidate on the live SWPC or Controller yet.
