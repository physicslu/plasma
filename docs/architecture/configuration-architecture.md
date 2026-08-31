# Plasma Configuration Architecture

> Status: current baseline for standalone integration-host deployment, managed Control Station routing, optional Plasma Manager, Engineering Mock Provider, and shared Gateway communication policy.

This document defines ownership, source-of-truth, precedence, persistence, migration, and reconciliation rules for Plasma configuration. It intentionally avoids private account names, private hostnames, and workstation-specific absolute paths.

## 1. First principles

Configuration describes intended or persistent behavior. Runtime state describes what the system is doing now. These are separate domains and must not be collapsed merely because both can be serialized.

Every permanent configuration value needs explicit answers for:

1. **Owner** — which subsystem is responsible?
2. **Source of Truth** — where is the authoritative value stored or produced?
3. **Precedence** — which candidate wins when multiple values exist?
4. **Lifecycle** — when is it created, changed, applied, and retired?
5. **Version/Migration** — how does persisted old state move to a new schema?

Generated systemd units, environment blocks, browser bootstrap values, derived response budgets, and other derived configuration are not independent sources of truth. They must be reproducible from authoritative input.

A second first-principle invariant applies to Browser routing:

> The Browser owns user interaction, not deployment topology.

A formal Control Station therefore routes:

```text
Browser
  -> same-origin Console/BFF
  -> Plasma Manager
  -> selected PPU
```

A standalone integration host routes:

```text
Browser
  -> same-origin Web endpoint
  -> local Vite proxy
  -> local Plasma Web REST Gateway
  -> local PPU / Engineering Mock Provider
```

Neither topology requires a hard-coded remote Gateway URL in Browser source code.

## 2. Canonical domain

Configuration follows the product/domain hierarchy:

```text
Facility -> PPU -> Site
```

Canonical Site identity is one-based:

```text
SITE 1 .. SITE N
```

There is no canonical `SITE 0`.

The word **Facility** is used for a factory/lab/deployment location. **Site** is reserved for a Programming Site inside a PPU. Do not reuse `Site` to mean deployment location in new configuration.

## 3. Configuration domains

| Domain | Examples | Owner | Authoritative source |
|---|---|---|---|
| Product defaults | timeout, size limit | Source code | Checked-in code/config |
| Facility/deployment | service ports, repository path, Manager enablement | Deployment operator | Persistent deployment config |
| Browser routing mode | managed vs standalone | Runtime/deployment | Same-origin discovery plus generated service environment |
| PPU identity | PPU ID, model, serial identity, facility association | Device provisioning | Device-local persistent identity |
| PPU capability | Site count, supported operations/interfaces, FPGA/Image capability | PPU runtime/hardware | Device-reported capability |
| Gateway communication policy | PPU request timeout and retry count | Plasma Web REST Gateway | Persistent Gateway settings YAML |
| Derived communication budget | complete PPU observation response budget | Plasma Web REST Gateway | Derived from Gateway policy; not persisted |
| Site configuration | Site enablement, interface binding, per-Site limits | PPU configuration | Canonical PPU config |
| Target profile | IC family, memory geometry, interface | Target-definition layer | Checked-in target/profile data |
| Job configuration | operation, target, file, offset, read length | Job request/server | Accepted server-side job record |
| Runtime state | online, busy, progress, current job | Runtime services | Live state |
| User preference | theme, layout, visible Sites | Browser/user | Browser-local preference storage |
| Secrets/credentials | certificates, tokens, private keys | Security/deployment layer | Protected secret storage |

A browser may cache presentation preferences, but it must not become authoritative for PPU inventory, Site topology, Site capability, hardware capability, Gateway retry policy, Gateway response budget, Manager selection, or PPU endpoint URLs.

## 4. Deployment configuration

The integration host uses a persistent operator configuration file under the user's configuration directory:

```text
$HOME/.config/plasma/plasmactl.env
```

The current deployment schema version is:

```bash
PLASMA_CONFIG_VERSION=6
```

Generic example:

```bash
PLASMA_REPO=/path/to/plasma
PLASMA_BRANCH=main
PLASMA_NPM=/path/to/npm
PLASMA_UV=/path/to/uv
PLASMA_GATEWAY_HOST=0.0.0.0
PLASMA_GATEWAY_PORT=18080
PLASMA_CORS_ORIGIN='*'
PLASMA_VITE_HOST=127.0.0.1
PLASMA_VITE_PORT=5173
PLASMA_PUBLIC_API_URL=
PLASMA_MANAGER_ENABLED=0
PLASMA_MANAGER_CONFIG=/path/to/manager.yaml
PLASMA_MANAGER_PPU_ALIAS=
PLASMA_ENGINEERING_MOCK_ENABLED=0
PLASMA_ENGINEERING_MOCK_ROOT=/path/to/runtime-state/engineering-mock
```

`PLASMA_PUBLIC_API_URL` is retained only as a compatibility field in schema v6 and is empty by default. It is no longer the Browser's topology owner. New deployments use same-origin Browser routing.

`PLASMA_MANAGER_PPU_ALIAS` is the explicit PPU selected for the Manager BFF command path. It may remain empty when Manager is disabled. When Manager is enabled, it must identify an alias already present in `PLASMA_MANAGER_CONFIG`; deployment must not infer the first registry entry.

`PLASMA_MANAGER_API_URL`, `PLASMA_CONTROL_STATION_MODE`, and `PLASMA_FLEET_UI_ENABLED` are generated runtime environment, not independent persistent operator inputs. For Manager-enabled integration-host deployment, `plasmactl` derives the local Manager URL and emits managed-mode environment into `plasma-vite.service`.

Ownership chain:

```text
product/source default
       ↓ fallback only
persistent Facility/deployment configuration
       ↓ authoritative deployment value
validation / migration
       ↓
generated service environment
       ↓
active processes
```

Manual edits to generated units are not a supported long-term configuration mechanism.

## 5. Canonical PPU configuration

Current PPU configuration uses `ppu`, `server`, and one-based `sites`:

```yaml
ppu:
  id: ppu-01
  facility_id: lab-01
  model: PYNQ-Z2
  display_name: Plasma PPU Prototype

server:
  host: 127.0.0.1
  port: 9900
  max_supported_sites: 8
  max_concurrent_jobs: 2
  max_queue_depth_per_site: 16

sites:
  - {id: 1, enabled: true, interface: mock}
  - {id: 2, enabled: true, interface: mock}
```

`max_supported_sites` defines the valid one-based Site ID space `1..N`. `max_concurrent_jobs` limits how many jobs may actually execute concurrently. These are different constraints.

The current loader accepts canonical `ppu`, `server`, and `sites` fields only. Retired `programmer` / `channels` configuration and zero-based identity are rejected rather than silently translated.

## 6. Routing and precedence rules

There is no universal precedence chain for every setting. Precedence is domain-specific.

### Facility/deployment

```text
1. valid explicit persistent deployment configuration
2. product/source default
```

### Browser/user preference

```text
1. valid browser-local presentation preference
2. UI product default
```

### Browser API routing

Direct Browser ownership of a remote Gateway endpoint is retired.

Standalone integration-host mode uses the Browser's current origin. Local Vite routing proxies PPU-local API namespaces to the local Gateway, currently `127.0.0.1:18080` by default.

Managed Control Station mode uses the same-origin Manager/BFF namespace. The Browser does not receive or edit the selected PPU Gateway URL.

```text
standalone:
Browser -> same origin -> local proxy -> Gateway

managed:
Browser -> same origin -> Console/BFF -> Manager -> selected PPU
```

An old Browser-local absolute API Base is migration input only. It is not retained as current topology truth.

### PPU capability

```text
1. valid capability reported by the PPU/device
2. provisioned model default, when available
3. no browser override
```

### Job configuration

Once a job is accepted, the server-side job record is authoritative for that execution.

### Gateway communication policy

```text
1. persistent Gateway settings selected by --gateway-settings
2. <output-root>/gateway-settings.yaml
3. code defaults: 10-second PPU request timeout and 3 retries
```

The resource is edited through `EMode -> Settings -> Gateway` and shared by PMode and EMode. Each Batch freezes a policy revision at START; updates affect only future Batches.

The writable persistent fields are `ppu_request_timeout_ms` and `ppu_retry_count`; `revision` is server-owned. The complete observation budget `ppu_response_budget_ms` is calculated by the Gateway from configured attempts plus communication backoff. It is read-only, not persisted, and must not be treated as a third operator setting.

The Browser may derive an outer HTTP watchdog from `ppu_response_budget_ms` plus a transport margin. That watchdog is a client-side transport guard only. It must not become a second source of truth for PPU request timeout or retry count.

## 7. Schema versioning and migration

Configuration that survives a software upgrade requires an explicit schema/version strategy.

A migration must be deterministic, bounded, idempotent, fail closed on unsupported future schemas, and covered by regression tests. Operator-owned values may be intentionally retired only when a new schema explicitly changes ownership.

Migration flow:

```text
read schema version
    ↓
validate version
    ↓
run ordered migrations
    ↓
validate resulting model
    ↓
persist new schema
    ↓
reconcile derived runtime state
```

Schema v5 added `PLASMA_MANAGER_PPU_ALIAS`. Migration preserved an existing explicit value; otherwise it added an empty value. It did not infer a command target from Manager registry ordering.

Schema v6 retires Browser-owned direct Gateway endpoints. Migration deliberately clears `PLASMA_PUBLIC_API_URL`, including prior custom values, because those values represented an ownership model that no longer exists. The local Gateway and Engineering Mock Provider are not removed; they remain reachable through same-origin integration-host routing.

Browser storage has a parallel migration boundary. Browser API-base storage schema v3 clears previously stored absolute API endpoints so runtime routing can resolve to same-origin standalone or Manager-owned managed transport.

Wire-protocol evolution is separate from deployment-config schema versioning. Protocol v3.3 / `PLASMA33` uses one-based `site_id`; retired zero-based Channel identity is not a current migration input.

## 8. Runtime reconciliation

Deployment is reconciliation, not merely restart:

```text
GitHub main
    ↓
fast-forward update
    ↓
re-exec latest plasmactl
    ↓
config migration + validation
    ↓
relevant tests
    ↓
regenerate systemd units
    ↓
systemctl --user daemon-reload
    ↓
restart
    ↓
health check
```

Invariant:

> If persistent deployment configuration is valid, a normal `plasmactl restart` must be sufficient to regenerate derived service configuration and activate it.

Re-running `install` must not be required merely to make a normal configuration change take effect.

## 9. Browser storage boundary

Browser storage is suitable for user-local presentation state, for example:

```text
theme
visible-Site preference
layout preference
language preference
```

A legacy Browser API Base may appear only as migration input and must be cleared by the current storage migration.

The following must not become authoritative browser state:

```text
PPU inventory
PPU endpoint URLs
selected PPU routing truth
PPU Site count
Site enable/disable truth
PPU hardware interfaces/capability
Gateway timeout/retry policy
Gateway response budget
production routing policy
authentication secrets
job execution state
```

## 10. PPU identity and capability

Higher-level software must consume PPU identity/capability reported by the PPU side rather than inventing topology in the browser.

Conceptual status/capability shape:

```json
{
  "ppu_id": "ppu-01",
  "facility_id": "lab-01",
  "model": "PYNQ-Z2",
  "site_count": 8,
  "enabled_site_count": 2,
  "capabilities": {
    "max_supported_sites": 8,
    "operations": ["erase", "program", "verify", "read"]
  }
}
```

The exact capability schema may evolve, but ownership does not: PPU identity and capability originate from the PPU/device side.

## 11. Control Station, Manager, and standalone integration host

The formal Control Station path is:

```text
Control Station Browser
        |
        v
same-origin Console/BFF
        |
        v
Plasma Manager
        |
        +-- selected PPU A Gateway -> local execution
        +-- selected PPU B Gateway -> local execution
        +-- selected PPU C Gateway -> local execution
```

The packaged Windows and macOS Control Station runtime must start in managed mode. A clean installation with no selected PPU fails closed at the Manager/BFF routing boundary; it must not silently fall back to a remote or remembered Gateway endpoint.

The standalone integration-host path remains valid for development, Engineering Mock, and PPU-local operation:

```text
Browser
   |
   v
same-origin Vite runtime
   |
   v
local Gateway
   |
   +-- Plasma Server / PPU execution
   `-- Engineering Mock Provider when enabled
```

Manager does not move Site scheduling, protocol timing, target safety, or recovery ownership into the Browser. Each PPU remains responsible for its local execution domain.

## 12. Secrets and credentials

Secrets have a separate lifecycle from ordinary configuration.

Rules:

- never commit secrets to the repository;
- do not store secrets in browser `localStorage` for convenience;
- do not copy integration-host or target credentials into Cloud environments simply to collapse validation boundaries;
- prefer OS/service secret mechanisms or a dedicated secret store when production requires one;
- configuration may reference a secret identifier/path but must not duplicate the secret value.

Private SSH usernames, private DNS/VPN identifiers, and workstation inventory belong in operator-local or protected documentation.

## 13. Effective-configuration observability

Operators should progressively be able to answer:

```text
What source version is running?
What config schema is loaded?
Is Browser routing standalone or managed?
Which PPU alias is selected by Manager?
What ports are active?
What Facility / PPU identity is active?
What Site topology/capability is active?
What Gateway policy revision is active?
What derived PPU response budget is effective?
```

A future structured read-only effective-configuration/status endpoint may reduce ambiguity, but its API contract should be designed deliberately rather than inferred from UI convenience.

## 14. Configuration registry baseline

| Key / concept | Domain | Owner | Source of Truth | Notes |
|---|---|---|---|---|
| `PLASMA_CONFIG_VERSION` | Facility/deployment | Deployment | `plasmactl.env` | Current schema v6 |
| `PLASMA_REPO` | Facility/deployment | Deployment | `plasmactl.env` | Host-specific repository location |
| `PLASMA_BRANCH` | Facility/deployment | Deployment | `plasmactl.env` | Normal deployment branch is `main` |
| `PLASMA_GATEWAY_HOST` | Facility/deployment | Deployment | `plasmactl.env` | Gateway bind input |
| `PLASMA_GATEWAY_PORT` | Facility/deployment | Deployment | `plasmactl.env` | Current deployment default 18080 |
| `PLASMA_VITE_HOST` | Facility/deployment | Deployment | `plasmactl.env` | Integration-host Web binding |
| `PLASMA_VITE_PORT` | Facility/deployment | Deployment | `plasmactl.env` | Current default 5173 |
| `PLASMA_PUBLIC_API_URL` | Compatibility | Deployment migration | `plasmactl.env` | Empty in schema v6; direct Browser endpoint ownership retired |
| `PLASMA_MANAGER_ENABLED` | Facility/deployment | Deployment | `plasmactl.env` | Optional on integration host; default `0` |
| `PLASMA_MANAGER_CONFIG` | Fleet control plane | Deployment | Operator-local YAML path | Required only when Manager is enabled |
| `PLASMA_MANAGER_PPU_ALIAS` | Fleet command target | Deployment | `plasmactl.env` or packaged selection file | Required for configured Manager command routing |
| `PLASMA_MANAGER_API_URL` | Derived runtime | Deployment generator | Generated service environment | Local Manager URL; not independent truth |
| `PLASMA_CONTROL_STATION_MODE` | Derived runtime | Packager/deployment generator | Generated service environment | `managed` for formal Control Station |
| `PLASMA_FLEET_UI_ENABLED` | Derived runtime | Packager/deployment generator | Generated service environment | Enabled for formal Control Station |
| `PLASMA_ENGINEERING_MOCK_ENABLED` | Test runtime | Deployment | `plasmactl.env` | Optional; default `0` |
| `PLASMA_ENGINEERING_MOCK_ROOT` | Test runtime | Deployment | Operator-local state path | Must remain outside the Git worktree |
| `NEXT_PUBLIC_PLASMA_API_URL` | Legacy/explicit build input | Deployment/build | Environment when deliberately supplied | No hard-coded remote fallback |
| Same-origin Browser API base | Browser transport | Runtime | `window.location.origin` | Default standalone Browser route |
| Gateway PPU timeout/retry | Gateway policy | Gateway | Persistent Gateway settings YAML | Frozen into each Batch snapshot |
| `ppu_response_budget_ms` | Derived Gateway policy | Gateway | Calculated from timeout/retry/backoff | Read-only; not persisted/writable |
| Browser HTTP watchdog | Derived transport guard | Browser | Gateway response budget + margin | Not a PPU policy source |
| Browser theme/layout | User preference | Browser/user | Browser storage | User-local only |
| PPU ID | PPU identity | PPU provisioning | Device-local identity | Stable resource identity |
| Site count | PPU capability | PPU/device | Device capability report | Support 1–8 in current software |
| Supported operations/interfaces | PPU capability | PPU/device | Device capability report | Hardware-dependent |
| Current job/progress | Runtime state | Plasma runtime | Live server state | Never deployment config |

## 15. Near-term priorities

```text
1. Keep configuration ownership and source-of-truth explicit
2. Keep deployment configuration versioned and reconcilable
3. Keep Browser routing same-origin and topology out of browser storage
4. Keep canonical Site identity one-based across new layers
5. Keep Manager control-plane routing separate from PPU-local execution ownership
6. Keep Gateway communication policy server-owned and derived budgets read-only
7. Keep Engineering Mock available without reintroducing direct Browser Gateway ownership
8. Add effective-config observability where ambiguity remains operationally costly
```

Do not build a large generic configuration framework merely because configuration exists. Add abstraction only when repeated concrete requirements justify it.

## 16. Open architecture questions

- Where will permanent PPU identity be provisioned on production hardware?
- Which PPU/Site capabilities are static and which are runtime-discoverable?
- May individual Sites expose different programming interfaces?
- What registry/enrollment mechanism will Plasma Manager use?
- How are PPUs authenticated, removed, and recovered after reconnect?
- What belongs in target-profile data versus PPU capability data?
- Which configuration changes require restart versus safe hot reload?
- What effective-configuration information is safe to expose through an API?

Resolve these questions from system requirements and executable constraints, not from convenience of a particular UI implementation.
