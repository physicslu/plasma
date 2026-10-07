# OpenOCD Tier A Route Candidate Proposal v6.4

Research-only candidate generation for the **389** highest-confidence identities in the current 956-row Active OpenOCD route gap.

## Selection rule

A `no_mapping` row enters Tier A only when:

1. the same **family + series** already contains one or more mapped sibling identities;
2. every mapped sibling in that family + series uses **exactly one identical OpenOCD target config**;
3. the candidate itself remains `no_mapping`.

This is intentionally weaker than a Production backend mapping decision.

## Candidate count

**389 exact MPNs**

Family distribution:

- STM32F2: 72
- STM32F3: 172
- STM32F4: 3
- STM32F7: 62
- STM32G0: 42
- STM32G4: 1
- STM32C0: 17
- STM32L4: 3
- STM32L1: 2
- STM32U3: 1
- STM32H7: 14

## Deliberate omissions

The proposal does **not** synthesize:

- `existing_identifier`
- `existing_identifier_kind`
- Programming Profile
- Engineering Verified status
- HIL result

It only proposes a **candidate target config** inherited from an unambiguous same-series sibling set.

## Coverage opportunity

Current Active OpenOCD route coverage:

**3,594 / 4,550 = 78.9890%**

If all 389 Tier A candidates later pass backend qualification:

**3,983 / 4,550 = 87.5385%**

Remaining gap would be **567**.

No Production file is changed by v6.4.
