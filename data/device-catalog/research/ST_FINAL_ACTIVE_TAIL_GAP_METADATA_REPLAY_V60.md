# ST Final Active Tail Gap — Metadata Replay v6.0

Research-only replay for the final **9** exact identities in the locked 2026-10-01 ST eStore Active denominator.

## Locked tail gap

- STM32F4: **3**
- STM32L4: **3**
- STM32L1: **2**
- STM32U3: **1**
- total: **9**
- exact-set SHA-256: `891831ec21f6f65e5332667bf30440f321039740709d697312afd38a821ac801`

Current Production prestate is **4,620 / 4,550 scoped Active intersection 4,541**, leaving exactly these nine identities.

## Metadata authority partition

All **9/9** are metadata-ready:

- **4** decode directly through existing official Ordering Information authorities:
  - STM32L412RBT3
  - STM32L496WGY6PST
  - STM32L496WGY6PTR
  - STM32U375CET6TR
- **5** use official exact-product authority without inventing opaque suffix semantics:
  - STM32F405OGY6VTR
  - STM32F405OGY6WTR
  - STM32F437VIT6WTR
  - STM32L151VDT7X
  - STM32L151VDY6XTR

For `V/W/X` suffixes, the catalog retains the literal manufacturer identity only. It does **not** infer option meaning.

## F4 lifecycle discrepancy

The three F4 identities are part of the locked/current eStore **Active** surface, while current st.com product pages expose them as **NRND**. The discrepancy is retained explicitly; it is not normalized away.

For the scoped 4,550 denominator, the locked eStore Active set remains the lifecycle authority.

## Capability boundary

This replay does not inherit existing F4/L4/L1/U3 OpenOCD mappings.

- backend scope evaluated: false
- existing family backend mapping inherited: false
- Programming Profile expansion: false
- Engineering Verified: false
- field evidence: false
- PS/HIL: false
- Production write: false

Next gate: prepare a frozen 9-row Layer-1 admission proposal. If that proposal is later approved and published, the scoped ST Active identity coverage becomes **4,550 / 4,550 = 100%**.
