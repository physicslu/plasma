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
Repeatability + privilege / ownership parity
        ↓
Persistent integration-host acceptance
        ↓
future PYNQ-Z2 native network backend qualification
```

The lab does not redefine the production commissioning state machine. It drives the existing production Manager, Gateway, PPU activation journal, and runtime registry through deterministic integration-host faults.

## Canonical runners

For direct fault-lab debugging or one-shot acceptance:

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

The P0 CI gate is intentionally stricter than the one-shot runner:

```bash
python scripts/static-ipv4-fault-injection-repeatability.py \
  --runtime-dir /path/to/plasma-release/runtime \
  --work-dir /same/work/directory \
  --report /path/to/repeatability.json
```

It runs the complete six-scenario fault lab **twice in the exact same work directory**. The wrapper performs no cleanup of that directory between runs. The fault lab itself must make disposable root-owned residue removable without `sudo`, then the normal non-root host process removes the stale workspace and starts the next run.

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

The repeatability gate tests a different property: while every scenario topology is fresh, the **host work directory is deliberately reused across complete lab executions**. This distinguishes scenario isolation from persistent-workspace portability.

## Privilege boundary

The production privilege rule remains unchanged:

```text
Plasma Manager      no CAP_NET_ADMIN
Plasma Gateway      no CAP_NET_ADMIN
fault helper        CAP_NET_ADMIN only
host verifier       non-root
private PPU journal root:root 0600
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

## Verifier independence and private evidence contract

The production-style PPU activation journal is private evidence:

```text
gateway-output/ppu-network-activation.json
owner = root:root
mode  = 0600
```

The host-side acceptance process is not allowed to make that file easier to read. The governing rule is:

> A test harness MUST NOT relax a production security property in order to make acceptance evidence observable.

`scripts/private-ppu-evidence-verifier.py` is therefore separate from the DUT, fault helper, and Manager crash injector. It must run as a non-root host user and fails unless the canonical journal is a regular non-symlink file with exactly `root:root 0600` ownership and mode.

The verifier does not `chmod`, use `sudo`, search recursively, or import production Manager/Gateway code. SHA-256 is read through a disposable reader container with:

```text
bind mount        read-only
network           none
capabilities      none
no-new-privileges true
container reader  uid 0 only for the private bind-mounted file
host verifier     non-root
```

This is an explicit producer/verifier separation:

```text
DUT / producer
  -> creates private root:root 0600 journal

fault injector
  -> creates deterministic failure condition only

independent verifier
  -> checks path + owner + mode
  -> hashes through locked read-only boundary
  -> never modifies the evidence
```

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

The GitHub-hosted `PPU release artifact` workflow runs the network layers in this order:

```text
Phase 1 packaged desired-state acceptance
        ↓
Phase 2 packaged activation / rollback acceptance
        ↓
Virtual PPU + production Manager happy path
        ↓
Static IPv4 repeatability + privilege / ownership parity
        ├─ complete six-scenario lab, run 1
        ├─ independent private-evidence verification
        ├─ same work directory reused
        ├─ complete six-scenario lab, run 2
        └─ independent private-evidence verification
```

The repeatability gate reuses the already clean-extracted packaged ARMv7 PPU runtime. It does not rebuild a different DUT artifact between the two executions.

A GitHub-hosted PASS still does **not** qualify a persistent integration host. Ephemeral runner semantics do not prove behavior across jobs, machine lifetime, local Docker configuration, filesystem history, or accumulated ownership residue.

## Persistent integration-host acceptance

`.github/workflows/persistent-integration-host.yml` defines the dedicated persistent-host path. The security and enrollment contract is defined in [Persistent Integration Host Qualification](persistent-integration-host-qualification.md).

It is intentionally `workflow_dispatch` only, main-only, and requires a pre-enrolled self-hosted runner with labels:

```text
self-hosted
linux
x64
plasma-integration
```

The workflow:

- rejects non-main dispatch before scheduling work onto the self-hosted runner;
- pins checkout and packaged evidence to the exact dispatch SHA;
- requires the host runner user to be non-root;
- runs a fail-closed host preflight, including rootful-Docker, persistent-root, ARMv7/QEMU, and host-network evidence;
- captures the exact Git SHA, uid/gid, kernel, Docker server/security options, Node/Python versions, OS release, and default-route signature;
- runs canonical source/configuration validation;
- verifies ARMv7 execution is already provisioned rather than mutating host binfmt configuration in the job;
- builds and clean-extracts the packaged PPU runtime at the exact checked-out revision;
- uses a persistent work root outside the Git checkout and `RUNNER_TEMP`;
- executes the same-workdir repeatability and privilege/ownership parity gate;
- uploads the preflight and repeatability evidence reports;
- performs no production deployment, service restart, SSH operation, or Z2 access.

This workflow is a **persistent-host post-merge qualification path**, not proof that a required PR gate is already operational. Until an actual persistent runner is enrolled and a successful main-only execution is observed, the repository must not describe persistent-host qualification as operational evidence.

Likewise, a self-hosted Linux PASS remains below PYNQ-Z2 native/HIL qualification. It does not become hardware evidence merely because the machine is persistent.

## Evidence boundary

A hosted repeatability PASS proves, on that Linux execution environment:

- production Manager duplicate-candidate exclusion remains fail closed;
- wrong-device candidate identity cannot be adopted as the original PPU;
- candidate reconnect timeout converges through automatic PPU rollback;
- privileged helper apply failure does not create false commissioning success;
- pre-commit Manager crash becomes durable `recovery_required` without registry corruption;
- post-commit Manager crash can finish Manager-local registry reconciliation after restart;
- Manager and Gateway remain unprivileged;
- only the helper sidecar receives network-mutation capability;
- the host uplink remains unchanged;
- the DUT is the packaged ARMv7 PPU runtime used by the release workflow;
- the complete fault lab succeeds twice in the same work directory without manual cleanup or `sudo`;
- the host verifier is non-root;
- the canonical private PPU activation journal remains `root:root 0600`;
- the verifier observes that journal without permission widening or recursive evidence discovery.

A persistent integration-host PASS additionally proves those same contracts on the enrolled persistent runner and its retained workspace/environment. It still does **not** prove:

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