# Plasma Configuration Architecture

> Status: Proposed baseline for the current prototype and the next multi-programmer phase.
>
> This document defines ownership, source-of-truth, precedence, persistence, migration, and reconciliation rules for Plasma configuration. It does **not** introduce a new configuration framework by itself.

## 1. Purpose

Plasma is moving from a two-channel prototype toward a system that can support multiple programmer devices with different channel counts and hardware capabilities. As that happens, configuration can no longer be treated as a collection of unrelated environment variables, YAML values, systemd settings, and browser preferences.

The objective of this architecture is to prevent configuration drift and ambiguous ownership.

For every configuration value, Plasma must be able to answer five questions:

1. **Owner** — which subsystem is responsible for the value?
2. **Source of Truth** — where is the authoritative value stored or produced?
3. **Precedence** — if more than one candidate value exists, which one wins?
4. **Lifecycle** — when is the value created, changed, applied, and retired?
5. **Version / Migration** — how does an older persisted value move to a newer schema?

A value that cannot answer these questions is not ready to become a permanent configuration surface.

---

## 2. First principles

### 2.1 Configuration is not runtime state

Configuration describes intended or persistent behavior.

Examples:

```text
programmer_id = PLASMA-Z2-001
channel_count = 8
gateway_port = 18080
public_api_url = https://plasma.open4th.com
```

Runtime state describes what the system is doing now.

Examples:

```text
programmer_online = true
CH3.state = programming
CH3.progress = 63%
last_seen = 2026-08-17T16:30:00+08:00
```

Runtime state must not be written back into persistent configuration merely because it is convenient to serialize both in the same format.

### 2.2 Capability is not user preference

A programmer's hardware capability is a property of the programmer/device and must not be owned by the browser.

Examples:

```text
channels = 8
interfaces = [SWD, SPI, I2C]
fpga_design_version = ...
```

Browser preferences are presentation choices.

Examples:

```text
theme = light
visible_channels = [0, 1]
layout = compact
```

The browser may cache preferences, but it must not become the authoritative source for programmer topology or hardware capability.

### 2.3 Derived configuration is not a second source of truth

A generated systemd unit, environment block, build artifact, or browser bootstrap value may contain a copy of configuration, but that copy is **derived state**.

Derived state must be regenerable from its authoritative source.

### 2.4 Deployment is reconciliation, not only restart

A correct deployment process does not merely pull code and restart processes. It must converge the effective runtime toward the desired configuration state:

```text
source defaults
      ↓
persistent site configuration
      ↓
validation / migration
      ↓
generated runtime configuration
      ↓
service restart
      ↓
health / effective-state verification
```

---

## 3. Configuration domains

Plasma configuration is divided into domains because a single global precedence rule is unsafe. Different types of values have different owners and lifecycles.

| Domain | Examples | Owner | Authoritative source |
|---|---|---|---|
| Product defaults | default timeout, firmware size limit | Source code | Checked-in code/configuration |
| Site / deployment | public API URL, service ports, repository path | Deployment operator | Versioned persistent deployment config |
| Programmer identity | programmer ID, model, serial identity | Programmer/device provisioning | Device-local persistent identity |
| Programmer capability | channel count, supported interfaces, FPGA/firmware capability | Programmer runtime / hardware | Device-reported capability |
| Target profile | IC family, memory geometry, required interface | Target definition layer | Checked-in target/profile database |
| Job configuration | operation, target, file, offset, read length | Job request | Accepted server-side job record |
| Runtime state | online, busy, progress, current job | Runtime services | Live server/device state |
| User preference | theme, layout, visible channels | Browser/user | Browser-local preference storage |
| Secrets / credentials | certificates, tokens, private keys | Security/deployment layer | Protected secret storage |

The current repository does not yet implement every domain above. The table defines the intended ownership boundary so future features do not invent conflicting storage locations.

---

## 4. Current SWPC deployment configuration

The current SWPC deployment uses:

```text
~/.config/plasma/plasmactl.env
```

as the persistent site/deployment configuration source for `scripts/plasmactl`.

The current schema version is:

```bash
PLASMA_CONFIG_VERSION=2
```

Current deployment keys include:

```bash
PLASMA_REPO=/storage/projects/plasma
PLASMA_BRANCH=main
PLASMA_NPM=...
PLASMA_UV=...
PLASMA_GATEWAY_HOST=0.0.0.0
PLASMA_GATEWAY_PORT=18080
PLASMA_CORS_ORIGIN='*'
PLASMA_VITE_HOST=127.0.0.1
PLASMA_VITE_PORT=5173
PLASMA_PUBLIC_API_URL=https://plasma.open4th.com
```

### 4.1 Ownership rule

For these deployment keys:

```text
code default
    ↓ fallback only
persistent plasmactl.env
    ↓ authoritative deployment value
validated/migrated plasmactl model
    ↓
generated systemd units
    ↓
active processes
```

The generated systemd unit is **not** an independent source of truth.

Manual edits to generated units are therefore unsupported as a long-term configuration mechanism; reconciliation may overwrite them.

### 4.2 Current service-derived values

For example, `PLASMA_PUBLIC_API_URL` is transformed into the Web service environment:

```text
NEXT_PUBLIC_PLASMA_API_URL
```

The service environment is a derived copy. `plasmactl start` and `plasmactl restart` must regenerate units from the current validated deployment configuration and run `systemctl --user daemon-reload` before activating services.

---

## 5. Configuration precedence

There is no single precedence chain for every Plasma setting. Precedence is defined per domain.

### 5.1 Site/deployment configuration

For a deployment setting such as `PLASMA_PUBLIC_API_URL`:

```text
1. Valid explicit persistent site configuration
2. Product/source default
```

Generated systemd values do not participate in precedence because they are outputs, not inputs.

### 5.2 Browser/user preference

For a user preference such as theme:

```text
1. Valid browser-local user preference
2. UI product default
```

### 5.3 Browser API override in the current prototype

The Web Console currently permits an operator to enter and persist an API Base in browser storage. This is retained as a prototype/development convenience.

Its policy is:

```text
valid explicit browser API override
    ↓
deployed DEFAULT_API_BASE
```

However, this browser value is **not** the source of truth for programmer topology or production routing.

Known obsolete defaults may be migrated out of browser storage. Unknown/custom values are preserved because they may represent an intentional operator override.

For a production-oriented multi-programmer console, this override should be reconsidered or restricted rather than expanded into a topology database.

### 5.4 Programmer capability

For hardware capability:

```text
1. Valid capability reported by the programmer/device
2. Provisioned device model defaults, if available
3. No browser override
```

A Web UI must not manufacture channel count or interface support when the programmer reports different capabilities.

### 5.5 Job configuration

Once a job is accepted, the server-side job record becomes authoritative for that execution.

The browser request is an input to job creation, not a continuously authoritative object after acceptance.

---

## 6. Schema versioning and migration

Any persistent configuration that can survive a software upgrade must have an explicit schema/version strategy.

### 6.1 Why schema version is required

Without a schema version, deployment cannot reliably distinguish between:

- a stale value created automatically by an old release; and
- an intentional operator override.

That ambiguity caused the public API endpoint configuration drift addressed by the v2 deployment migration.

### 6.2 Migration rules

A migration must be:

- deterministic;
- bounded to known old schemas/values;
- idempotent;
- non-destructive to unknown operator overrides unless the schema contract explicitly says otherwise;
- testable without a live SWPC service restart when practical.

The current v1/unversioned → v2 API Base migration follows this rule:

```text
known historical defaults
    → migrate to current canonical default

unknown/custom value
    → preserve as explicit operator override

already v2
    → do not guess intent again
```

### 6.3 Future schema evolution

Future persistent configuration formats should follow the same pattern:

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

Migration code and migration tests must land in the same change whenever feasible.

---

## 7. Runtime reconciliation

Persistent configuration and active runtime can diverge unless deployment actively reconciles them.

For SWPC the desired flow is:

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

The important invariant is:

> If the persistent deployment configuration is valid, a normal `plasmactl restart` must be sufficient to regenerate derived service configuration and activate it.

Re-running `install` must not be required simply to make a normal configuration change take effect.

---

## 8. Browser storage boundary

Browser storage is allowed for user-local state, but every key must be classified.

### 8.1 Allowed browser-owned values

Examples:

```text
plasma-theme
visible-channel preference
layout preference
language preference
```

These values affect presentation and do not redefine system topology.

### 8.2 Transitional/operator values

The current prototype also stores:

```text
plasma-api-base
plasma-api-base-version
```

The API Base is a transitional operator convenience, not a general-purpose configuration database.

Known legacy endpoint values are migrated once so an obsolete browser value does not permanently override the deployed endpoint.

### 8.3 Values that must not become browser truth

The following must not be authoritative in `localStorage`:

```text
programmer inventory
programmer channel count
programmer hardware interfaces
programmer firmware/FPGA compatibility
production routing policy
authentication secrets
job execution state
```

---

## 9. Programmer identity and capability model

The next Plasma phase will need to support programmer devices that may expose 2, 4, or 8 channels.

The Web Console must not hard-code those differences as separate front-end products.

A programmer should eventually expose a machine-readable identity/capability model similar to:

```json
{
  "programmer_id": "PLASMA-Z2-001",
  "model": "Z2-PROTOTYPE",
  "channel_count": 8,
  "interfaces": ["SWD", "SPI", "I2C"],
  "software_version": "...",
  "fpga_design_version": "..."
}
```

The exact API/schema is **not defined by this document**. The ownership rule is defined:

> Programmer identity and capability originate from the programmer/device side and are consumed by higher-level software; they are not invented by the browser.

This allows one Web Console architecture to render different programmer models from capability data instead of maintaining separate fixed 2-channel, 4-channel, and 8-channel UI implementations.

---

## 10. Multi-programmer topology

### 10.1 Current state

The current implemented Web path is effectively one Web Console communicating with one Python HTTP Gateway, which then communicates with the Plasma Server.

The current Gateway is the repository's Python HTTP Gateway implementation; architecture work must follow executable code and tests rather than older discussions about FastAPI/WebSocket.

### 10.2 Target direction

When Plasma supports multiple programmer devices, topology should move toward a manager/registry model:

```text
Web Console
    │
    ▼
Plasma Manager / Registry
    │
    ├── Programmer A (2 channels)
    ├── Programmer B (4 channels)
    └── Programmer C (8 channels)
```

The manager/registry should eventually become the authoritative source for programmer inventory and connection topology.

The browser should query topology rather than permanently store a list of programmer URLs.

This is a target architecture boundary, not a claim that a central manager already exists.

---

## 11. Secrets and credentials

Secrets require a separate lifecycle from ordinary configuration.

Examples include:

```text
Cloudflare credentials
private keys
access tokens
device certificates
future programmer enrollment credentials
```

Rules:

- Never commit secrets to the repository.
- Do not place secrets in browser `localStorage` as a convenience.
- Do not copy SWPC/Z2 credentials into Codex Cloud merely to collapse validation boundaries.
- Prefer OS/service secret mechanisms or a dedicated secret store when the production architecture requires one.
- A configuration document may reference a secret identifier/path, but should not duplicate the secret value.

---

## 12. Effective configuration observability

A configuration system is difficult to operate if an engineer can inspect only input files but not the values actually active at runtime.

Plasma should progressively make effective configuration observable.

Minimum operational verification should answer:

```text
What source version is running?
What config schema is loaded?
What public API Base is effective?
What ports are active?
What programmer identity/capability is active?
What generated service environment is active?
```

Today, SWPC inspection is distributed across `plasmactl status`, `plasmactl.env`, generated systemd units, service status, and HTTP health checks.

A future structured read-only effective-configuration/status endpoint may reduce operational ambiguity, but its API contract should be designed separately before implementation.

---

## 13. Configuration change lifecycle

A new persistent configuration key should not be added until its lifecycle is documented.

Use this checklist:

1. Name the configuration domain.
2. Define the owner.
3. Define the authoritative source.
4. Define valid type/range/enum constraints.
5. Define whether a source-code default exists.
6. Define precedence and whether overrides are allowed.
7. Define persistence location and scope: repository, site, device, user, or job.
8. Define whether the value is secret.
9. Define how runtime receives the value.
10. Define how derived copies are reconciled.
11. Define schema/migration behavior for persisted values.
12. Define how operators inspect the effective value.
13. Add tests for validation/migration/reconciliation when applicable.
14. Update architecture/deployment documentation together with behavior changes.

If ownership or source-of-truth cannot be stated unambiguously, the configuration design is incomplete.

---

## 14. Anti-patterns

The following designs should be treated as architectural warnings:

### 14.1 Same value independently persisted in multiple layers

Bad:

```text
source default = A
plasmactl.env = B
systemd unit manually edited to C
browser localStorage = D
```

Correct direction:

```text
authoritative input
    ↓
validated model
    ↓
generated/derived copies
```

### 14.2 Browser as device inventory database

Bad:

```text
localStorage:
  programmer_A_url
  programmer_B_url
  programmer_A_channel_count
```

Correct direction:

```text
Browser
  ↓ query
Manager / programmer capability API
```

### 14.3 Runtime state written into static config

Bad:

```yaml
channel_3:
  state: programming
  progress: 63
```

inside a persistent programmer configuration file.

### 14.4 Silent fallback after invalid explicit configuration

An invalid operator value should normally fail validation with a clear diagnostic rather than silently falling back to a different endpoint or hardware behavior.

Fallback is appropriate for an **absent optional value**, not for a malformed explicit value.

### 14.5 Migration by unconditional overwrite

A migration must not overwrite every historical-looking value without considering whether the current schema treats it as an explicit operator choice.

---

## 15. Configuration registry baseline

The following table is the initial registry for important current/near-term values. It should evolve as implementation evolves.

| Key / Concept | Domain | Owner | Source of Truth | Notes |
|---|---|---|---|---|
| `PLASMA_CONFIG_VERSION` | Site/deployment | Deployment | `plasmactl.env` | Controls deployment config migration |
| `PLASMA_REPO` | Site/deployment | Deployment | `plasmactl.env` | SWPC repository location |
| `PLASMA_BRANCH` | Site/deployment | Deployment | `plasmactl.env` | SWPC deployment branch; current normal value `main` |
| `PLASMA_GATEWAY_HOST` | Site/deployment | Deployment | `plasmactl.env` | Runtime binding input |
| `PLASMA_GATEWAY_PORT` | Site/deployment | Deployment | `plasmactl.env` | SWPC operational port 18080 |
| `PLASMA_VITE_HOST` | Site/deployment | Deployment | `plasmactl.env` | Demo/development Web service binding |
| `PLASMA_VITE_PORT` | Site/deployment | Deployment | `plasmactl.env` | Current SWPC Web service port 5173 |
| `PLASMA_PUBLIC_API_URL` | Site/deployment | Deployment | `plasmactl.env` | Canonical default `https://plasma.open4th.com` |
| `NEXT_PUBLIC_PLASMA_API_URL` | Derived runtime | Deployment generator | Generated systemd environment | Must not be manually treated as independent truth |
| `plasma-theme` | User preference | Browser/user | Browser storage | Safe user-local preference |
| `plasma-api-base` | Transitional operator override | Browser/operator | Browser storage | Prototype convenience; not topology truth |
| Programmer ID | Programmer identity | Programmer provisioning | Device-local identity | Exact storage format TBD |
| Channel count | Programmer capability | Programmer/device | Device capability report | Must support model variation 2/4/8 without separate UI products |
| Supported interfaces | Programmer capability | Programmer/device | Device capability report | SWD/SPI/I2C/etc.; exact schema TBD |
| Current job/progress | Runtime state | Plasma runtime | Live server state | Never persistent deployment configuration |

---

## 16. Decisions established by the API Base incident

The API Base configuration incident established several permanent engineering rules:

1. Changing a source default is not sufficient when older persistent configuration exists.
2. Persistent configuration requires schema/version migration.
3. Generated systemd units are derived state and must be reconciled from persistent configuration.
4. A self-updating deployment script must re-exec after updating itself before relying on new deployment logic.
5. Browser storage is an additional persistence layer and must have explicit migration/ownership rules.
6. Unknown operator overrides should not be destroyed merely to force a new default.
7. Deployment success and browser-effective behavior are separate observations and should be verified separately.

---

## 17. Near-term implementation priorities

This architecture document does not justify building a large generic `ConfigManager` framework immediately.

The near-term priority order is:

```text
1. Define ownership and boundaries
2. Keep current deployment config versioned and reconcilable
3. Stop adding topology/capability truth to browser storage
4. Define programmer identity/capability schema before multi-programmer UI work
5. Define manager/registry topology contract before supporting multiple Z2 programmers
6. Add effective-config observability where operational ambiguity remains costly
```

Implement abstractions only when repeated concrete requirements justify them.

---

## 18. Open architecture questions

The following questions require explicit decisions before the corresponding production features are implemented:

- Where will permanent programmer identity be provisioned on Z2?
- Which programmer capabilities are compile-time/static and which are runtime-discoverable?
- Will channel capability be uniform per programmer or may individual channels expose different interfaces?
- What component becomes the multi-programmer registry/manager?
- How are programmers enrolled, authenticated, and removed from that manager?
- What configuration belongs in a target-profile database versus programmer capability data?
- Which configuration changes require a service restart and which can be safely hot-reloaded?
- What effective-configuration information is safe to expose through an API?
- At what stage should the browser API Base override be removed or restricted for production deployments?

These questions should be resolved from system requirements and executable constraints rather than convenience of a particular UI implementation.
