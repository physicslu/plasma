# STM32F4 Phase 4.0 Foundation Batch 10 Admission

## Scope

Batch 10 uses the maximum six-target acquisition bound: lifecycle control
`STM32F469ZE` plus policy-ready candidates `STM32F469ZG`, `STM32F469ZI`,
`STM32F479VG`, `STM32F479VI`, and `STM32F479ZG`. `STM32F479ZI` is intentionally
left for the next bounded transaction. Admission policy is unchanged. OpenOCD
ordering-pattern mapping is routing evidence only and is not proof of
programming-algorithm equivalence.

## Fresh post-Batch9 inventory

- OpenOCD ordering-pattern Base Devices: `149`
- production Base Devices: `50`
- STM32F4 production exact ICPNs: `151`
- remaining Base Device gaps: `99`
- policy-ready gaps: `6`
- policy-blocked gaps: `93`

## Evidence transaction

Discovery run `33459946054`, artifact `9782865727`, required two bounded
whole-batch attempts. The first attempt acquired `4/6`; the second acquired
`6/6` cleanly. The discovery ZIP SHA-256 is
`5bbe5ac3c70bd14b00885e76f72f5499213de2d1a77502081b70783000af21d0`.

Baseline-locked live evidence run `33460561015`, artifact `9783059763`, also
required two bounded whole-batch attempts. The first attempt acquired `5/6`
and timed out waiting for the `STM32F469ZI` browser readiness surface; the
second acquired `6/6` cleanly with zero candidate or lifecycle drift. The
retained ZIP SHA-256 is
`10d49bebdc897428bd3477ce0cb03132ddcc67525fd514a3a6e3936af958061b`.
The retained evidence ID is
`stm32f4-phase4.0-foundation-batch10-2026-09-01-retained-20260901T015746Z-6ecf759`.

The retained package is offline-valid, `scale_ready`, maps all `6/6` Base
Devices deterministically, and records no non-Active observations. The retries
are retained as acquisition provenance; they are not represented as evidence
that the browser transport is stable.

## Proposal and controlled publish

Read-only proposal run `33461938201`, artifact `9783458088`, produced:

- candidates/admit: `6/6`
- already present/manual review/reject/conflicts: `0/0/0/0`
- canonical rows: `151 -> 157`
- proposal ZIP SHA-256:
  `201cf27d4b2f2e72f51a566e6a32b1f5cf582d6746ad1df3ab7320588d60d295`
- admission-plan SHA-256:
  `1613d2a0ee774ae34d246feb713cc253f1d1a21717f723d2aa1f20b18754de81`
- proposed/final CSV SHA-256:
  `9a5c90fd0b1b326a073fa7d88d7d76962716872505a5f856b6b8f5ba0b2d3a41`

Controlled publish run `33462297240` verified immutable artifact bindings,
rebuilt and byte-compared the proposal, enforced the 151-row production
precondition, and committed the CSV, production manifest, and admission audit
atomically.

Admitted exact ICPNs:

- `STM32F469ZGT6`, `STM32F469ZGT6TR`
- `STM32F469ZIT6`
- `STM32F479VGT6`
- `STM32F479VIT6`
- `STM32F479ZGT6`

Production after publish:

- STM32F1 exact ICPNs: `75`
- STM32F4 exact ICPNs: `157`
- total ST exact ICPNs: `232`
- STM32F4 production Base Devices: `55`
- remaining gaps: `94` (`1` policy-ready, `93` policy-blocked)
- remaining policy-ready Base Device: `STM32F479ZI`

Historical replay reconstructs the 151-row pre-write dataset, reproduces the
immutable plan hash, materializes the exact 157-row CSV, and proves the second
application is a no-op. `STM32F479VIT6` is the runtime/REST representative.
`STM32F401CCF6TR` remains in production: its current Preview observation is
audit-only, and this phase has no de-admission authority. All one-shot live,
proposal, and publish workflows are absent from the merge-ready branch.
