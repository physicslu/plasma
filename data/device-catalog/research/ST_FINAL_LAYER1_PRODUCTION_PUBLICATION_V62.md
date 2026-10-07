# ST Final Layer-1 Production Publication v6.2

Owner approval was received on **2026-10-07** for the frozen v6.1 final-nine proposal.

## Transaction

| Family | Before | After | Added |
|---|---:|---:|---:|
| STM32F4 | 384 | **387** | 3 |
| STM32L4 | 446 | **449** | 3 |
| STM32L1 | 144 | **146** | 2 |
| STM32U3 | 106 | **107** | 1 |

All **9** additions remain `no_mapping`. Existing family OpenOCD mappings are not inherited.

## Production poststate

- Production exact ICPNs: **4,629**
- Production sources: **28**
- mapped: **3,673**
- no_mapping: **956**
- scoped ST Active intersection: **4,550 / 4,550**
- scoped Active gap: **0**
- scoped Active identity coverage: **100%**

## Historical integrity

The v6.2 validator removes exactly the nine new identities from the four current canonical files and requires the remaining bytes to equal the pre-v6.2 family artifacts exactly. Therefore the transaction proves that existing mapped identities were not rewritten.

## Meaning of 100%

The 100% figure is strictly **identity coverage against the locked 2026-10-01 ST eStore Active denominator of 4,550 exact MPNs**.

It does not mean:

- 100% OpenOCD/backend mapping
- 100% Programming Profile coverage
- 100% Engineering Verified coverage
- 100% physical/HIL programming coverage

The backend partition after publication is **3,673 mapped / 956 no_mapping**.
