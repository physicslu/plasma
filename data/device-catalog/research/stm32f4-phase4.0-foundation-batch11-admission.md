# STM32F4 Phase 4.0 Foundation Batch 11 Admission

## Scope

Batch 11 closes the last Base Device that was admission-ready under the
unchanged STM32F4 policy. The bounded transaction uses production-admitted
`STM32F479ZG` as its lifecycle control and admits only `STM32F479ZI`.
OpenOCD ordering-pattern mapping is routing evidence only; it is not evidence
of programming-algorithm equivalence, PPU qualification, socket validation, or
hardware operation.

## Fresh post-Batch10 inventory

- OpenOCD ordering-pattern Base Devices: `149`
- production Base Devices: `55`
- STM32F4 production exact ICPNs: `157`
- remaining Base Device gaps: `94`
- policy-ready gaps: `1`
- policy-blocked gaps: `93`
- sole policy-ready Base Device: `STM32F479ZI`

## Evidence transaction

Discovery run `33464522226`, artifact `9784377080`, acquired both targets
cleanly in one bounded attempt. The discovery ZIP SHA-256 is
`db546ac3dc9477fc02daaa9d0fb9114dbad436af5597c644dde5150536502950`.
The locked discovery set was:

- lifecycle control: `STM32F479ZG` -> `STM32F479ZGT6`
- admission candidate: `STM32F479ZI` -> `STM32F479ZIT6`

Baseline-locked live evidence run `33464822120`, artifact `9784489545`,
required the one permitted whole-batch retry. The first attempt acquired `1/2`
and timed out waiting for the `STM32F479ZI` browser readiness surface; the
second acquired `2/2` cleanly with zero candidate or lifecycle drift. The
retained ZIP SHA-256 is
`3de6bfd40576768d1afc672158eb1c507b6b50bb73805de54e8fd18e90643344`.
The retained evidence ID is
`stm32f4-phase4.0-foundation-batch11-2026-09-01-retained-20260901T030509Z-4fb6652`.

The retained package contains README, control summary, evaluation, pilot
summary, provenance, and a deterministic per-file manifest. Offline validation
reports `scale_ready`, `2/2` unique ordering-pattern mappings, no candidate
drift, and no non-Active observation in this Batch 11 target set. The retry is
preserved as provenance and is not represented as evidence of a stable browser
transport.

## Proposal and controlled publish

Read-only proposal run `33465207580`, artifact `9784588327`, produced:

- candidates/admit: `1/1`
- already present/manual review/reject/conflicts: `0/0/0/0`
- canonical rows: `157 -> 158`
- admitted ICPN: `STM32F479ZIT6`
- proposal ZIP SHA-256:
  `906ae4219072b29b5f83b40c3e8f587e948758cbfbc4a0e681adb3001993e92f`
- admission-plan SHA-256:
  `2c024e80102919ff9be2213d48809c0dde07d8a8e5d7ad7dbdd83fab54f433fe`
- proposed/final CSV SHA-256:
  `6a3150e356511dfed679b747515d1ae1380d3da101b11edd3322f27cd936c948`
- final CSV Git blob:
  `21ad3fee8b780949e8184cdb56b5601fe6a48c03`

Controlled publish run `33473216599` verified the immutable ZIP, plan, CSV, and
Git-blob bindings; rebuilt and byte-compared the proposal; enforced the
157-row production precondition; and committed the CSV, production manifest,
and admission audit atomically.

## Production and governance result

- STM32F1 exact ICPNs: `75`
- STM32F4 exact ICPNs: `158`
- total ST exact ICPNs: `233`
- STM32F4 production Base Devices: `56`
- remaining gaps: `93`
- policy-ready gaps under the unchanged policy: `0`
- policy-blocked gaps requiring Phase 4.1 policy work: `93`

Historical replay reconstructs the 157-row pre-write dataset, reproduces the
immutable plan hash, materializes the exact 158-row CSV, and proves a second
application is a no-op. `STM32F479ZIT6` is the runtime/REST representative.

The prior official-ST observation of `STM32F401CCF6TR` as `Preview` remains a
lifecycle audit signal only. The row remains production-admitted because this
phase has no de-admission policy or authority. Regression coverage binds that
non-Active observation to the existing explicit governance note and prevents
Batch 11 from silently removing the row.

All Batch 11 discovery, live-acquisition, proposal, and publish workflows are
absent from the review branch. Phase 4.1 must be a separate policy-expansion
transaction before any of the remaining 93 Base Device gaps can become catalog
admission candidates. PPU and hardware qualification remain explicitly out of
scope until catalog coverage and its policy evidence are completed.
