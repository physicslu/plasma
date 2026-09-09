# STM32F3 Phase 4.4D Admission Plan

Status: deterministic admission planning complete; Production publication not applied.

## Inputs

Phase 4.4D requires the closed Phase 4.4C policy baseline and replays the
retained Phase 4.4B manufacturer evidence and current OpenOCD mapping catalog.
The guarded prestate is:

- STM32F3 canonical rows: 0 / dataset absent
- Production exact ICPNs: 492
- Production Base Devices: 169
- Production families: STM32F1=75, STM32F2=33, STM32F4=384

Any non-empty STM32F3 canonical prestate or changed Production/policy binding
fails closed.

## Deterministic result

The offline proposal run on GitHub Actions produced:

- candidate count: 10
- admit: 10
- already present: 0
- manual review: 0
- reject: 0
- conflicts: 0
- lifecycle exclusions: 0

Admission-plan SHA-256:

`d8cdab4d4c8f4fbecdc7fbf58ca7c9b58c8089389f5c8c36f0c7b7cd067b1495`

A sandbox header-only canonical dataset was then passed to the generic admission
writer. The first application wrote exactly 10 rows; the second application was
an explicit `no_op`.

Expected 10-row canonical file SHA-256:

`c371b7a1c3b271afb9c8c823a4d12071be57da1aa11d138b59d39911489e1ee8`

The temporary proposal workflow was removed after these bindings were measured.
Permanent CI retains the admission planner and sandbox/idempotency regressions.

## Governance boundary

This phase does not publish the generated CSV and does not modify the Production
manifest. The following remain false/not claimed:

- Production write applied
- programming algorithm equivalence
- runtime programming support
- full STM32F3 surface coverage

A separate controlled publication transaction is required before STM32F3 can be
counted in Production. If all ten planned rows are published without other
catalog changes, the expected Production transition is 492 -> 502 exact ICPNs
and 169 -> 175 Base Devices. These are expected transaction results, not current
Production state.
