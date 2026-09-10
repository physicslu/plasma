# PPU Bootstrap and Console-managed Deployment

Status: Phase 1 foundation under implementation.

## Responsibility boundary

```text
Control Console / Manager
        |
        | desired state + policy
        v
PPU Bootstrap
        |
        | verify / stage / activate / rollback / recovery
        v
Plasma Runtime
        |
        | programming execution
        v
FPGA / Sites
```

The Bootstrap is independent from the Plasma Runtime it manages. A failed or absent Plasma Server/Gateway must not remove the recovery control path.

## Lifecycle contract

The initial software lifecycle states are:

```text
bootstrap_ready
runtime_absent
runtime_staged
runtime_activating
runtime_active
runtime_failed
runtime_rollback
recovery_required
```

The target deployment transaction is:

```text
receive -> verify -> stage -> activate -> health-check -> commit
                                             |
                                             +-> rollback on failure
```

The Console owns desired state. The Bootstrap owns target mutation and rollback. The Plasma Runtime owns programming execution.

## FPGA lifecycle extension point

This project reserves semantic metadata only. It does not implement bitstream deployment.

```text
hardware_revision
pl_version
pl_compatibility
pl_qualification
capabilities.fpga_update = false
```

No low-level FPGA loading mechanism, physical address, driver API, Site power, target voltage, or IC programming action is part of this contract.

## Evidence boundaries

- CI: Bootstrap/domain/API/state-machine correctness.
- Render/Playwright: Console -> BFF -> Manager -> Bootstrap operator workflow.
- Real PYNQ-Z2 HIL: filesystem/systemd/reboot/install/upgrade/rollback appliance behavior.

A CI or Render PASS must not be reported as real-PUU hardware qualification.
