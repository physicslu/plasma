# PPU Site Desired Runtime Activation

Status: P3 software/deployment contract. Physical Z2, PL, electrical, socket, DUT-power, and real-IC behavior remain separate qualification stages.

## Problem

P0/P1/P2 separate Browser Draft, persisted Desired configuration, and observed Runtime. Saving a Site changes canonical PPU configuration but the running Plasma Server continues with the configuration loaded at process start. A simple browser-side `idle -> restart` sequence is unsafe because a Job can be admitted after the idle observation but before the service restart.

P3 closes that race at the execution authority.

```text
Browser
  -> Save Desired
  -> restart_required
  -> Activate Desired Configuration
       |
       v
Plasma Gateway
  -> validate aggregate Desired revision + ppu_id
       |
       v
bounded runtime-activation helper
       |
       +-> Plasma Server local Unix control socket
       |     -> acquire quiesce under SiteManager execution lock
       |     -> reject if execution lease is active
       |     -> block new Job admission while quiesced
       |
       +-> restart exactly plasma-server.service
       |
       v
Plasma Server reloads canonical PPU configuration
       |
       v
Gateway verifies same ppu_id + unchanged aggregate Desired revision
       |
       v
Desired / Runtime reconciliation
```

## Authoritative quiesce

The SiteManager execution lock is the safety boundary. Runtime activation and Job reservation consult the same lock:

- quiesce acquisition fails while any execution lease is active;
- once quiesce is acquired, new Job reservation fails with `PPU_BUSY`;
- the quiesce lease has a bounded TTL and expires automatically if the activation client/helper fails;
- no Browser or Manager observation is treated as execution authority.

This closes the check-then-restart TOCTOU window without changing Plasma Protocol v3.3.

## Privilege boundary

The Plasma Gateway remains unprivileged. It talks to a local Unix-socket helper. The helper accepts one exact operation only:

```text
restart plasma-server.service
```

The helper does not accept a service name, shell command, executable path, unit action, or arbitrary `systemctl` arguments from the request. It first obtains an authoritative quiesce lease from the running Plasma Server and verifies the expected PPU identity before restarting the service.

## Activation identity

P3 derives a deterministic PPU-level Desired Runtime revision from the sorted set of:

```text
site_id + per-Site desired_revision
```

The Browser sends both the aggregate revision and expected `ppu_id`. The Gateway rejects a stale activation before restart. After restart it verifies:

1. the same `ppu_id` is running;
2. the aggregate Desired revision did not change during activation;
3. Runtime reconciles to `in_sync`, or to `partially_observable` only where Protocol v3.3 intentionally hides dormant bindings for disabled Sites.

The aggregate revision is activation concurrency identity. It is not a release version, hardware qualification, or proof of electrical behavior.

## UI contract

Runtime activation is a PPU-level action because restarting Plasma Server affects every Site in that PPU. The Engineering PPU/Site page therefore exposes one `Activate Desired Configuration` control rather than a restart button per Site.

The UI must make these facts visible:

- activation applies saved Desired state only; unsaved Browser Drafts are not included;
- all Sites are affected by the Plasma Server restart;
- active execution blocks activation;
- stale Desired revision or PPU identity fails closed;
- success is reported only after post-restart Runtime reconciliation.

## Upgrade preservation correction

P3 also closes a prerequisite P2 correctness defect: a successful software upgrade must not regenerate canonical PPU configuration over an existing `/etc/plasma/ppu.yaml`. The existing canonical file is mutable product state and must survive release upgrades. First installation may create the initial configuration; later upgrades preserve persisted Site Desired content.

This is required for runtime activation to have meaningful semantics. An activation feature layered over an upgrade path that erases Desired state would be internally inconsistent.

## Non-goals

P3 does not introduce:

- hot reload of Site configuration;
- a Plasma Protocol v3.3 extension;
- WebSocket or SSE;
- arbitrary remote service restart;
- generic Manager proxying;
- PL/FPGA access;
- target voltage, power, pinmux, or socket control;
- real IC programming qualification;
- physical Z2 deployment as part of software CI.

Passing software, packaging, Mock, and CI checks is not physical-hardware acceptance.
