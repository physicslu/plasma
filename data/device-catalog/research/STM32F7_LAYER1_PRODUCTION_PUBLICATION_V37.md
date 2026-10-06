# STM32F7 Layer-1 Production Publication v3.7

**Owner approval received. This publication expands Device Catalog Layer-1 only.**

## Approved proposal

The publication consumes merged proposal #716 (`stm32f7-layer1-admission-proposal-v3.6`).

Approved locks:

- additions: **154 exact MPNs**
- addition exact-set SHA-256: `ec93408ecec154bf40a6fcd4d5ddb063e5e36cb023bc19bbed13b306a3b4a931`
- proposal CSV SHA-256: `bde4bbf82b4a528a18eb6d4d298b06cf8df9bbc7918150bfb9ed510cdbfe3170`
- metadata authority SHA-256: `9828220050adfa19c7c6c6ff74a863ab2d3583d13258b6d286c3b831975129c6`

## Production transaction

The existing STM32F7 Production source is expanded:

- STM32F7 exact ICPNs: **19 → 173**
- canonical SHA-256: `3a41384c29195329dd09042aaa992ab38fb5f13d45f200dfddef5efbe7ef7fe4`
- canonical Git blob: `109efdfe2901919b685e047d7e8895b541ec9b5f`
- Production exact total: **4,088 → 4,242**
- Production source count: **24 → 24**

## Layer separation

The original 19 STM32F7 rows retain their deterministic OpenOCD route to `tcl/target/stm32f7x.cfg`.

The newly published 154 rows remain:

- backend mapping state: **`no_mapping`**
- backend scope evaluated for these additions: **false**
- OpenOCD target config: empty
- Programming Profile applicability: unresolved
- Engineering Verified: not claimed
- field evidence: not claimed
- PS/HIL qualification: not claimed

The three STM32F750 x8 metadata overrides remain exact-product bounded only.

After publication, the full Production backend partition is:

| State | Exact ICPNs |
| --- | ---: |
| mapped | 3,673 |
| `no_mapping` | 569 |
| total | 4,242 |

## Coverage effect

- STM32F7 current Active identity coverage: **173 / 173 = 100%**
- whole-ST current Active intersection: **4,009 → 4,163 / 4,550**
- whole-ST current Active gap: **541 → 387**
- whole-ST Active identity coverage: **88.1099% → 91.4945%**
