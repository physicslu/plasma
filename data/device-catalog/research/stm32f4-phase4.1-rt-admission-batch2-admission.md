# STM32F4 Phase 4.1 R/T Batch 2 Admission Closure

## Scope

This transaction admits exact commercial STM32F4 ICPNs for the approved R/T catalog-semantics policy class. The admission is evidence-bound and deterministic. OpenOCD ordering-pattern routing remains routing evidence only and is not treated as programming-algorithm equivalence.

No IC Support profile, PS/PL runtime, PPU, deployment, or hardware behavior is changed by this transaction.

## Discovery baseline

- discovery workflow run: `33476464732`
- discovery artifact: `9788381143`
- discovery artifact SHA-256: `35bbebc8c1cce87ad8fa3fa43f30a76bde056273eb9adcf8549cc2658bbde7d8`
- lifecycle control: `STM32F479ZG` / `STM32F479ZGT6`
- candidate Base Devices: `STM32F401RB`, `STM32F401RC`, `STM32F401RD`, `STM32F401RE`, `STM32F405RG`
- expected Active exact observations including the lifecycle control: `18`
- expected new admission candidates: `17`

The baseline admits only exact commercial part numbers observed on the official ST product page with Marketing Status `Active`. Non-Active observations remain lifecycle audit data and are excluded from new admission.

## Retained evidence

- evidence ID: `stm32f4-phase4.1-rt-admission-batch2-2026-09-01-retained-20260901T125059Z-4e0435d`
- retained evidence artifact: `9801196525`
- retained evidence ZIP SHA-256: `ebd6bcf6a7eaccbf69dabba72adcaed736bbf8c29952091fe73d9bc336468e5b`
- acquisition targets: `6/6`
- candidate baseline match: `true`
- candidate drift: `0`
- retained evidence state: `scale_ready`

The following two official ST observations are NRND and remain audit-only exclusions:

- `STM32F405RGT6V`
- `STM32F405RGT6W`

## Deterministic admission proposal

- proposal workflow run: `33510466747`
- proposal artifact: `9801403104`
- proposal ZIP SHA-256: `3f0ad3b5c9437cf51fb41ba06b532fd2c54bd896dc776de9d18e927d080e727b`
- admission plan SHA-256: `6f5344b46564f38a7d5b7eadd64ecaeff8d0807209005253f7b79985f7dd7c9e`
- decision counts: `17 admit / 0 already_present / 0 manual_review_required / 0 reject`
- conflicts: `0`
- issues: none

### Admitted exact ICPNs

1. `STM32F401RBT6`
2. `STM32F401RBT6TR`
3. `STM32F401RCT6`
4. `STM32F401RCT6TR`
5. `STM32F401RCT7`
6. `STM32F401RCT7TR`
7. `STM32F401RDT6`
8. `STM32F401RDT6TR`
9. `STM32F401RDT7`
10. `STM32F401RDT7TR`
11. `STM32F401RET6`
12. `STM32F401RET6TR`
13. `STM32F401RET7`
14. `STM32F405RGT6`
15. `STM32F405RGT6TR`
16. `STM32F405RGT7`
17. `STM32F405RGT7TR`

## Controlled publish result

The controlled publish was bound to the production pre-state, immutable proposal artifact, deterministic plan, and byte-identical regenerated CSV before canonical write.

| State | STM32F4 rows | ST total rows | CSV SHA-256 | Git blob |
| --- | ---: | ---: | --- | --- |
| Pre-admission | 158 | 233 | `6a3150e356511dfed679b747515d1ae1380d3da101b11edd3322f27cd936c948` | `21ad3fee8b780949e8184cdb56b5601fe6a48c03` |
| Post-admission | 175 | 250 | `6d096c2129a2a3f520c049c0eaab1749cec05f163a773be7db10ec82472c8e58` | `614e81313b69c27d8306b22df68a5a20b031e20d` |

The admission audit records `canonical_dataset_written=true`, with `17` new exact ICPNs and no conflicts or unresolved issues.

## Regression closure

Historical transaction tests must preserve immutable historical hashes and row counts without freezing the current production catalog at a past snapshot.

For Batch 10 and Batch 11, the regression model now separates two concerns:

1. Historical replay reconstructs the transaction pre-state from an explicit immutable evidence cohort and verifies the original deterministic plan/materialization hashes.
2. Current-state assertions allow later catalog growth while verifying that the current production manifest is bound to the current canonical CSV.

In particular, Batch 11 no longer reconstructs its 157-row pre-state by subtracting one Batch 11 row from the current catalog. Its historical 157-row pre-state is reconstructed from the exact evidence cohorts that existed before Batch 11.

The Phase 4.1 R/T policy regression likewise verifies that approved policy semantics remain effective after later admissions while all unapproved policy classes remain fail-closed.

The permanent Device Catalog CI includes retained-evidence validation and post-admission replay for this Batch 2 transaction. Temporary acquisition/proposal/publish/regression-fix workflows are not part of the retained production workflow set.

## Safety boundary

This closure establishes exact commercial identity admission only. It does not claim that devices sharing `tcl/target/stm32f4x.cfg` have equivalent programming algorithms, flash geometry, electrical behavior, or execution requirements. Those remain separate IC Support / execution-validation concerns.
