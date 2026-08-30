# Device Catalog Phase 3.3 — ICPN Coverage Expansion

## Objective

Phase 3.3 changes the optimization target from framework validation to admitted exact-ICPN coverage growth. The Phase 3.0 generic evidence/pipeline/admission core remains unchanged; family adapters absorb manufacturer/family semantics.

## Batch model

A coverage batch has two logically separate roles:

1. **control target** — reacquire an already admitted base device to detect source/candidate drift;
2. **admission targets** — new base devices whose exact commercial ICPNs may enter canonical data after a clean plan.

The control must not be re-admitted under a new evidence ID. Canonical rows intentionally bind their original evidence reference, so a later control acquisition would otherwise look like a semantic conflict. This is a provenance invariant, not a reason to weaken canonical equality.

## Batch 1

Control:

- STM32F401CC — 5 exact ICPNs, drift guard only.

New admission bases:

- STM32F401CB — 4 exact ICPNs
- STM32F407VE — 2 exact ICPNs
- STM32F407ZG — 3 exact ICPNs
- STM32F411CC — 4 exact ICPNs
- STM32F429ZG — 3 exact ICPNs

Live headed-Chromium result:

- targets: 6/6 acquired
- exact candidates: 21/21 baseline match
- candidate drift: 0
- OpenOCD mapping: 6/6 base devices and all exact candidates deterministically resolve to `tcl/target/stm32f4x.cfg`
- admission scope: 16 new exact ICPNs
- live plan: 16 admit, 0 already-present, 0 manual-review, 0 reject, 0 conflict

Coverage transition:

- STM32F4 canonical: 18 → 34 exact ICPNs
- ICPN v1 production view: 93 → 109 exact ICPNs
- STM32F1 remains 75

## Evidence and replay

The immutable retained package records the live run executed at Git SHA `db7f09010c340a4b9c08fd587ff4107d9e475d3f`.

Final CI is offline and fail-closed. It must:

1. validate retained evidence byte integrity and deterministic reevaluation;
2. reconstruct the exact live admission plan from the 18-row prewrite canonical state;
3. match the live admission-plan SHA-256;
4. run the generic writer 18 → 34;
5. run the same writer again and obtain `no_op`;
6. require byte-identical output to the checked-in canonical CSV;
7. validate the production manifest/runtime view as 109 exact ICPNs.

The one-time online acquisition workflow is removed after evidence retention.

## Architecture result

Batch 1 requires no change to:

- `device_catalog_evidence_framework.py`
- `device_catalog_pipeline_framework.py`
- `device_catalog_admission_framework.py`
- `stm32f4_admission_policy.py`

The only family-adapter extension is explicit admission-base selection. Full retained evidence is still validated before filtering, so a control or non-admitted target cannot silently bypass evidence validation.

## Next coverage work

Further batches should repeat this pattern and increase coverage only where the existing family policy can resolve exact commercial identity, metadata, and OpenOCD mapping deterministically. Unsupported package or ordering semantics belong in a manual-review backlog until real evidence justifies a policy extension.

Coverage growth does not imply PPU or Socket verification. Those remain separate product evidence states.
