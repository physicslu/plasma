# PPU Network Configuration

## Purpose

This document defines the PPU-owned network configuration contract used by the `PPU / SITE Configuration` commissioning workflow.

The ownership boundary is:

```text
Control Console
        |
        v
Manager BFF
        |
        v
Plasma Manager
        |
        | static IPv4 commissioning orchestration / reconnect
        v
Plasma Gateway (unprivileged)
        |
        +--> desired PPU network settings
        +--> activation transaction + durable journal
        |
        `--> Unix socket
                |
                v
        privileged Network Activation Helper
                |
                v
        Linux network subsystem
```

Canonical terminology is:

- **Plasma Gateway** — the northbound API service running on each PPU;
- **Plasma Gateway API** — the REST contract exposed by that service;
- **Plasma Gateway Endpoint** — the service network location such as `http://192.168.2.99:18080`;
- **Default Gateway** — the Linux Layer-3 next-hop router for `eth0`, not the Plasma Gateway service.

PPU network configuration is separate from Plasma Gateway communication policy:

```text
/api/settings/gateway       Plasma Gateway communication timeout/retry policy
/api/settings/ppu-network   this PPU's desired Linux eth0 configuration
```

The existing `/api/settings/gateway` path is retained for API compatibility. The `gateway` JSON field inside `/api/settings/ppu-network` is also retained for wire compatibility, but its operator-facing meaning is **Default Gateway**.

## Phase 1 desired-state contract

Phase 1 provides a validated, persistent desired-state contract. Canonical routes:

```text
GET  /api/settings/ppu-network
POST /api/settings/ppu-network
```

The configured interface is fixed to `eth0`. Supported desired modes are `dhcp` and `static`.

The server owns `revision` and `interface`. Clients write exactly:

```json
{
  "mode": "static",
  "address": "192.168.10.21",
  "prefix_length": 24,
  "gateway": "192.168.10.1",
  "dns_servers": ["192.168.10.1", "8.8.8.8"]
}
```

In this schema, `gateway` means the Linux **Default Gateway**. It does not identify the Plasma Gateway service.

For DHCP mode, all static fields must be empty:

```json
{
  "mode": "dhcp",
  "address": null,
  "prefix_length": null,
  "gateway": null,
  "dns_servers": []
}
```

When no privileged activation helper is configured, the response retains the Phase 1 boundary:

```json
{
  "activation": {
    "supported": false,
    "state": "not_implemented"
  }
}
```

A successful desired-state POST means the configuration was validated and durably stored. It does not by itself mean that `eth0`, routes, DNS, DHCP client state, or the current Plasma Gateway Endpoint changed.

## Desired-state validation and persistence

Static mode requires:

- a valid IPv4 address;
- `prefix_length` in the range `1..32`;
- no network/broadcast address for prefixes where those addresses are reserved;
- an optional **Default Gateway** on the configured subnet and different from the PPU address;
- at most three unique IPv4 DNS server addresses.

DHCP mode rejects static address, prefix, Default Gateway, and DNS values. Unknown and missing POST fields are rejected rather than silently ignored.

The desired-state persistence file is:

```text
<output-root>/ppu-network-settings.yaml
```

Updates use temporary-file write, flush, `fsync`, and atomic replacement. The in-memory desired state changes only after persistence succeeds. An invalid existing persistence file fails closed during Plasma Gateway startup.

## Control Station desired-state integration

The EMode `PPU / SITE Configuration` surface can read and persist the selected PPU's desired network state through the existing Manager-owned control path:

```text
Control Console
  -> same-origin Manager BFF
  -> Manager alias-scoped allowlisted relay
  -> selected Plasma Gateway
  -> GET/POST /api/settings/ppu-network
```

The Browser supplies the selected Manager registry alias, not a destination URL. The Manager resolves the registered Plasma Gateway Endpoint and remains the routing owner. The desired-state relay exposes only the exact PPU network settings resource; the Browser does not receive an arbitrary Manager reverse-proxy capability.

A desired-state write through this surface requires the PPU registry lifecycle to be `commissioned` (`Validate & Enable` completed). The Console also disables the edit while it has evidence of active Site execution, an active PPU network activation, or a blocking Manager commissioning transaction. The Plasma Gateway remains the authoritative desired-state validator and persistence owner.

The panel displays:

- fixed interface `eth0`;
- desired revision and mode;
- static IPv4 address, prefix length, **Default Gateway**, and DNS fields when applicable;
- PPU activation support/state;
- last committed PPU activation revision when available;
- latest Manager commissioning transaction state and candidate endpoint when present.

The operator action **Save Desired Network** deliberately remains separate from **Commission Static Network**.

`Save Desired Network` means only:

```text
validate desired values
-> persist PPU-owned desired settings
-> return new desired revision
```

It does **not** mean:

```text
mutate Linux eth0
change the Manager registry Plasma Gateway Endpoint
prove candidate reachability
commit an activation
```

`Commission Static Network` is the Manager-owned endpoint migration transaction. The Browser does not call `/api/settings/ppu-network/activation` directly.

## Manager-owned Static IPv4 commissioning

Manager exposes an explicit resource separate from the generic managed PPU relay:

```text
GET  /api/registry/{alias}/network-commissioning
POST /api/registry/{alias}/network-commissioning
```

The same-origin Browser route is:

```text
/api/manager/registry/{alias}/network-commissioning
```

The POST requires `Idempotency-Key` and accepts:

```json
{
  "desired": {
    "mode": "static",
    "address": "192.168.10.21",
    "prefix_length": 24,
    "gateway": "192.168.10.1",
    "dns_servers": ["192.168.10.1"]
  },
  "rollback_timeout_s": 20
}
```

The EMode action currently uses a 20-second rollback window. The PPU activation contract itself remains bounded to 2..120 seconds.

Before Manager starts the transaction it requires:

- a mutable/durable runtime registry;
- registry lifecycle `commissioned`;
- no Manager-observed active Site execution;
- a current trusted fleet observation;
- canonical PPU identity from the current Plasma Gateway Endpoint;
- an available candidate Plasma Gateway Endpoint not already owned by another registered PPU.

The transaction is:

```text
requested
  -> desired_saved
  -> apply_requested
  -> reconnecting
  -> identity_verified
  -> activation_committed
  -> registry_reconciled
  -> completed
```

The execution sequence is:

```text
resolve old registry Plasma Gateway Endpoint
-> GET /api/node on old endpoint and capture immutable ppu_id
-> POST desired static network to old endpoint
-> derive candidate endpoint by replacing only the host/IP
   while preserving scheme and port
-> verify candidate endpoint is not owned by another registry entry
-> POST PPU activation on old endpoint
-> reconnect candidate endpoint
-> GET /api/node on candidate
-> require the same immutable ppu_id
-> POST activation commit on candidate
-> durably record activation_committed
-> compare-and-swap Manager registry endpoint old -> candidate
-> durably record registry_reconciled
-> completed
```

Example endpoint derivation:

```text
old endpoint:       http://192.168.10.10:18080
static IPv4 target: 192.168.10.21
candidate endpoint: http://192.168.10.21:18080
```

The Browser never supplies the candidate URL. This prevents a commissioning request from becoming arbitrary server-side request routing.

### Same-identity requirement

Reachability is insufficient evidence. The candidate endpoint must return the same canonical immutable `ppu_id` from `/api/node`.

If a different `ppu_id` appears at the candidate address:

```text
candidate_identity_mismatch
-> do not commit PPU activation
-> do not update Manager registry endpoint
-> wait for PPU rollback evidence
```

This rule prevents an address collision or wrong device from being silently adopted as the original PPU.

### Registry compare-and-swap

After PPU activation commit, Manager updates the registry only if the alias still points to the exact old endpoint captured when the transaction started.

```text
expected endpoint = old endpoint
new endpoint      = verified candidate endpoint
```

The update is rejected if another PPU already owns the candidate endpoint or if an operator/concurrent transaction changed the endpoint meanwhile. A committed PPU activation plus failed registry reconciliation becomes `recovery_required`; Manager does not overwrite newer registry state.

### Failure and rollback semantics

Failure before PPU activation scheduling records `failed` and leaves the registry unchanged.

Failure after activation scheduling but before confirmed commit enters:

```text
rollback_wait
  -> rolled_back
     or
  -> recovery_required
```

Manager polls the old endpoint for PPU rollback evidence while the PPU-side activation deadline remains authoritative. Manager never changes the registry endpoint before confirmed PPU commit.

If rollback cannot be confirmed, the transaction becomes `recovery_required` rather than claiming that the old or candidate endpoint is authoritative.

### Manager journal and restart recovery

The Manager network-commissioning journal is derived from `manager.registry_state_path` and stored beside it. It records transaction identity, request fingerprint, alias, old/candidate endpoints, PPU identity, desired revision, PPU activation ID, rollback deadline, state, and error evidence.

The journal intentionally does **not** persist the caller's `Authorization` header or bearer credential.

This creates a deliberate restart boundary:

- if `activation_committed` is already durable, Manager restart may safely finish Manager-local registry compare-and-swap reconciliation without another protected PPU command;
- if restart occurs before durable `activation_committed` evidence, Manager marks the transaction `recovery_required` and does not guess whether a protected PPU command succeeded;
- a `recovery_required` transaction blocks another commissioning attempt for that alias until network and registry state are reconciled deliberately.

Fully unattended recovery from every pre-commit Manager crash point would require a separate Manager-to-PPU service identity / credential-lifecycle architecture. This slice does not persist user credentials merely to achieve that behavior.

### Idempotency

The Browser supplies one Manager-level `Idempotency-Key`. Manager journals the request key and a fingerprint of the desired settings/rollback timeout. Reusing the same key with different input fails closed. Replaying an already completed identical transaction returns the existing completion rather than committing again.

Manager generates separate PPU command idempotency keys for desired-state write, activation apply, and commit. Those keys are derived from the Manager transaction identity.

## DHCP boundary

DHCP remains valid desired PPU state, but **automatic DHCP endpoint migration is not implemented**.

The missing primitive is deterministic candidate discovery/lease evidence bound to the same immutable PPU identity. Without that evidence, Manager cannot safely know what Plasma Gateway Endpoint to reconnect and commit.

Therefore `Commission Static Network` is available only for Static IPv4. DHCP remains **Save Desired Network** only.

## Phase 2 PPU activation API

Phase 2 adds a separate PPU activation resource; a desired-state write is never reinterpreted as an already-applied configuration.

```text
GET  /api/settings/ppu-network/activation
POST /api/settings/ppu-network/activation
POST /api/settings/ppu-network/activation/{activation_id}/commit
```

Apply request:

```json
{
  "action": "apply",
  "expected_revision": 2,
  "expected_ppu_id": "PPU-Z2-A38F21",
  "rollback_timeout_s": 10
}
```

The PPU rejects the request before network mutation when:

- another activation is active;
- `expected_revision` does not equal the current desired revision;
- `expected_ppu_id` does not equal the PPU identity reported by the local Plasma Server;
- the rollback timeout is outside the bounded contract;
- the privileged helper is unavailable.

A successful apply returns HTTP `202 Accepted` while the old Plasma Gateway Endpoint still exists. Actual mutation is deliberately delayed briefly after the ACK so the response can leave through the old network path.

The PPU transaction then follows:

```text
scheduled
-> applying
-> applied_waiting_commit
       | same ppu_id confirmed on new endpoint
       +-> committed
       |
       ` deadline / shutdown / failure
          -> rolling_back
          -> rolled_back
```

Commit request:

```json
{
  "expected_revision": 2,
  "expected_ppu_id": "PPU-Z2-A38F21"
}
```

The coordinator must reconnect through the candidate Plasma Gateway Endpoint and read canonical identity (`/api/node`) before sending commit. Reaching an IP address is not sufficient evidence; the endpoint must report the same immutable `ppu_id`.

While an activation is active, the desired settings resource is read-only. This prevents candidate drift between snapshot, apply, reconnect, and commit.

## Desired revision versus committed revision

`revision` and `committed_revision` have different meanings:

```text
revision             latest durable desired configuration
committed_revision   last activation explicitly committed after identity verification
```

Example:

```text
revision 2 -> apply 192.168.10.21 -> verify -> commit
committed_revision = 2

revision 3 -> apply 192.168.10.22 -> no commit -> timeout rollback
actual network returns to revision-2 state
revision remains 3
committed_revision remains 2
```

The PPU therefore exposes desired/actual drift rather than silently overwriting operator intent after rollback.

## Durable PPU activation journal and recovery

The PPU activation journal is:

```text
<output-root>/ppu-network-activation.json
```

It stores the activation ID, PPU identity, desired revision, candidate settings, previous actual-network snapshot, rollback deadline, state, committed revision, and recovery reason/error.

If the Plasma Gateway starts and finds an interrupted active transaction, it attempts to restore the saved previous snapshot before accepting that transaction as complete. Successful startup recovery is recorded as `rolled_back` with reason `startup_recovery`. If the helper cannot perform recovery, the transaction becomes `recovery_required`; the Plasma Gateway does not claim success.

Graceful Plasma Gateway shutdown also fails safe. In particular, shutdown during a helper `apply` does not race a premature restore against an in-flight mutation: the worker observes shutdown after `apply` returns and restores the previous snapshot. A helper that fails to return within the bounded shutdown wait leaves explicit `recovery_required` evidence.

## Privilege separation

The Plasma Gateway must not receive `CAP_NET_ADMIN`, execute `sudo`, or run arbitrary shell network commands.

Phase 2 uses a local Unix-domain socket helper contract with only three operations:

```text
snapshot
apply(settings)
restore(snapshot)
```

The Plasma Gateway owns admission, identity/revision checks, PPU transaction state, PPU journal, deadlines, commit, and rollback policy. The helper owns only the privileged OS mutation.

Manager owns cross-domain commissioning orchestration and registry reconciliation. It does not receive network-mutation privilege.

This boundary is deliberate. A future PYNQ-Z2 adapter may use NetworkManager, `systemd-networkd`, or another mechanism without changing the REST transaction semantics.

## Secure Plasma Gateway policy

When the secure Plasma Gateway boundary is active:

- read access uses `settings.read`;
- desired-state writes, activation, and commit use `settings.ppu_network.write`;
- the built-in `admin` role owns PPU network write permission;
- operator, engineer, viewer, and service roles do not receive this write permission by default;
- every state-changing PPU POST uses the existing durable `Idempotency-Key` command ledger.

Manager/BFF preserve the incoming authorization evidence in memory while orchestrating the transaction. Network commissioning intentionally does not introduce a parallel authorization model or persist the credential in the Manager journal.

## Phase 1 packaged ARMv7 acceptance

The Phase 1 regression runner remains:

```bash
source software/python/.venv/bin/activate
python scripts/ppu-network-phase1-acceptance.py
```

It builds the canonical `linux-armv7l` release, clean-extracts it, runs the packaged PPU under QEMU ARMv7, exercises desired-state validation/persistence, and proves that actual `eth0` does not change when no activation helper is configured.

Default report:

```text
.work/reports/ppu-network-phase1-acceptance.json
```

This regression remains important after Phase 2 because an installation without the privileged helper must preserve the original fail-closed behavior.

## Phase 2 packaged ARMv7 acceptance

The canonical Phase 2 one-command acceptance runner is:

```bash
source software/python/.venv/bin/activate
python scripts/ppu-network-phase2-acceptance.py
```

It performs:

```text
build + validate PPU runtime
-> build canonical linux-armv7l release
-> detached SHA-256 verification
-> clean extraction + runtime validation
-> ARMv7 QEMU/binfmt preflight
-> create isolated Docker bridge
-> start packaged PPU namespace with Docker-owned control IPv4 192.168.77.40 and no CAP_NET_ADMIN
-> start helper sidecar in the same network namespace with CAP_NET_ADMIN only
-> helper adds the PPU managed IPv4 192.168.77.10 on eth0
-> start independent coordinator probe
-> desired revision 2 = 192.168.77.21
-> apply and receive ACK on managed old endpoint 192.168.77.10
-> real isolated eth0 managed-address mutation .10 -> .21 while Docker control .40 remains untouched
-> reconnect .21 and verify same ppu_id
-> prove managed old endpoint .10 is removed
-> commit revision 2
-> prove .21 survives rollback deadline
-> desired revision 3 = 192.168.77.22
-> apply .21 -> .22 and deliberately omit commit
-> prove automatic timeout rollback .22 -> .21
-> prove desired revision remains 3 while committed revision remains 2
-> emit terminal summary + JSON evidence
```

The Docker control address is deliberately outside the property being tested. Docker/IPAM owns `.40`; the privileged helper owns only the managed PPU address `.10/.21/.22`. This prevents the test harness from asking Docker to relinquish its own control-plane address while still exercising real Linux IPv4 add/delete on the same `eth0` network namespace.

Default report:

```text
.work/reports/ppu-network-phase2-acceptance.json
```

A PASS proves the Phase 2 PPU transaction semantics, real static managed-IPv4 mutation inside the isolated ARMv7 lab namespace, privilege separation, reconnect, same-`ppu_id` verification, explicit commit, old-endpoint removal, and automatic rollback.

It does **not** prove:

- PYNQ-Z2 hardware;
- the final PYNQ-Z2 Linux network-manager backend;
- primary-address replacement under Docker IPAM;
- DHCP activation;
- production DNS/default-route mutation;
- boot-time network persistence;
- native Z2 Manager-to-PPU commissioning;
- PS-to-PL, Site I/O, target power, or IC programming.

The actual Z2 image must be inspected before selecting its persistent Linux backend. The REST transaction contract is intentionally independent of that choice.

## Validation environments

SWPC/QEMU ARMv7 is the software qualification environment for packaged PPU runtime and Phase 2 transaction behavior. The [Virtual PPU Network Lab](virtual-ppu-network-lab.md) adds the production Plasma Manager across a real isolated managed-IPv4 endpoint migration. Z2 remains the hardware/network-image qualification environment.

The acceptance hierarchy is therefore:

```text
unit / REST / security tests
-> Manager commissioning unit/REST/Web contract tests
-> packaged SWPC ARMv7 Phase 1 regression
-> packaged SWPC ARMv7 Phase 2 isolated network mutation
-> Virtual PPU + production Manager commissioning acceptance
-> PYNQ-Z2 backend inspection and adapter
-> Z2 native apply/reconnect/rollback acceptance
-> native Z2 Manager-owned commissioning acceptance
```
