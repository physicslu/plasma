# PPU Network Configuration

## Purpose

This document defines the PPU-owned network configuration contract used by the `PPU / SITE Configuration` commissioning workflow.

The ownership boundary is:

```text
Control Console / Manager
        |
        | commissioning orchestration / reconnect
        v
PPU Web REST Gateway (unprivileged)
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

PPU network configuration is separate from Gateway communication policy:

```text
/api/settings/gateway       Gateway-to-PPU timeout/retry policy
/api/settings/ppu-network   this PPU's desired Linux eth0 configuration
```

The two resources must not be merged merely because both contain the word "gateway" in operator terminology.

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

A successful desired-state POST means the configuration was validated and durably stored. It does not by itself mean that `eth0`, routes, DNS, DHCP client state, or the current PPU endpoint changed.

## Desired-state validation and persistence

Static mode requires:

- a valid IPv4 address;
- `prefix_length` in the range `1..32`;
- no network/broadcast address for prefixes where those addresses are reserved;
- an optional gateway on the configured subnet and different from the PPU address;
- at most three unique IPv4 DNS server addresses.

DHCP mode rejects static address, prefix, gateway, and DNS values. Unknown and missing POST fields are rejected rather than silently ignored.

The desired-state persistence file is:

```text
<output-root>/ppu-network-settings.yaml
```

Updates use temporary-file write, flush, `fsync`, and atomic replacement. The in-memory desired state changes only after persistence succeeds. An invalid existing persistence file fails closed during Gateway startup.

## Control Station desired-state integration

The EMode `PPU / SITE Configuration` surface can read and persist the selected PPU's desired network state through the existing Manager-owned control path:

```text
Control Console
  -> same-origin Manager BFF
  -> Manager alias-scoped allowlisted relay
  -> selected PPU Gateway
  -> GET/POST /api/settings/ppu-network
```

The Browser supplies the selected Manager registry alias, not a destination URL. The Manager resolves the registered PPU endpoint and remains the routing owner. The current relay exposes only the exact desired-state resource; the Browser does not receive an arbitrary Manager reverse-proxy capability.

A desired-state write through this surface requires the PPU registry lifecycle to be `commissioned` (`Validate & Enable` completed). The Console also disables the edit while it has evidence of active Site execution or an active network activation transaction. The PPU Gateway remains the authoritative validator and persistence owner.

The panel displays:

- fixed interface `eth0`;
- desired revision and mode;
- static IPv4 fields when applicable;
- activation support/state;
- last committed activation revision when available.

The operator action is deliberately named **Save Desired Network**. It means only:

```text
validate desired values
-> persist PPU-owned desired settings
-> return new desired revision
```

It does **not** mean:

```text
mutate Linux eth0
change the Manager registry endpoint
prove candidate reachability
commit an activation
```

The Browser intentionally does not call `/api/settings/ppu-network/activation` directly. A safe endpoint migration crosses two durable ownership domains — PPU network state and Manager registry endpoint state — and must therefore be owned by a Manager commissioning transaction rather than a sequence of loosely coupled Browser requests.

The next commissioning gate is a Manager-owned static IPv4 transaction:

```text
persist desired static network
-> schedule PPU activation on old endpoint
-> reconnect to deterministic candidate endpoint
-> read /api/node and verify the same immutable ppu_id
-> commit PPU activation
-> reconcile the Manager registry endpoint durably
```

Failure before commit must leave explicit rollback/recovery evidence and must not silently repoint the Manager registry. DHCP remains valid as PPU desired state, but automatic DHCP endpoint migration is not claimed until Manager has a deterministic lease/discovery and same-identity reconnect contract.

## Phase 2 activation API

Phase 2 adds a separate activation resource; a desired-state write is never reinterpreted as an already-applied configuration.

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

A successful apply returns HTTP `202 Accepted` while the old endpoint still exists. Actual mutation is deliberately delayed briefly after the ACK so the response can leave through the old network path.

The transaction then follows:

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

The coordinator must reconnect through the candidate endpoint and read canonical identity (normally `/api/node`) before sending commit. Reaching an IP address is not sufficient evidence; the endpoint must report the same immutable `ppu_id`.

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

## Durable activation journal and recovery

The activation journal is:

```text
<output-root>/ppu-network-activation.json
```

It stores the activation ID, PPU identity, desired revision, candidate settings, previous actual-network snapshot, rollback deadline, state, committed revision, and recovery reason/error.

If the Gateway starts and finds an interrupted active transaction, it attempts to restore the saved previous snapshot before accepting that transaction as complete. Successful startup recovery is recorded as `rolled_back` with reason `startup_recovery`. If the helper cannot perform recovery, the transaction becomes `recovery_required`; the Gateway does not claim success.

Graceful Gateway shutdown also fails safe. In particular, shutdown during a helper `apply` does not race a premature restore against an in-flight mutation: the worker observes shutdown after `apply` returns and restores the previous snapshot. A helper that fails to return within the bounded shutdown wait leaves explicit `recovery_required` evidence.

## Privilege separation

The Web REST Gateway must not receive `CAP_NET_ADMIN`, execute `sudo`, or run arbitrary shell network commands.

Phase 2 uses a local Unix-domain socket helper contract with only three operations:

```text
snapshot
apply(settings)
restore(snapshot)
```

The Gateway owns admission, identity/revision checks, transaction state, journal, deadlines, commit, and rollback policy. The helper owns only the privileged OS mutation.

This boundary is deliberate. A future PYNQ-Z2 adapter may use NetworkManager, `systemd-networkd`, or another mechanism without changing the REST transaction semantics.

## Secure Gateway policy

When the secure Gateway boundary is active:

- read access uses `settings.read`;
- desired-state writes, activation, and commit use `settings.ppu_network.write`;
- the built-in `admin` role owns PPU network write permission;
- operator, engineer, viewer, and service roles do not receive this write permission by default;
- every state-changing POST uses the existing durable `Idempotency-Key` command ledger.

Network activation intentionally does not introduce a parallel authorization model.

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

A PASS proves the Phase 2 transaction semantics, real static managed-IPv4 mutation inside the isolated ARMv7 lab namespace, privilege separation, reconnect, same-`ppu_id` verification, explicit commit, old-endpoint removal, and automatic rollback.

It does **not** prove:

- PYNQ-Z2 hardware;
- the final PYNQ-Z2 Linux network-manager backend;
- primary-address replacement under Docker IPAM;
- DHCP activation;
- production DNS/default-route mutation;
- boot-time network persistence;
- production Manager integration;
- PS-to-PL, Site I/O, target power, or IC programming.

The actual Z2 image must be inspected before selecting its persistent Linux backend. The REST transaction contract is intentionally independent of that choice.

## Validation environments

SWPC/QEMU ARMv7 is the software qualification environment for packaged runtime and Phase 2 transaction behavior. Z2 remains the hardware/network-image qualification environment.

The acceptance hierarchy is therefore:

```text
unit / REST / security tests
-> packaged SWPC ARMv7 Phase 1 regression
-> packaged SWPC ARMv7 Phase 2 isolated network mutation
-> PYNQ-Z2 backend inspection and adapter
-> Z2 native apply/reconnect/rollback acceptance
-> commissioning UI / Manager orchestration integration
```
