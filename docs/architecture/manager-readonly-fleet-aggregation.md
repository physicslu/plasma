# Plasma Manager Read-only Fleet Aggregation

## Scope

Plasma Manager is an **optional, read-only fleet control plane**. It inventories configured PPU Plasma Gateway Endpoints and aggregates current health, canonical PPU identity, Site topology, and explicit last-known observation state. It does not participate in local job execution.

The architectural dependency remains one-way:

```text
Plasma Manager -> PPU
```

A PPU continues to start, expose its local Plasma Gateway and Plasma PPU Console, execute Site jobs, recover, and perform maintenance without a Manager connection. The fleet-facing PPU contract continues to require `manager_required = false`.

Heterogeneous **2-Site**, **4-Site**, and **8-Site** PPUs may coexist in the same fleet. Manager never assumes a uniform Site count.

## Runtime shape

```text
Fleet client
    |
    v
Plasma Manager
    |
    +--> PPU A Plasma Gateway -> local Plasma Server -> Sites
    +--> PPU B Plasma Gateway -> local Plasma Server -> Sites
    +--> PPU C Plasma Gateway -> local Plasma Server -> Sites
```

The Manager is a separate `plasma_manager` Python package and service. It is not part of `plasma_server` or `SiteManager`, so fleet concerns do not enter the deterministic local execution path.

## Manual registry and Manager configuration

The current release uses explicit configuration rather than discovery or mandatory registration:

```yaml
manager:
  host: 127.0.0.1
  port: 18180
  request_timeout_s: 2.0
  poll_interval_s: 2.0
  # Optional; choose a writable operator-local absolute path.
  # observation_db_path: /absolute/operator/local/path/manager-observations.sqlite3

ppus:
  - alias: ppu-a
    endpoint: http://ppu-a.example.invalid:18080
  - alias: ppu-b
    endpoint: http://ppu-b.example.invalid:18080
```

`poll_interval_s` controls background fleet observation cadence and defaults to 2 seconds. Client request frequency does not multiply outbound PPU polling.

`observation_db_path` is optional. When omitted, last-known history remains process memory and is lost on Manager restart. When present, it must be a writable absolute operator-local filesystem path and enables SQLite persistence of the latest trusted observation per configured endpoint.

The endpoint identifies the root of one autonomous PPU's **Plasma Gateway Endpoint**. `alias` is operator-facing registry metadata only; canonical `ppu_id`, `facility_id`, model, capabilities, and Site counts come from the PPU itself.

Manager configuration rejects duplicate endpoints, embedded URL credentials, query strings, fragments, nested endpoint paths, invalid polling intervals, and relative observation database paths. The observation database is operational state, not a source-controlled artifact and not a credential store.

For deployment, the real Manager config belongs outside the Git worktree, for example under `$XDG_CONFIG_HOME/plasma/manager.yaml`. Repository `software/python/config/manager.example.yaml` remains example/test material.

## Manager REST contract

### `GET /api/health/live`

Reports only the Manager process state. It does not contact any PPU.

### `GET /api/registry`

Returns the configured read-only PPU endpoint registry without performing fleet polling.

### `GET /api/fleet`

Returns the last completed fleet snapshot from Manager memory. The HTTP request itself does not contact any PPU.

A dedicated background poller refreshes the snapshot by querying each configured PPU through the Plasma Gateway API:

```text
GET /api/health/live
GET /api/health/ready
GET /api/node
GET /api/status
```

Scaling remains:

```text
1 Manager poller x M PPUs -> observation state -> cached snapshot -> N fleet readers
```

rather than request-driven `N x M` fan-out.

The Manager validates fleet contract version `1`, `node_role = ppu`, `manager_required = false`, canonical PPU/Site identity, agreement between readiness/node/status identity, positive unique one-based `site_id` values, and duplicate `ppu_id` conflicts across registry endpoints.

The fleet response remains HTTP 200 when one PPU is offline. `ok=true` means Manager successfully produced a fleet snapshot. `degraded=true` and per-PPU errors describe partial fleet health.

Existing current-capacity summaries stay current-only: configured, reachable, ready and identified PPU counts, reported/enabled Site counts, identity conflicts, and Facility summaries never count stale topology as currently usable capacity.

## Transport, execution, and observation state

Each PPU entry separates current transport from current local execution:

```json
{
  "transport_state": "reachable",
  "execution_state": "ready",
  "gateway_live": true,
  "execution_ready": true
}
```

`gateway_live` is an existing API field name retained for compatibility; semantically it reports Plasma Gateway liveness.

`transport_state` is `reachable`, `unreachable`, or `unknown`. An HTTP response that violates the fleet contract is still transport-reachable; contract failure is not mislabeled as a network outage.

`execution_state` is `ready`, `unavailable`, or `unknown`. A reachable Plasma Gateway may therefore report unavailable local execution.

The observation model remains:

```text
current  -> this poll completed a trusted canonical observation
stale    -> current poll is not trusted/current, but last-known trusted history exists
unknown  -> no trusted last-known observation is available
```

A trusted observation requires a live Plasma Gateway, ready local execution, compatible fleet contract, no identity conflict, valid canonical PPU/Site topology, and no per-PPU errors.

Each PPU entry exposes:

```json
{
  "observation": {
    "state": "stale",
    "stale": true,
    "last_success_at": "2026-08-19T06:20:37.763570+00:00",
    "stale_age_s": 12.5
  },
  "last_known": {
    "observed_at": "2026-08-19T06:20:37.763570+00:00",
    "ppu": {
      "ppu_id": "z2-dev-01",
      "facility_id": "swpc-lab",
      "site_count": 8
    },
    "sites": []
  }
}
```

For `current`, `stale=false` and `stale_age_s=0.0`. For `stale`, `last_success_at` remains the prior trusted timestamp. For `unknown`, `last_success_at`, `stale_age_s`, and `last_known` are null.

A transient outage therefore remains explicit:

```text
current truth:
    ppu = null
    sites = []
    transport/execution describe what is observable now

historical truth:
    last_known contains the prior trusted topology
    observation.state = stale
```

The summary fields `known_ppus`, `stale_ppus`, and `unknown_ppus` describe observation knowledge. With durable persistence enabled, `known_ppus` may include history restored from the observation database after Manager restart.

## Durable last-known observation persistence

Durable persistence is intentionally narrow. SQLite stores **one latest trusted observation per configured PPU Plasma Gateway Endpoint**:

```text
endpoint -> observed_at + canonical PPU object + canonical Sites
```

It does not store a time series, job history, audit trail, credentials, Programming Image state, scheduling state, or authoritative execution state. The PPU remains the source of truth whenever a new trusted observation succeeds.

The database uses SQLite `PRAGMA user_version = 1`. Manager creates schema v1 only when the configured database is genuinely empty. It refuses to claim or mutate an unknown unversioned database that already contains user tables. Unsupported future schema versions or a v1 database missing its required table are rejected by the persistence layer.

### Retention policy

The retention model is deliberately bounded:

```text
one last-known record per currently configured endpoint
```

When an endpoint is removed from the Manager registry, its durable last-known record is removed on the next successful observation-store write. There is no historical timeline and no age-based retention policy in this phase.

Endpoint is the persistence key. If an operator deliberately reuses the same Plasma Gateway Endpoint for different hardware, prior data may appear as **stale last-known** until a new trusted observation replaces it. It is never counted as current capacity.

### Recovery and failure policy

Persistence is an availability aid, not an execution dependency.

```text
SQLite healthy
    -> load last-known records at Manager startup
    -> successful trusted observations replace durable records

SQLite write failure after a successful load
    -> current fleet snapshot still succeeds
    -> observation_store.healthy = false
    -> next background observation retries the write

SQLite load/schema/corruption failure
    -> current Manager process continues memory-only
    -> database is quarantined read-only for that process
    -> Manager does not overwrite the suspect database
    -> operator repairs/replaces it and restarts Manager

Plasma Manager unavailable
    -> fleet aggregation unavailable
    -> healthy PPUs continue local execution
```

This avoids turning a cache-storage problem into a programming outage and avoids destructive "self-healing" that could erase evidence from a corrupt or misconfigured database.

Each fleet snapshot exposes observation-store health without exposing the host filesystem path:

```json
{
  "observation_store": {
    "mode": "sqlite",
    "healthy": true,
    "writable": true,
    "last_error": null
  }
}
```

Memory-only mode reports `mode=memory`; `writable=false` means no durable backend is configured, not that fleet aggregation is unhealthy.

## Background polling and cache lifecycle

At Manager startup, the observation store loads durable last-known records when configured, then the poller performs one bounded initial fleet refresh before the HTTP serving loop begins. PPU-specific outages remain contained by the aggregator.

Snapshot publication remains atomic from the HTTP reader's perspective. Readers see either the previous completed snapshot or the next completed snapshot, never a partially assembled fleet result. HTTP reads receive a copy of the cached snapshot and cannot mutate stored state.

Manager-level cache metadata remains separate from per-PPU stale age and observation-store persistence health:

```json
{
  "cache": {
    "mode": "background",
    "poll_interval_s": 2.0,
    "age_s": 0.314,
    "last_refresh_error": null
  }
}
```

`cache.age_s` describes the last completed Manager-level snapshot. `observation.stale_age_s` describes how long one endpoint has lacked a trusted observation. `observation_store` describes persistence backend health.

## Deployment baseline

`scripts/plasmactl` manages an optional user-level `plasma-manager.service`. Manager remains opt-in:

```text
PLASMA_MANAGER_ENABLED=0   -> standalone PPU services only
PLASMA_MANAGER_ENABLED=1   -> add plasma-manager.service
```

The operator-local Manager config remains selected by:

```text
PLASMA_MANAGER_CONFIG=/absolute/operator/local/path/manager.yaml
```

Adding or changing `observation_db_path` is an operator runtime/configuration change and must follow the normal deployment approval gate. No new `plasmactl` persistent schema version is required because the field belongs to the Manager YAML, not `plasmactl.env`.

The Manager systemd unit depends on network availability only; it does not make local PPU execution depend on Manager or on SQLite.

## Read-only boundary

This release still rejects Manager POST/PUT/PATCH/DELETE fleet commands. It does not implement job routing, central scheduling, mandatory registration, mDNS discovery, authentication/authorization policy, central audit persistence, or Programming Image rollout. PMode provides a Factory Console, but Manager remains an observation-only provider rather than its command scheduler.

Durable observation persistence must not be confused with those control-plane responsibilities. Future command routing must use an existing Plasma Gateway API contract rather than bypassing the PPU and invoking internal `SiteManager`/`SiteWorker` APIs directly.

## Development and deployment entry points

Foreground development/testing:

```bash
plasma-manager --config config/manager.example.yaml
```

For managed deployment, place the real registry and optional observation database outside the repository, set `PLASMA_MANAGER_ENABLED=1` and `PLASMA_MANAGER_CONFIG=<absolute path>` in operator-local configuration, then use the normal `plasmactl` reconciliation flow. Activating or restarting shared runtime remains an explicit deployment approval gate.
