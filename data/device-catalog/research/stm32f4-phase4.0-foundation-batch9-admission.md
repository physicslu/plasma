# STM32F4 Phase 4.0 Foundation Batch 9 Admission

## Scope

Batch 9 uses the maximum six-target acquisition bound: lifecycle control
`STM32F429ZG` plus policy-ready candidates `STM32F429ZE`, `STM32F469VE`,
`STM32F469VG`, `STM32F469VI`, and `STM32F469ZE`. Admission policy is unchanged.
OpenOCD ordering-pattern mapping is routing evidence only and is not proof of
programming-algorithm equivalence.

## Fresh post-Batch8 inventory

- OpenOCD ordering-pattern Base Devices: `149`
- production Base Devices: `45`
- STM32F4 production exact ICPNs: `143`
- remaining Base Device gaps: `104`
- policy-ready gaps: `11`
- policy-blocked gaps: `93`

## Evidence transaction

Expanded discovery run `33393803969`, artifact `9758593055`, completed on the
first whole-batch browser attempt with `6/6` clean targets. The artifact ZIP
SHA-256 is
`1dfd2c8b1fc672469e6768dca9ce659031494ec806c29a162b110e7da7bf6be8`.

Baseline-locked live evidence run `33394189239`, artifact `9758673074`, also
completed on the first attempt with zero candidate/lifecycle drift. The retained
ZIP SHA-256 is
`1c324578524caf8c1993a23abad9dc75842c49c4710d5968adef6ed841933eaf`.
The retained evidence ID is
`stm32f4-phase4.0-foundation-batch9-2026-08-31-retained-20260831T125555Z-4e5cc1b`.

The retained package is offline-valid, `scale_ready`, maps all `6/6` Base
Devices deterministically, and records no non-Active observations.

## Proposal and controlled publish

Read-only proposal run `33394448145`, artifact `9758746391`, produced:

- candidates/admit: `8/8`
- already present/manual review/reject/conflicts: `0/0/0/0`
- canonical rows: `143 -> 151`
- admission-plan SHA-256:
  `7e015f9be2c9814ca7a7f208b29e0686911e44e804026664b6ae2d1b843b96df`
- proposed/final CSV SHA-256:
  `4162766eef529f17da3d5f5d904ee1a6db6a58e805ad23ca1b1c75d20ca62e50`

The controlled publish verified immutable artifact bindings, rebuilt and
byte-compared the proposal, enforced the 143-row production precondition, and
committed the CSV, production manifest, and audit atomically.

Admitted exact ICPNs:

- `STM32F429ZET6`, `STM32F429ZET6TR`
- `STM32F469VET6`, `STM32F469VET6TR`
- `STM32F469VGT6`
- `STM32F469VIT6`, `STM32F469VIT6TR`
- `STM32F469ZET6`

Production after publish:

- STM32F1 exact ICPNs: `75`
- STM32F4 exact ICPNs: `151`
- total ST exact ICPNs: `226`
- STM32F4 production Base Devices: `50`
- remaining gaps: `99` (`6` policy-ready, `93` policy-blocked)

Historical replay reconstructs the 143-row pre-write dataset, reproduces the
immutable plan hash, materializes the exact 151-row CSV, and proves the second
application is a no-op. `STM32F469VIT6TR` is the runtime/REST representative.
All one-shot workflows are absent from the merge-ready branch.
