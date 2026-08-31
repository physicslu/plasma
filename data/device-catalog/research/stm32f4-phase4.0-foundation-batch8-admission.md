# STM32F4 Phase 4.0 Foundation Batch 8 Admission

## Scope

Batch 8 admits the bounded policy-ready Base Devices `STM32F417VE` and
`STM32F417ZE`. `STM32F417VG` is the lifecycle control. This change does not
expand admission policy and does not claim programming-algorithm equivalence.
OpenOCD ordering-pattern mapping remains routing evidence only.

## Fresh post-Batch7 inventory

- OpenOCD ordering-pattern Base Devices: `149`
- production Base Devices: `43`
- STM32F4 production exact ICPNs: `140`
- remaining Base Device gaps: `106`
- policy-ready gaps: `13`
- policy-blocked gaps: `93`

## Discovery and retained ST evidence

Discovery run `33390363041`, artifact `9757212311`, completed on the first
bounded browser attempt with `3/3` clean targets. The discovery ZIP SHA-256 is
`d4cb68966ff91cc3db6875e33d9b7ac84255a327237e2b20d1ee627c052b1301`.

Baseline-locked live evidence run `33390913931`, artifact `9757414867`, also
completed on the first attempt with no candidate or lifecycle drift. Its ZIP
SHA-256 is
`be4f002b8c000cdd2e92171ace203b03178eb28056094602248f9007aa26dc0a`.
The retained evidence ID is
`stm32f4-phase4.0-foundation-batch8-2026-08-31-retained-20260831T121653Z-5299281`.

The retained package is offline-valid, `scale_ready`, and records no non-Active
observations. Acquisition never writes the canonical dataset.

## Read-only proposal and controlled publish

Proposal run `33391164641`, artifact `9757487138`, produced:

- candidate/admit: `3/3`
- already present/manual review/reject/conflicts: `0/0/0/0`
- canonical rows: `140 -> 143`
- admission-plan SHA-256:
  `f4f79a0850d50f3ec7f09123e901d08a201eec7300ede4eed4a1db929d8e8b5a`
- proposed/final CSV SHA-256:
  `c37c2931bd27c5754a65cc3e1d7f14702637f95153941abc650b0b30d526eae8`

The controlled publish re-downloaded and hash-checked the proposal, rebuilt it
from retained evidence, compared plan and CSV bytes, enforced the 140-row
production precondition, and committed the canonical CSV, production manifest,
and admission audit as one transaction.

Admitted exact ICPNs:

- `STM32F417VET6`
- `STM32F417VET6TR`
- `STM32F417ZET6`

Production after publish:

- STM32F1 exact ICPNs: `75`
- STM32F4 exact ICPNs: `143`
- total ST exact ICPNs: `218`
- STM32F4 production Base Devices: `45`
- remaining gaps: `104` (`11` policy-ready, `93` policy-blocked)

## Post-admission proof

Offline replay reconstructs the 140-row pre-write dataset from historical
evidence provenance, reproduces the immutable admission-plan hash, materializes
the exact 143-row production CSV, and proves a second application is a no-op.
Current-state replanning reports all three Batch 8 candidates as already
present. Runtime and Web REST regression use `STM32F417VET6TR` as the Batch 8
representative and preserve the 100-result search cap while metadata reports
the full 143-row STM32F4 family.

All discovery, live-evidence, proposal, and publish workflows are one-shot and
must be absent from the merge-ready branch. Final CI is offline/read-only.
