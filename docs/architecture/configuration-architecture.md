# Plasma Configuration Architecture

> Status: baseline for the current prototype and the next multi-programmer phase.

This document defines ownership, source-of-truth, precedence, persistence, migration, and reconciliation rules for Plasma configuration. It intentionally avoids site-specific account names, private hostnames, and absolute workstation paths.

## 1. First principles

Configuration describes intended or persistent behavior. Runtime state describes what the system is doing now. These are different domains and must not be collapsed merely because both can be serialized.

A permanent configuration value must have explicit answers for:

1. **Owner** — which subsystem is responsible?
2. **Source of Truth** — where is the authoritative value stored or produced?
3. **Precedence** — which candidate wins when multiple values exist?
4. **Lifecycle** — when is it created, changed, applied, and retired?
5. **Version/Migration** — how does persisted old state move to a new schema?

Derived configuration such as generated systemd units, environment blocks, or browser bootstrap values is not a second source of truth. Derived state must be reproducible from authoritative input.

## 2. Configuration domains

| Domain | Examples | Owner | Authoritative source |
|---|---|---|---|
| Product defaults | timeout, size limit | Source code | Checked-in code/config |
| Site/deployment | service ports, repository path, public API URL | Deployment operator | Persistent deployment config |
| Programmer identity | programmer ID, model, serial identity | Device provisioning | Device-local persistent identity |
| Programmer capability | channel count, interfaces, FPGA/firmware capability | Programmer runtime/hardware | Device-reported capability |
| Target profile | IC family, memory geometry, interface | Target-definition layer | Checked-in target/profile data |
| Job configuration | operation, target, file, offset, read length | Job request/server | Accepted server-side job record |
| Runtime state | online, busy, progress, current job | Runtime services | Live state |
| User preference | theme, layout, visible channels | Browser/user | Browser-local preference storage |
| Secrets/credentials | certificates, tokens, private keys | Security/deployment layer | Protected secret storage |

A browser may cache presentation preferences, but it must not become authoritative for programmer topology or hardware capability.

## 3. Deployment configuration

The integration host uses a persistent operator configuration file under the user's configuration directory:

```text
$HOME/.config/plasma/plasmactl.env
```

The current schema version is:

```bash
PLASMA_CONFIG_VERSION=2
```

A public example uses generic site-specific paths:

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
PLASMA_PUBLIC_API_URL=https://plasma.open4th.com
```

The ownership chain is:

```text
product/source default
       ↓ fallback only
persistent site configuration
       ↓ authoritative deployment value
validation / migration
       ↓
generated systemd units
       ↓
active processes
```

Generated systemd units are derived state. Manual edits to generated units are not a supported long-term configuration mechanism.

## 4. Precedence rules

There is no universal precedence chain for every setting. Precedence is domain-specific.

### Site/deployment

```text
1. valid explicit persistent site configuration
2. product/source default
```

### Browser/user preference

```text
1. valid browser-local preference
2. UI product default
```

### Transitional browser API override

The prototype may allow an operator-entered API Base for development convenience:

```text
valid explicit browser API override
    ↓
deployed default API Base
```

This value is not topology truth and should not evolve into a browser-owned programmer inventory.

### Programmer capability

```text
1. valid capability reported by the programmer/device
2. provisioned device-model default, when available
3. no browser override
```

### Job configuration

Once a job is accepted, the server-side job record becomes authoritative for that execution.

## 5. Schema versioning and migration

Any configuration that survives a software upgrade requires an explicit schema/version strategy. Otherwise deployment cannot distinguish an automatically persisted old default from an intentional operator override.

A migration must be:

- deterministic;
- bounded to known old schemas/values;
- idempotent;
- non-destructive to unknown operator overrides unless the schema contract explicitly requires it;
- covered by regression tests.

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

Known historical defaults may migrate to the current canonical default. Unknown/custom values are preserved as explicit operator overrides. Already-versioned values are not repeatedly reinterpreted.

Private addresses used by a development site are compatibility data, not documentation requirements. If executable migration code must still recognize a historical value, executable code and tests remain the source of truth without repeating that infrastructure inventory in public documentation.

## 6. Runtime reconciliation

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

## 7. Browser storage boundary

Browser storage is suitable for user-local presentation state, for example:

```text
theme
visible-channel preference
layout preference
language preference
```

The following must not become authoritative browser state:

```text
programmer inventory
programmer channel count
programmer hardware interfaces
programmer firmware/FPGA compatibility
production routing policy
authentication secrets
job execution state
```

The prototype API Base override is a transitional operator convenience and must not expand into a topology database.

## 8. Programmer identity and capability

Plasma must support programmers exposing different channel counts without creating separate frontend products.

A programmer should expose a machine-readable identity/capability model conceptually similar to:

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

The exact final schema is not defined here. The ownership rule is:

> Programmer identity and capability originate from the programmer/device side and are consumed by higher-level software; they are not invented by the browser.

## 9. Multi-programmer topology

The current implemented path is one Web Console communicating with one Python HTTP REST Gateway, which communicates with the Plasma Server.

The current Gateway is the repository's implemented Python HTTP Gateway. Future architecture must follow executable code and tests rather than stale assumptions about frameworks discussed earlier.

Target direction:

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

The manager/registry should eventually become authoritative for programmer inventory and connection topology. The browser should query topology rather than permanently store a list of programmer URLs.

This is a target boundary, not a claim that a central manager already exists.

## 10. Secrets and credentials

Secrets have a separate lifecycle from ordinary configuration.

Rules:

- never commit secrets to the repository;
- do not store secrets in browser `localStorage` for convenience;
- do not copy integration-host or target credentials into Cloud environments simply to collapse validation boundaries;
- prefer OS/service secret mechanisms or a dedicated secret store when production requires one;
- configuration may reference a secret identifier/path but must not duplicate the secret value.

Private SSH usernames, private DNS/VPN/Tailscale identifiers, and workstation inventory are infrastructure metadata and likewise belong in operator-local or protected documentation.

## 11. Effective-configuration observability

Operators should progressively be able to answer:

```text
What source version is running?
What config schema is loaded?
What public API Base is effective?
What ports are active?
What programmer identity/capability is active?
What generated service environment is active?
```

A future structured read-only effective-configuration/status endpoint may reduce ambiguity, but its API contract should be designed separately before implementation.

## 12. Configuration change lifecycle

Before adding a new persistent configuration key:

1. name the configuration domain;
2. define the owner;
3. define the authoritative source;
4. define valid type/range/enum constraints;
5. define whether a source default exists;
6. define precedence and allowed overrides;
7. define persistence scope: repository, site, device, user, or job;
8. define whether the value is secret;
9. define how runtime receives it;
10. define how derived copies are reconciled;
11. define schema/migration behavior;
12. define how the effective value is inspected;
13. add validation/migration/reconciliation tests when applicable;
14. update documentation with behavior changes.

If ownership or source-of-truth cannot be stated unambiguously, the configuration design is incomplete.

## 13. Anti-patterns

Avoid:

- the same value independently persisted in source defaults, persistent config, generated units, and browser storage;
- browser storage used as a device-inventory database;
- runtime progress/state written into static configuration;
- silent fallback from malformed explicit operator configuration;
- unconditional migration overwrite of unknown values;
- public documentation used as an operator infrastructure inventory.

Correct direction:

```text
authoritative input
    ↓
validated model
    ↓
generated / derived copies
```

## 14. Configuration registry baseline

| Key / concept | Domain | Owner | Source of Truth | Notes |
|---|---|---|---|---|
| `PLASMA_CONFIG_VERSION` | Site/deployment | Deployment | `plasmactl.env` | Controls deployment migration |
| `PLASMA_REPO` | Site/deployment | Deployment | `plasmactl.env` | Site-specific repository location |
| `PLASMA_BRANCH` | Site/deployment | Deployment | `plasmactl.env` | Normal deployment branch is `main` |
| `PLASMA_GATEWAY_HOST` | Site/deployment | Deployment | `plasmactl.env` | Runtime binding input |
| `PLASMA_GATEWAY_PORT` | Site/deployment | Deployment | `plasmactl.env` | Current default 18080 |
| `PLASMA_VITE_HOST` | Site/deployment | Deployment | `plasmactl.env` | Development/demo Web binding |
| `PLASMA_VITE_PORT` | Site/deployment | Deployment | `plasmactl.env` | Current default 5173 |
| `PLASMA_PUBLIC_API_URL` | Site/deployment | Deployment | `plasmactl.env` | Public API Base configuration |
| `NEXT_PUBLIC_PLASMA_API_URL` | Derived runtime | Deployment generator | Generated systemd environment | Not independent truth |
| Browser theme/layout | User preference | Browser/user | Browser storage | User-local only |
| Browser API Base | Transitional operator override | Browser/operator | Browser storage | Prototype convenience |
| Programmer ID | Programmer identity | Programmer provisioning | Device-local identity | Exact storage TBD |
| Channel count | Programmer capability | Programmer/device | Device capability report | Support model variation |
| Supported interfaces | Programmer capability | Programmer/device | Device capability report | SWD/SPI/I2C/etc. |
| Current job/progress | Runtime state | Plasma runtime | Live server state | Never deployment config |

## 15. Near-term priorities

```text
1. Keep ownership and configuration boundaries explicit
2. Keep deployment configuration versioned and reconcilable
3. Stop adding topology/capability truth to browser storage
4. Define programmer identity/capability schema before multi-programmer UI expansion
5. Define manager/registry topology before supporting multiple programmers
6. Add effective-config observability where ambiguity remains costly
```

Do not build a large generic configuration framework merely because configuration exists. Introduce abstractions only when repeated concrete requirements justify them.

## 16. Open architecture questions

- Where will permanent programmer identity be provisioned on Z2?
- Which capabilities are static and which are runtime-discoverable?
- May individual channels expose different interfaces?
- What component becomes the multi-programmer registry/manager?
- How are programmers enrolled, authenticated, and removed?
- What belongs in target-profile data versus programmer capability data?
- Which configuration changes require restart versus safe hot reload?
- What effective-configuration information is safe to expose through an API?
- When should the browser API Base override be removed or restricted for production?

These questions must be resolved from system requirements and executable constraints rather than convenience of a particular UI implementation.
