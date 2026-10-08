# OpenOCD A-Residual Diagnostic v6.18

Research-only diagnostic for the 25 exact ICPNs remaining in the post-v6.16/post-v6.17 Tier-A-equivalent gap.

## Scope

Current family partition:

- STM32G0: 12
- STM32C0: 5
- STM32F3: 4
- STM32L4: 2
- STM32G4: 1
- STM32L1: 1

These rows already have a same-series mapped sibling set with one consistent target config. That is sufficient to justify deeper route analysis, but not sufficient to infer an identifier or write a Production mapping.

## Diagnostic dimensions

For each exact ICPN, v6.18 records mapped sibling count, same-series route inventory, same-base route inventory, current family-policy matches, exact Catalog option-suffix normalization, prefix semantics, one-character diagnostic generalization, structural gap class, and the recommended next gate.

## Fail-closed rules

v6.18 must fail if the 25-row family/series partition drifts, a direct current-policy match unexpectedly appears, an exact-suffix-normalized match unexpectedly reappears, the frozen G0 12-row prefix result changes from 0/12, or the five C0 residuals stop being missing-base-variant route-inventory gaps.

No probe result authorizes a family-wide policy change. Any future bridge must be independently bounded to an exact set and must retain separate owner approval before Production write.

No Programming Profile, erase/program/verify, Engineering Verified, or HIL claim is made.


## Diagnostic result

The 25-row residual partitions into two structural classes:

- route inventory present, policy-shape gap: **18**
- base variant absent from canonical route inventory: **7**

Probe result:

- unique under one-character diagnostic: **17**
  - STM32G0: 12
  - STM32F3: 4
  - STM32L1: 1
- ambiguous under one-character diagnostic: **1**
  - STM32G4: 1
- no identifier probe match: **7**
  - STM32C0: 5
  - STM32L4: 2

The one-character result is diagnostic only. It is weaker than an admitted route binding and does not justify a family-wide normalization rule.

The 17 unique rows are the next exact-set evidence-review opportunity. If all 17 later pass an independent bounded-bridge qualification and Production transaction, Active route coverage would move from **3,958 / 4,550 = 86.9890%** to **3,975 / 4,550 = 87.3626%**, leaving **575** Active route gaps.

The seven missing-base-variant rows require canonical route-inventory expansion rather than identifier-policy relaxation. The ambiguous STM32G4 row also requires stronger route evidence before any bridge can be proposed.
