# PLASMA Phase 2A.3 — Configuration Owner Safety Contract Interlock

**Gate 1 implementation / HOST-ONLY. M1 Architecture Freeze = NO-GO.**
This is an integration of the merged Phase 2A.1 ConfigurationOwner (PR #988)
with the Phase 2A.2 synthetic Configuration Safety Contract (PR #991).
It is not a live FPGA loader, hardware acceptance, or a production authorization.

## Enforced model sequence

The existing `ConfigurationOwner` remains the sole coordinator of one
regular-file-only UIOBackend and its managed Sites. Phase 2A.3 adds mandatory,
per-phase, exact `ConfigurationPin` / evidence checks to the transition:

1. `READY → QUIESCE`: `begin_quiesce(pin=...)` seals admission **before**
   snapshotting any evidence; the immutable pin must match Owner boot,
   resource, source commit, mapping generation and owner epoch. Existing
   no-pin quiesce calls are retained for early negative tests only; they
   **cannot complete** a configuration transaction.
2. `OWNERSHIP_AUDIT → SAFE_IO`: existing `HostAudit` plus
   `OwnershipEvidence` (no Sites, external VMA/Kernel/DMA/owner assumptions).
3. `SAFE_IO → RELEASE`: existing `HostSafety` plus
   `IsolationEvidence`, including synthetic AXI-drained and independent
   recovery claims. No lease count can establish physical AXI drain.
4. `RELEASE → MODEL_LOAD`: host UIO regular-file mapping must retire
   successfully; `confirm_synthetic_retirement(RetirementEvidence)` must
   independently reject missing/false/unknown test claims **before** a model
   image label can be recorded.
5. `MODEL_LOAD → VERIFY`: record a string label in RAM only, with caller's
   exact candidate SHA-256 claim matching the pre-bound pin.
6. `VERIFY → NEW_MAPPING_GENERATION`: existing `HostVerification` plus
   `VerificationEvidence`; all four phase-specific records are passed
   through Phase 2A.2 `validate_synthetic_transition`.
7. `NEW_MAPPING_GENERATION → IDLE`: requires one exact,
   host-only `SyntheticTransitionReceipt`, no retained mapping/lease and
   same boot/source/resource/owner epoch and old generation. Receipt is
   consumed and cleared. A newly created regular-file backend must explicitly
   attach with the incremented generation before `READY` is restored.

Out-of-order method calls are rejected by the existing state guard without
advancing the transition. Missing or rejected stage evidence, foreign owner
epoch, stale generation, false/unknown claims, candidate digest mismatch,
or inconsistent receipts poison the active transaction as terminal `FAULT`;
none can publish a generation. There is no automatic retry, restore,
rebind or FPGA load.
The Owner's RLock serializes gate submission and Site admission.

**Claim limits:** Neither HostAudit nor Phase 2A.2 booleans are hardware
observations. SHA shape checks are not hash verification of image bytes;
the candidate label is not an independently authenticated image identity.
The `SyntheticTransitionReceipt` is not cryptographically authenticated,
is not a privilege token, and `grants_hardware_authority=False`.
The Python cooperative `flock` cannot exclude Kernel consumers, DMA,
unmanaged processes or other MMIO mappings.

## Validation / Gate limits

Dedicated GitHub Actions job runs the **complete Host-only model regression**:

```bash
PYTHONPATH=software/python python3 -m pytest -q \
  software/python/tests/test_configuration_owner_host.py \
  software/python/tests/test_configuration_safety_contract_host.py \
  software/python/tests/test_uio_backend_host.py \
  software/python/tests/test_linux_mmio.py
```

Negative scenarios cover missing stage data, per-field rejection, foreign
epoch and candidate identity, map-retirement failure, stale/forged receipt,
and blocked generation increments. Other existing UIO/MMIO regressions remain.

**NO-GO:** real `/dev/uio*`, `/dev/mem`, FPGA Manager, driver
unbind/rebind, AXI Bridge, DUT, Z2/USB Hub/LA, hardware bitstream loading,
live HIL-B/C, service/deployment modifications or PR #972 changes.
No merge without separate owner Gate 2 authorization.
