# Plasma Manager Runtime PPU Registry

## Purpose

The EMode `PPU / Site` surface manages which Plasma Gateways belong to a Plasma Manager deployment. This inventory is operational state, not source-controlled deployment configuration.

The ownership chain is:

```text
Control Console
  -> same-origin Manager BFF
  -> Plasma Manager runtime registry
  -> Plasma Gateway
  -> Plasma Server
  -> Sites
```

The Console never edits `manager.yaml` and never invents PPU identity or physical Site topology.

## Bootstrap versus runtime state

`manager.yaml` remains the explicit deployment/bootstrap configuration. Existing `ppus:` entries keep backward compatibility.

When `manager.registry_state_path` is omitted:

- Manager keeps the historical config-backed read-only registry;
- `GET /api/registry` remains available;
- runtime Add / Validate & Enable / Disable / Remove mutations are rejected;
- Static IPv4 commissioning is rejected because Manager cannot durably reconcile a changed Plasma Gateway Endpoint.

When `manager.registry_state_path` is configured:

1. if the runtime registry state file does not exist, Manager seeds it from `manager.yaml` `ppus:` entries;
2. seeded entries are treated as already commissioned so existing deployments do not unexpectedly lose write authority;
3. after the state file exists, it becomes the runtime inventory source of truth;
4. later Add / Validate & Enable / Disable / Remove operations update the runtime state file atomically;
5. a successfully committed Static IPv4 commissioning transaction may update only the affected PPU's Plasma Gateway Endpoint through a compare-and-swap operation;
6. Manager does not rewrite `manager.yaml`.

This separation prevents runtime inventory churn from becoming deployment-file churn and avoids concurrent Browser/YAML ownership of the same state.

## Deployment defaults

New Control Station installations provision a writable operator-local runtime registry path:

```text
macOS
$HOME/Library/Application Support/Plasma/state/manager-registry.json

Windows
%ProgramData%\Plasma\state\manager-registry.json
```

The installer-created `manager.yaml` points to those paths. The immutable application release does not contain registry state.

Existing integration-host or manually maintained Manager configuration is not silently rewritten during this change. Those deployments remain config-backed/read-only until an operator explicitly adds an absolute `manager.registry_state_path` and applies the normal deployment reconciliation/restart gate. This is intentional: enabling Browser-driven inventory mutation changes control-plane authority and must not appear as an implicit software upgrade side effect.

When runtime registry persistence is enabled, Manager derives its network-commissioning journal beside the registry state file. The journal is Manager-owned operational state and is not source controlled.

## Lifecycle

The operator-facing workflow is:

```text
Add PPU
  -> Pending
  -> Manager observes current trusted identity/topology
  -> Validate & Enable
  -> Enabled for managed write operations

Enabled
  -> Disable
  -> Disabled

Pending / Enabled / Disabled
  -> Remove PPU
  -> registry entry removed only
```

The internal lifecycle token for a PPU that passed `Validate & Enable` is `commissioned`. The Console intentionally does not use `Commission` as the primary operator label.

`Remove PPU` means only "remove this Plasma Gateway Endpoint/alias from Manager inventory". It does not erase, reset, power off, update firmware, or change the physical PPU.

## Validation gate

Manager, not the Browser, decides whether `Validate & Enable` is allowed. A PPU must have a current trusted fleet observation with:

- reachable Plasma Gateway;
- execution-ready PPU;
- compatible PPU fleet contract;
- no canonical `ppu_id` identity conflict;
- valid PPU identity and Site topology;
- no current observation errors.

A stale or unknown observation is not enough to enable a newly added PPU.

The same trusted-observation requirement is rechecked before Manager starts a Static IPv4 commissioning transaction. Commissioning is also rejected while Manager observes active Site execution.

## Write authority

Pending and Disabled PPUs may still be observed with read requests. Managed write operations are rejected until lifecycle is `commissioned`.

Disable and Remove are rejected when Manager has evidence of an active Site/Job. This guard prevents the control plane from intentionally forgetting or disabling a target it knows is executing.

An unreachable PPU can still be removed because removal is an inventory operation, not a remote stop command. The Console confirmation must keep that distinction explicit.

Static IPv4 commissioning is different from an ordinary registry edit. The Browser cannot directly write a replacement endpoint. Manager first proves that the PPU activation was committed after same-`ppu_id` verification, then performs the registry endpoint mutation itself.

## API

Manager runtime registry endpoints:

```text
GET    /api/registry
POST   /api/registry
PATCH  /api/registry/{alias}
DELETE /api/registry/{alias}
```

`POST /api/registry` accepts only:

```json
{
  "alias": "line1-ppu-a",
  "endpoint": "http://192.168.10.21:18080"
}
```

Here, `endpoint` is the **Plasma Gateway Endpoint** for the PPU. The field name remains `endpoint` for API compatibility.

A new entry starts as `pending`.

Lifecycle update:

```json
{
  "lifecycle": "commissioned"
}
```

or:

```json
{
  "lifecycle": "disabled"
}
```

The explicit Manager-owned Static IPv4 commissioning resource is:

```text
GET  /api/registry/{alias}/network-commissioning
POST /api/registry/{alias}/network-commissioning
```

It is not a generic Plasma Gateway relay. The POST requires an `Idempotency-Key` and a static desired-network object. The Manager owns candidate endpoint derivation, reconnect, same-`ppu_id` verification, PPU commit, and durable endpoint reconciliation.

The Browser reaches these endpoints only through the same-origin `/api/manager/registry` BFF. The BFF keeps the Manager API URL loopback-only and requires Managed Control Station mode for registry mutation and commissioning.

## Endpoint compare-and-swap invariant

Registry endpoint reconciliation uses compare-and-swap rather than blind replacement:

```text
transaction starts with old_endpoint=A
PPU activation commits candidate=B
Manager registry update succeeds only if current endpoint is still A
```

The mutation is rejected when:

- the alias disappeared;
- another PPU already owns candidate endpoint B;
- an operator or concurrent transaction changed the alias endpoint after this transaction started.

This prevents a completed network activation from silently overwriting newer control-plane state. If PPU activation is already committed but registry compare-and-swap cannot be completed, the commissioning journal records `recovery_required` rather than guessing.

## Site configuration boundary

The PPU owns physical Site count, canonical one-based `site_id`, interface, target, and current enabled state. The current PPU/Site management slice displays those values from Manager Fleet observations.

Persistent Site Enable/Disable is deliberately read-only until a separate PPU-owned Site configuration contract exists. The Console must not simulate Site configuration with Browser-local toggles.

## Persistence failure semantics

Registry state is written with a temporary file followed by atomic replacement. Runtime mutation must fail rather than report success when durable state cannot be written. In-memory mutation is rolled back if persistence fails.

A corrupt or unsupported existing runtime registry file fails Manager startup rather than silently rebuilding from `manager.yaml`, because silently discarding operational inventory would be more dangerous than failing closed.

Network commissioning follows the same fail-closed principle. The Manager journal never stores the caller's `Authorization` header. After restart, only a transaction with already-durable `activation_committed` evidence may automatically finish Manager-local endpoint reconciliation. Earlier ambiguous states become `recovery_required` and do not mutate the registry automatically.
