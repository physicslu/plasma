# STM32F4 Phase 4.1 Batch 1 — R/T policy expansion

## Decision

Phase 4.1 Batch 1 adds one catalog-semantic mapping only:

```text
STM32F4 pin-count code R + package code T -> LQFP, 64 pins
```

Seven official STMicroelectronics datasheet ordering schemes cover all six
affected STM32F4 series. The retained evidence package is
`evidence/stm32f4-phase4.1-rt-policy-2026-09-01`.

## Exact impact

The production STM32F4 catalog remains at 158 exact ICPNs and the combined ST
production catalog remains at 233 exact ICPNs. No exact commercial identity is
admitted by this policy change.

The read-only OpenOCD coverage-gap inventory changes as follows:

| Metric | Before | After |
|---|---:|---:|
| OpenOCD ordering-pattern Base Devices | 149 | 149 |
| Production STM32F4 Base Devices | 56 | 56 |
| Gap Base Devices | 93 | 93 |
| Policy-ready gaps | 0 | 11 |
| Policy-blocked gaps | 93 | 82 |

Newly policy-ready Base Devices:

- `STM32F401RB`
- `STM32F401RC`
- `STM32F401RD`
- `STM32F401RE`
- `STM32F405RG`
- `STM32F411RC`
- `STM32F411RE`
- `STM32F413RG`
- `STM32F415RG`
- `STM32F446RC`
- `STM32F446RE`

All other unsupported flash-size, package, and pin/package classes remain
fail-closed. The offline regression locks the complete set of 15 remaining
blocker classes.

## Evidence and non-claims

The retained source observations bind ST datasheet document IDs, revisions,
section/table locators, official URLs, affected Base Devices, and the normalized
`R`/`T` assertions. The package manifest binds all retained local files with
SHA-256 and is validated without network access.

The ST PDF bytes are not retained and no PDF-byte hash is claimed. This policy
evidence proves only the commercial-order-code field semantics. It does not
prove that any syntactically possible exact ICPN is Active or orderable.

OpenOCD ordering patterns remain routing evidence for
`tcl/target/stm32f4x.cfg`; they are not a programming-algorithm-equivalence
claim. Each of the 11 Base Devices still requires separate official live exact
ICPN evidence and a clean admission plan before any production row can be
added.

`STM32F401CCF6TR` remains admitted. Its current official `Preview` observation
is audit-only because no explicit de-admission policy exists in this phase.

## Next transaction boundary

After this policy PR is merged, live acquisition and exact-ICPN admission must
run in separate bounded transactions. A future admission batch may select only
from the 11 policy-ready Base Devices, must use an admitted lifecycle control,
must retain official ST product-page evidence, and must stop without writing the
production CSV unless its deterministic admission plan is clean.
