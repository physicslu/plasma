# PLASMA Phase 2A.2 — Host-only Configuration Safety Contract

Status: **Gate 1 implementation candidate**. M1 Architecture Freeze **NO-GO**.
This does not amend ADR-0003 or the approved limitations of PR #982/#988.

## Model boundary

The standalone `configuration_safety_contract.py` accepts only immutable
synthetic evidence pinned to the same boot, runtime source, resource/DT identity,
old/candidate SHA-256 image, generation and owner epoch. Source commits must
use canonical lower-case 40/64-hex digests; images require lower-case 64-hex
SHA-256 digests. Shape and identity matching do **not** verify actual bytes. No real FPGA loading, IO, sysfs,
driver operation, bridge control, Kernel/DMA arbitration or hardware credential
exists in this module. Passing the model returns an explicitly Host-only receipt
with `grants_hardware_authority=False`.

It intentionally does **not** integrate its synthetic receipt into a physical
driver or confer an extra READY state on Phase 2A.1 ConfigurationOwner.

## Required transition gates (all exact, ordered and fail-closed)

1. **Ownership:** admissions sealed; all managed leases retired; complete
   external process/VMA inventory; no retained maps, Kernel, DMA or unmanaged
   MMIO owners. Existing cooperative flock alone proves none of these.
2. **Isolation:** safe DUT/external IO; **drained** in-flight AXI operations;
   verified PS–PL isolation; confirmed independent recovery path.
   A Python lease count is *not* proof of AXI drain.
3. **Retirement:** previous mapping retired; no live handles or pending IO.
4. **Verification:** exact image, resource topology, independent runtime health,
   recovery receipt. A new generation must not be inferred from a successful
   model test or a simulated image label.

Any mismatched/stale pin, unknown/false/non-boolean evidence, or non-synthetic
kind rejects the transition. Host-only validation does not measure any of these
conditions on hardware; the booleans are fixture assumptions, not attestation.

## Explicit unresolved real hardware blockers

- Precise Z2 Kernel source/patch identity and live Device Tree/UIO ownership.
- Kernel-enforced exclusion of all processes, persistent VMAs, devices and DMA.
- Demonstrable drain/isolation of PS–PL AXI transactions with independent
  fault containment for SIGBUS, hung accesses and interrupted reloads.
- Real RTL Hardware ABI v1 and image provenance validation.
- Safe IO/reset/power state and operator-observed external recovery.
- Fresh ARMv7 HIL checks and independent SSH/HTTP recovery observation.

**NO-GO:** no real /dev/uio, /dev/mem, FPGA Manager, unbind/rebind,
bitstream load, Z2, USB Hub, logic analyzer, DUT operations, production
deployment or PR #972 changes. A separate owner-approved hardware Gate 1
and its technical evidence are required before any physical HIL.

## Validation

`python3 -m pytest -q software/python/tests/test_configuration_safety_contract_host.py software/python/tests/test_configuration_owner_host.py software/python/tests/test_uio_backend_host.py software/python/tests/test_linux_mmio.py`

This is a reviewable safety-model increment, not a hardware implementation or
a claim of M1 architecture qualification.
