# PLASMA — Manager / Backend Engineering Contract

> Domain-specific contract. Read with [AGENTS.md](../../AGENTS.md) and [Common](plasma-development-common.md) for Plasma Manager, Controller, Gateway routing and REST backend.

## Scope
- Plasma Manager, Gateway/Controller/BFF, REST APIs, backend routing, deployment coordination and related service behavior.
- SWPC hosts Web/Controller/BFF; PPU/Z2 PS hosts the embedded programming runtime. Do not move live OpenOCD to SWPC.
- Preserve canonical one-based Site identity, Protocol v3.3 and Web REST v3 unless an approved change replaces the contract and all dependents together.
- Manager is bounded managed PPU routing, not an assumed universal scheduler. Inspect actual endpoints, process ownership and ports before edits.
- Changes to PPU-facing API also load [Embedded](plasma-embedded.md); changes to Web-facing API also load [Web](plasma-web.md).
- Update callers, tests, fixtures and documentation in the same change under Replace-by-Default.

## Current software architecture

PPU-local path:

```text
Browser / Plasma PPU Console
        |
        | HTTP REST polling / Web REST v3
        v
Plasma Gateway
        |
        | Plasma Protocol v3.3 / PLASMA33
        v
Plasma Server :9900
        |
        v
SiteManager / SiteWorker
        |
        v
Interface / Handler
        |
        v
MockInterface today; Z2/FPGA/real-target validation is separate
```

Managed Control Station path:

```text
Browser
    |
    v
Control Station Console/BFF
    |
    v
Plasma Manager (registry / fleet observation / bounded managed PPU relay)
    |
    +--> PPU A Plasma Gateway -> local execution
    +--> PPU B Plasma Gateway -> local execution
    +--> ...
```

Implementation facts:

- Plasma Gateway uses Python standard-library `ThreadingHTTPServer`.
- It is **not FastAPI**.
- It does **not use WebSocket**.
- Web Console uses REST polling.
- `plasma_manager` is optional and not required for local PPU execution.
- Manager deployment is opt-in (`PLASMA_MANAGER_ENABLED=0` by default for the integration profile).
- Manager fleet observation is read-only, but Manager also owns explicit bounded control relays. The managed allowlist includes health/status/settings surfaces plus the current Job, Batch, Programming Asset, Engineering session/target, Site Desired/runtime-activation and network-commissioning routes required by the Control Station product.
- Managed routing is **not** a generic reverse proxy. Exact methods and paths are allowlisted in `software/python/plasma_manager/server.py`; Browser traffic reaches those routes through the same-origin BFF.
- Job/Batch execution remains PPU/Gateway-owned. Manager relays commands and observations to the selected PPU; it is not a central Job scheduler and does not replace the PPU execution engine.
- Site Desired reads/writes remain PPU-owned. Manager relays the allowlisted Site settings routes and the explicit `If-Match`/idempotency/security headers required by that contract.
- Manager still does not provide automatic PPU discovery, a general Fleet write API, or an independent central authentication/scheduling policy layer.
- Mock programming success does not prove hardware programming.

Do not introduce FastAPI/WebSocket merely because they were discussed as future options.

## Runtime services and ports

Service management is defined by `scripts/plasmactl`. Port numbers are profile-specific defaults; use `docs/deployment/port-profile-matrix.md` as the canonical cross-profile map rather than assuming one Manager port applies to every deployment.

| systemd service | Default port | Canonical role |
|---|---:|---|
| `plasma-server.service` | 9900 | Plasma PPU Programming Server / Protocol v3.3 TCP Server |
| `plasma-web.service` | 18080 | Full Plasma Gateway |
| `plasma-vite.service` | 5173 | Plasma PPU Console development/demo runtime |
| `plasma-manager.service` | 18180 | Generic/integration/package Manager default; registry, fleet observation, and bounded managed PPU relay |

The Linux `local-control-station` profile intentionally uses Console/BFF `127.0.0.1:18190` and Manager `127.0.0.1:18280`. The SWPC x86 `swpc-z2like` engineering surrogate owns only its full local Gateway on `127.0.0.1:18080`; its former host `18081` diagnostics/status ingress was retired by Issue #549 and must remain unused. Public `z2like-demo` uses SWPC host `18082` as its Cloudflare-Access-protected managed ingress to the private QEMU backend. Inside QEMU and on a real Z2, `:18081` remains the independent Bootstrap/recovery service. These are profile contracts, not accidental drift.

Packaged PPU deployments must bind `plasma-server.service` and `plasma-web.service` to the same explicit canonical PPU configuration path. Site Desired persistence requires directory-level create/rename permission for atomic replacement; grant that write boundary only to the Plasma Gateway service and only for the managed Plasma configuration root. `plasma-server.service` remains read-only for canonical configuration. A successful Save Desired changes persistent desired state only; runtime activation is a separate explicit operation.

Useful commands:

```bash
plasmactl status
plasmactl ports
plasmactl test
plasmactl restart
plasmactl logs
plasmactl deploy
```

`plasmactl test` is the preferred full integration-host validation for cross-stack changes.

Normal deployment flow:

```text
GitHub main
   -> fast-forward update
   -> re-exec latest plasmactl
   -> full relevant validation
   -> regenerate/reconcile systemd units
   -> restart configured services
   -> health check
```

Do not bypass failed tests and restart new code as if validation succeeded.

## Site execution invariants

The PPU Runtime owns Flash outcome policy, `JobRequest.max_retries`,
`attempt_history`, `retry_backoff_s`, and any decision to mark a Job failed
or block a Site after exhausted retries. Each attempt creates a fresh hardware
session. Plasma Manager only relays and observes PPU Jobs; PPU HTTP retry is
separate from Flash retry.

Unless a real shared resource requires synchronization:

- Sites execute independently.
- A Site must not wait for an unrelated Site pipeline.
- Per-Site cancellation must not cancel unrelated Sites.
- Batch cancellation is authoritative for batch classification when it races terminal Job success; the underlying final Job result remains truthful.
- `program` means write only.
- A complete programming flow is composed explicitly, e.g. `erase -> program -> verify`.
- Batch operation selection may include any subset of Erase / Program / Verify / Read.

For Program/Verify, a PPU-wide Normalized Image lease may synchronize Sites because one physical PPU must not execute different target Images concurrently when they share programming resources.

## Python environment and domain rules

Python project:

```text
software/python/
```

`pyproject.toml` is authoritative. Baseline is Python >= 3.11.

Preferred test command:

```bash
cd software/python
.venv/bin/python -m pytest -q
```

Canonical Python/domain vocabulary includes:

```text
PPUConfig
SiteConfig
SiteManager
SiteWorker
SiteState
ppu_id
facility_id
site_id
ProgrammingAsset
ProgrammingAssetType
ProgrammingAssetFormat
NormalizedImage
JobRequest.image
image_size
image_sha256
```

Retired Programmer/Channel domain vocabulary and old programming-data vocabulary must not appear in canonical production code. Do not create compatibility aliases unless an explicit new architecture decision reintroduces a real compatibility requirement.

## Manager and backend architecture boundaries

These facts must not be mistaken for implemented capabilities:

1. Python supports >=3.11; CI and integration host may use different allowed minor versions.
2. Integration deployment uses Plasma Gateway port 18080 while `plasma_web.gateway` retains a code-level local default of 8080.
3. Plasma Gateway is standard-library HTTP + REST polling, not FastAPI/WebSocket.
6. Only binary Image Asset normalization is implemented; other declared Asset formats/types are extension points, not validated functionality.
7. Programming Recipe/Package is an architectural direction, not yet an implemented execution contract.
8. Plasma Manager currently implements explicit registry/fleet aggregation plus bounded managed PPU command routing for the current Control Station contract, including allowlisted Job/Batch/Programming Asset and Site/network operations. It is not a generic proxy or central scheduler; automatic discovery, general Fleet write orchestration, and an independent central auth/scheduling policy remain outside the current contract.
10. Site Desired persistence and Runtime activation are separate contracts. Current P3-capable deployments support explicit bounded runtime activation through the activation helper/server-control sockets; saving Desired state alone never implies that runtime activation occurred.

Web-specific boundaries are owned by [plasma-web.md](plasma-web.md); hardware validation limits by [plasma-embedded.md](plasma-embedded.md). Global validation evidence requirements remain in [AGENTS.md](../../AGENTS.md).

## Python validation commands

```bash
cd software/python
.venv/bin/python -m pytest -q
```

## Programming operations (one Job, `operations` list)

Erase / Program / Verify run as ONE `programming` Job with an ordered `operations` list (one Job ID, lease, Job Binding and receipt); `read` is an independent Job; `flash_cycle` is the unchanged legacy contract. Normative detail: [OPF Programming Operations v1](../architecture/opf-programming-operations-v1.md). Host-only tests are not a hardware qualification of any operation.

EMode Batch Retry / Stop Policy is Manager-owned (`programming_batch.py`): [EMode Batch Retry / Stop Policy v1](../architecture/emode-batch-retry-stop-policy-v1.md). Repeat is not implemented.

A Start whose HTTP answer was lost is reconciled against the Manager journal by its Manager-issued `start_id` (read-only `GET programming/starts/{start_id}`): [Programming Start Outcome Reconciliation v1](../architecture/programming-start-reconciliation-v1.md).
