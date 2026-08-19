# Plasma Manager Read-only Fleet Aggregation

## Scope

The implemented Plasma Manager is an **optional, read-only fleet control plane**. It inventories configured PPU REST Gateway endpoints and aggregates their health, canonical identity, and Site topology. It does not participate in local job execution.

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

The current release uses explicit configuration rather than discovery or mandatory registration:

```yaml
manager:
  host: 127.0.0.1
  port: 18180
  request_timeout_s: 2.0
  poll_interval_s: 2.0

ppus:
  - alias: ppu-a
    endpoint: http://ppu-a.example.invalid:18080
  - alias: ppu-b
    endpoint: http://ppu-b.example.invalid:18080
```

`poll_interval_s` controls the background fleet observation cadence and defaults to 2 seconds. It is intentionally independent of client request frequency so multiple Fleet UI/API readers do not multiply outbound PPU traffic.

The endpoint identifies the root of one autonomous PPU's Plasma Web REST Gateway. `alias` is operator-facing registry metadata only; canonical `ppu_id`, `facility_id`, model, capabilities, and Site counts come from the PPU itself.

Manager configuration rejects duplicate endpoints, embedded URL credentials, query strings, fragments, nested endpoint paths, and invalid polling intervals. Authentication and secret distribution are intentionally not introduced by this phase.

For deployment, the Manager registry/configuration is operator-local state and should live outside the Git worktree, for example under `$XDG_CONFIG_HOME/plasma/manager.yaml`. Repository `software/python/config/manager.example.yaml` remains example/test material.

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

Returns the **last completed fleet snapshot from Manager memory**. The HTTP request itself does not contact any PPU.

A dedicated background poller refreshes that snapshot at `manager.poll_interval_s` by querying each configured PPU independently through the northbound contract established by the Plasma Web REST Gateway:

```text
GET /api/health/live
GET /api/health/ready
GET /api/node
GET /api/status
```

This changes the scaling model from request-driven fan-out:

```text
N fleet readers x M PPUs -> N x M observation fan-out
```

to Manager-owned observation:

```text
1 Manager poller x M PPUs -> observation state -> cached snapshot -> N fleet readers
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

Existing summary fields remain **current-observation fields**: configured, reachable, ready, identified, reported Site count, enabled Site count, and identity conflicts. Facility summaries also use only the current trusted topology. Stale last-known topology is not silently counted as currently available capacity. Heterogeneous **2-Site**, **4-Site**, and **8-Site** PPUs remain supported in the same fleet.

The observation layer adds:

```text
known_ppus
stale_ppus
unknown_ppus
```

where `known_ppus` means the Manager has completed at least one trusted observation for that configured endpoint during the current Manager process lifetime.

## Current transport and execution state

Each PPU entry exposes explicit current-state fields in addition to the legacy booleans:

```json
{
  "gateway_live": true,
  "execution_ready": true,
  "transport_state": "reachable",
  "execution_state": "ready"
}
```

`transport_state` is one of:

```text
reachable
unreachable
unknown
```

A transport exception while contacting the liveness endpoint is `unreachable`. Receiving an HTTP response that fails the fleet contract is not called a network outage; the transport is `reachable` while the contract error remains in `errors`.

`execution_state` is one of:

```text
ready
unavailable
unknown
```

A Gateway may therefore be reachable while local PPU execution is unavailable. This prevents Fleet UI or operations code from collapsing network health, Gateway health, and execution readiness into one boolean.

## Last-known observation semantics

The Manager keeps the last trusted canonical PPU/Site observation for each configured endpoint **in memory**. A trusted observation requires a live Gateway, ready local execution, compatible fleet contract, no identity conflict, valid canonical PPU identity/Site topology, and no per-PPU errors.

Each PPU entry contains:

```json
{
  "observation": {
    "state": "current",
    "stale": false,
    "last_success_at": "2026-08-19T05:56:26.243307+00:00",
    "stale_age_s": 0.0
  },
  "last_known": {
    "observed_at": "2026-08-19T05:56:26.243307+00:00",
    "ppu": {
      "ppu_id": "z2-dev-01",
      "facility_id": "swpc-lab",
      "site_count": 8
    },
    "sites": []
  }
}
```

`observation.state` has three meanings:

```text
current  -> this poll completed a trusted canonical observation
stale    -> this poll is not trusted/current, but a prior trusted observation exists
unknown  -> no trusted observation has ever completed for this endpoint in this Manager lifetime
```

For `current`, `stale=false` and `stale_age_s=0.0`. For `stale`, `last_success_at` remains the prior trusted timestamp and `stale_age_s` measures from that timestamp to the current fleet observation. For `unknown`, there is no fabricated history: `last_success_at`, `stale_age_s`, and `last_known` are null.

When a previously healthy PPU becomes unreachable, the current fields remain truthful:

```text
ppu = null
sites = []
transport_state = unreachable
execution_state = unknown
```

while `last_known` retains the prior identity and Site topology and `observation.state=stale`. This deliberately separates **what is true now** from **what was last known to be true**.

Likewise, if the Gateway remains reachable but the local Plasma Server becomes unavailable:

```text
transport_state = reachable
execution_state = unavailable
observation.state = stale   # when prior trusted topology exists
```

A duplicate current `ppu_id` conflict is never promoted into last-known trusted state. Previously trusted identities remain available as stale observations rather than being overwritten by the conflicted result.

The additions are backward-compatible fields under Manager contract version `1`; existing current booleans and current topology fields retain their existing meanings.

## Background polling and cache lifecycle

At Manager startup, the poller performs one bounded initial fleet refresh before the HTTP serving loop begins. PPU-specific outages are contained by the aggregator, so an unreachable PPU does not prevent Manager startup. After the initial snapshot is published, a single daemon polling thread refreshes it periodically.

Snapshot publication is atomic from the HTTP reader's perspective: readers either see the prior completed snapshot or the new completed snapshot, never a partially assembled fleet result. HTTP reads receive a copy of the cached snapshot and cannot mutate the poller's stored state.

Each cached fleet response also includes cache metadata:

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

`cache.age_s` is the age of the last completed Manager-level snapshot. It is different from per-PPU `observation.stale_age_s`, which measures how long a particular endpoint has lacked a trusted canonical observation.

If an unexpected Manager-level refresh exception occurs, the poller keeps the last completed cached snapshot and exposes the exception through `last_refresh_error`; the next interval attempts recovery. Normal per-PPU transport/readiness failures are represented inside a newly completed degraded fleet snapshot and do not count as Manager-level refresh exceptions.

The background poller is stopped during normal Manager shutdown. It never calls local `SiteManager`/`SiteWorker` APIs and does not create a dependency from PPU execution back to Manager.

## Failure containment

```text
One PPU offline
    -> current transport/execution state becomes degraded
    -> prior trusted identity/topology remains explicit as stale last_known data
    -> current capacity summaries do not count stale topology
    -> other PPU polling and aggregation continue

One PPU local Plasma Server unavailable
    -> Gateway may remain reachable
    -> execution_state = unavailable
    -> prior trusted topology may remain stale
    -> other PPUs remain independent

One unexpected Manager refresh failure
    -> last completed cached snapshot remains readable
    -> cache.last_refresh_error records the failure
    -> next background interval retries

Plasma Manager unavailable
    -> fleet aggregation unavailable
    -> all healthy PPUs continue local execution
```

The Manager therefore does not become an execution single point of failure.

## Deliberate persistence boundary

Last-known observation state in this phase is **process-memory state, not durable inventory history**. Restarting Plasma Manager clears `last_known`, `last_success_at`, and stale history; each configured endpoint begins as `current` after a successful new observation or `unknown` if the first new observation fails.

This boundary is intentional. Durable storage introduces lifecycle, schema migration, corruption/recovery, backup, retention, and operator-ownership questions. SQLite or another persistence layer should be introduced only as an explicit persistence phase rather than hidden inside the observation-state change.

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
- a Fleet Web UI;
- durable per-PPU observation persistence.

Those capabilities must be added incrementally above the autonomous PPU boundary. In particular, future command routing must call an existing PPU REST contract rather than bypassing the PPU and invoking internal `SiteManager`/`SiteWorker` APIs directly.

## Development and deployment entry points

For foreground development/testing:

```bash
plasma-manager --config config/manager.example.yaml
```

For a managed integration-host service, place the real registry outside the repository, set `PLASMA_MANAGER_ENABLED=1` and `PLASMA_MANAGER_CONFIG=<absolute path>` in the operator-local `plasmactl.env`, then use the normal `plasmactl` reconciliation/start/restart flow. Actual activation or restart of a shared Manager remains an explicit deployment approval gate.
