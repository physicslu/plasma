# Static IPv4 Fault Injection

## Status and purpose

This document defines the current integration-host chaos acceptance for Manager-owned Static IPv4 commissioning.

The previous [Virtual PPU Network Lab](virtual-ppu-network-lab.md) proves the production Plasma Manager happy path across a real isolated managed-IPv4 migration. This fault-injection layer asks the opposite question: **when identity, reachability, the privileged helper, or the Manager process fails, does the control plane preserve authoritative registry truth and fail closed?**

The evidence stack is:

```text
PPU Phase 2 isolated activation / rollback
        ↓
Virtual PPU + production Manager happy path
        ↓
Static IPv4 fault injection / crash recovery
        ↓
future PYNQ-Z2 native network backend qualification
```

The lab does not redefine the production commissioning state machine. It drives the existing production Manager, Gateway, PPU activation journal, and runtime registry through deterministic integration-host faults.

## Canonical runner

```bash
source software/python/.venv/bin/activate
python scripts/static-ipv4-fault-injection-lab.py
```

Default outputs:

```text
.work/static-ipv4-fault-injection/
.work/reports/static-ipv4-fault-injection.json
```

CI can reuse an already clean-extracted and validated packaged PPU runtime:

```bash
python scripts/static-ipv4-fault-injection-lab.py \
  --runtime-dir /path/to/plasma-release/runtime
```

## Fresh-topology rule

Every fault scenario owns a new Docker bridge, two new packaged ARMv7 PPU processes, new helper sidecars, and a fresh Manager registry/commissioning journal.

```text
scenario N
  -> create isolated network
  -> start Virtual PPU A/B
  -> start production Manager or test-only crash launcher
  -> inject exactly one fault
  -> execute production commissioning transaction
  -> validate PPU journal + Manager journal + registry + endpoints
  -> verify host uplink unchanged
  -> destroy topology

scenario N+1 starts from zero
```

A scenario must not inherit a rollback, registry mutation, transaction ID, ARP state, or recovery marker from an earlier scenario.

## Privilege boundary

The production privilege rule remains unchanged:

```text
Plasma Manager      no CAP_NET_ADMIN
Plasma Gateway      no CAP_NET_ADMIN
fault helper        CAP_NET_ADMIN only
host uplink         never used as PPU mutation target
```

The chaos helper is `scripts/static-ipv4-fault-helper.py`. It is a test-only process mounted into the helper sidecar. The Gateway still sees only the existing Unix-socket operations:

```text
snapshot
apply(settings)
restore(snapshot)
```

The helper adds deterministic test behavior unavailable in production:

```text
normal
apply-error
apply-noop
apply-drop
restore-error
```

`apply-noop` reports the requested candidate without changing the managed address. It is used to expose a deterministic wrong-device candidate while keeping PPU A reachable for rollback.

`apply-drop` removes the old managed address and deliberately does not add the candidate. It creates a deterministic reconnect timeout while preserving a real Linux address-loss event.

These controls do not enter the packaged PPU artifact, Plasma Gateway API, or production Manager code.

## Scenario 1 — duplicate candidate ownership

Topology:

```text
Manager registry:
  ppu-a -> 192.168.78.10:18080
  ppu-b -> 192.168.78.21:18080

request:
  commission ppu-a -> 192.168.78.21
```

The candidate endpoint is already owned by another Manager registry entry. The production Manager must reject the candidate before starting PPU activation.

Required evidence:

- commissioning terminal state is `failed`;
- PPU A activation remains `idle`;
- PPU A registry endpoint remains the old endpoint;
- PPU B registry endpoint remains the candidate endpoint;
- no false candidate adoption occurs.

## Scenario 2 — wrong immutable `ppu_id`

Topology:

```text
Manager registry:
  ppu-a -> 192.168.78.10
  ppu-b -> 192.168.78.11

real isolated network:
  PPU B also answers 192.168.78.21

PPU A fault helper:
  apply-noop
```

The registry does not know that `.21` is occupied. Manager therefore reaches the candidate identity check. The candidate is a real second packaged PPU and returns `virtual-ppu-b`, not PPU A's immutable identity.

Required production behavior:

```text
candidate_identity_mismatch
  -> no Manager commit
  -> rollback_wait
  -> PPU rollback confirmation
  -> Manager rolled_back
```

The Manager registry must remain on PPU A's old endpoint.

## Scenario 3 — reconnect timeout

PPU A's test helper performs `apply-drop`:

```text
old managed IPv4 removed
candidate managed IPv4 not installed
```

The Manager cannot reconnect to the candidate before the PPU rollback deadline.

Required evidence:

```text
candidate_endpoint_unreachable
  -> rollback_wait
  -> PPU restores old IPv4
  -> Manager rolled_back
  -> registry remains old endpoint
```

The test therefore proves a real Linux address-loss and recovery path rather than merely mocking an HTTP timeout.

## Scenario 4 — privileged helper apply failure

The helper returns an explicit error from `apply` while `restore` remains healthy.

The production PPU controller must fail safe:

```text
apply error
  -> rollback previous snapshot
  -> PPU rolled_back
```

Required evidence:

- PPU activation reason is `apply_failed`;
- the injected helper error remains observable in the PPU activation journal/status;
- Manager never reports commissioning success;
- Manager registry remains on the old endpoint.

## Scenario 5 — Manager crash before durable commit boundary

The first Manager process is started through:

```text
scripts/manager-network-commissioning-crash-injector.py
```

The launcher monkey-patches only its own test process. It calls the real `NetworkCommissioningStore.put()` first. Only after the real journal write has completed does it issue `SIGKILL` when the record reaches:

```text
identity_verified
```

The restart uses the ordinary unmodified production Manager.

Expected restart semantics:

```text
journal = identity_verified
Manager process disappears
        ↓
production Manager restart
        ↓
recovery_required
error = manager_restart_before_commit_boundary
```

The Manager must not guess whether the protected PPU commit happened. Registry mutation is refused. After PPU automatic rollback restores the old endpoint and trusted fleet observation returns, a new commissioning request remains blocked by the persisted `recovery_required` transaction until deliberate reconciliation occurs.

## Scenario 6 — Manager crash after PPU commit, before registry CAS

The crash launcher terminates only after the real Manager journal durably records:

```text
activation_committed
```

At this boundary the PPU already reports `committed`, but Manager registry compare-and-swap has not yet completed.

Production restart is allowed to finish only Manager-local reconciliation:

```text
activation_committed
  -> production Manager restart
  -> compare-and-swap registry old -> candidate
  -> registry_reconciled
  -> completed
```

The PPU activation journal is SHA-256 fingerprinted before and after Manager restart. It must remain byte-for-byte unchanged. This is integration evidence that post-commit restart recovery does not need another PPU network mutation/commit operation.

## `recovery_required` is an evidence result, not a synthetic seventh case

`recovery_required` is intentionally exercised as the real outcome of the pre-commit Manager crash. It is not fabricated as a standalone state-setting test.

This preserves the state machine's meaning: `recovery_required` exists because the system has insufficient durable evidence to safely choose an endpoint, not because a test directly assigned the state.

## CI placement

The `PPU release artifact` workflow runs the network layers in this order:

```text
Phase 1 packaged desired-state acceptance
        ↓
Phase 2 packaged activation / rollback acceptance
        ↓
Virtual PPU + production Manager happy path
        ↓
Static IPv4 fault injection / crash recovery
```

The fault lab reuses the already clean-extracted packaged ARMv7 PPU runtime. It does not rebuild a different DUT artifact.

## Evidence boundary

A PASS proves, on a Linux integration host:

- production Manager duplicate-candidate exclusion remains fail closed;
- wrong-device candidate identity cannot be adopted as the original PPU;
- candidate reconnect timeout converges through automatic PPU rollback;
- privileged helper apply failure does not create false commissioning success;
- pre-commit Manager crash becomes durable `recovery_required` without registry corruption;
- post-commit Manager crash can finish Manager-local registry reconciliation after restart;
- Manager and Gateway remain unprivileged;
- only the helper sidecar receives network-mutation capability;
- the host uplink remains unchanged;
- the DUT is the packaged ARMv7 PPU runtime used by the release workflow.

A PASS does **not** prove:

- PYNQ-Z2 MAC/PHY/carrier/switch behavior;
- the final PYNQ-Z2 Linux network-manager backend;
- DHCP lease discovery or endpoint migration;
- production DNS or Default Gateway mutation;
- boot-time network persistence;
- physical cable/switch fault behavior;
- PS-to-PL communication;
- FPGA Site I/O or timing;
- target power control;
- real IC programming.

Those remain separate acceptance layers.
