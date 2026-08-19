# Plasma Manager Read-only Fleet Aggregation

## Scope

The first implemented Plasma Manager is an **optional, read-only fleet control plane**. It inventories configured PPU REST Gateway endpoints and aggregates their health, canonical identity, and Site topology. It does not participate in local job execution.

The architectural dependency remains one-way:

```text
Plasma Manager -> PPU
```

A PPU continues to start, expose its local Plasma Web REST Gateway and Plasma PPU Console, execute Site jobs, recover, and perform maintenance without a Manager connection.

## Runtime shape

```text
Fleet client
    |
    v
Plasma Manager
    |
    +--> PPU A Plasma Web REST Gateway -> local Plasma Server -> Sites
    |
    +--> PPU B Plasma Web REST Gateway -> local Plasma Server -> Sites
    |
    +--> PPU C Plasma Web REST Gateway -> local Plasma Server -> Sites
```

The Manager is a separate `plasma_manager` Python package and service. It is not part of `plasma_server` or `SiteManager`, so fleet concerns do not enter the deterministic local execution path.

## Manual registry

The first release uses explicit configuration rather than discovery or mandatory registration:

```yaml
manager:
  host: 127.0.0.1
  port: 18180
  request_timeout_s: 2.0

ppus:
  - alias: ppu-a
    endpoint: http://ppu-a.example.invalid:18080
  - alias: ppu-b
    endpoint: http://ppu-b.example.invalid:18080
```

The endpoint identifies the root of one autonomous PPU's Plasma Web REST Gateway. `alias` is operator-facing registry metadata only; canonical `ppu_id`, `facility_id`, model, capabilities, and Site counts come from the PPU itself.

Manager configuration rejects duplicate endpoints, embedded URL credentials, query strings, fragments, and nested endpoint paths. Authentication and secret distribution are intentionally not introduced by this phase.

For deployment, the Manager registry/configuration is operator-local state and should live outside the Git worktree, for example under `$XDG_CONFIG_HOME/plasma/manager.yaml`. Repository `config/manager.example.yaml` remains example/test material.

## Manager REST contract

### `GET /api/health/live`

Reports only the Manager process state. It does not contact any PPU.

```json
{
  "ok": true,
  "service": "plasma-manager",
  "contract_version": "1",
  "manager": "alive"
}
```

### `GET /api/registry`

Returns the configured read-only PPU endpoint registry without performing fleet polling.

### `GET /api/fleet`

Polls each configured PPU independently through the northbound contract established by the Plasma Web REST Gateway:

```text
GET /api/health/live
GET /api/health/ready
GET /api/node
GET /api/status
```

The Manager validates:

- PPU fleet contract version `1`;
- `node_role = ppu`;
- `manager_required = false`;
- canonical `ppu_id`, `facility_id`, model, and Site counts;
- agreement between readiness, `/api/node`, and `/api/status` identity;
- positive, unique one-based `site_id` values;
- duplicate `ppu_id` conflicts across registry endpoints.

The fleet response remains HTTP 200 when one PPU is offline. `ok=true` means the Manager successfully produced a fleet snapshot; `degraded=true` and per-PPU errors represent partial fleet health.

A summary reports configured, reachable, ready, and identified PPUs plus reported/enabled Site counts. Facility summaries group only trusted canonical PPU identities without hard-coding a uniform Site count, so 2-Site, 4-Site, and 8-Site PPUs may coexist. Duplicate identity conflicts are surfaced instead of being double-counted as trusted topology.

## Failure containment

```text
One PPU offline
    -> that registry entry is degraded
    -> other PPU polling and aggregation continue

One PPU local Plasma Server unavailable
    -> Gateway may remain live
    -> execution_ready is false for that PPU
    -> other PPUs remain independent

Plasma Manager unavailable
    -> fleet aggregation unavailable
    -> all healthy PPUs continue local execution
```

The Manager therefore does not become an execution single point of failure.

## Deployment baseline

`scripts/plasmactl` can generate and manage an optional user-level `plasma-manager.service`. Deployment is **opt-in**, not automatic:

```text
PLASMA_MANAGER_ENABLED=0   -> standalone PPU services only
PLASMA_MANAGER_ENABLED=1   -> add plasma-manager.service
```

The deployment schema keeps the Manager registry path separate from source code:

```text
PLASMA_MANAGER_CONFIG=/absolute/operator/local/path/manager.yaml
```

When Manager is enabled, `plasmactl` validates the Manager YAML before service restart, generates the unit, enables it, and checks the Manager's own `/api/health/live` endpoint. The Manager systemd unit depends only on `network-online.target`; it does **not** depend on the same host running `plasma-web.service`. This preserves the option to place Manager on a dedicated control-plane host later.

When Manager remains disabled, normal `plasmactl deploy/start/restart` does not start it. If an old Manager process is still active while configuration says disabled, reconciliation stops it so runtime state matches the explicit opt-in setting.

## Read-only boundary

This release intentionally rejects Manager POST/PUT/PATCH/DELETE requests. It does not implement:

- job routing or fleet command proxying;
- central scheduling;
- mandatory PPU registration or Manager heartbeat;
- mDNS/automatic discovery;
- authentication/authorization policy;
- central audit persistence;
- firmware catalog or rollout;
- a Fleet Web UI.

Those capabilities must be added incrementally above the autonomous PPU boundary. In particular, future command routing must call an existing PPU REST contract rather than bypassing the PPU and invoking internal `SiteManager`/`SiteWorker` APIs directly.

## Development and deployment entry points

For foreground development/testing:

```bash
plasma-manager --config config/manager.example.yaml
```

For a managed integration-host service, place the real registry outside the repository, set `PLASMA_MANAGER_ENABLED=1` and `PLASMA_MANAGER_CONFIG=<absolute path>` in the operator-local `plasmactl.env`, then use the normal `plasmactl` reconciliation/start/restart flow. Actual activation or restart of a shared Manager remains an explicit deployment approval gate.
