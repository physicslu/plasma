# STM32H7 Active Gap Lock + Metadata Replay v5.7

Research-only delta refresh against the locked **2026-10-01 ST eStore Active universe**.

## Exact delta

- STM32H7 current Active exact set: **205**
- STM32H7 Production prestate: **191**
- exact gap: **14**
- gap SHA-256: `22587c53a237fe3d2d4a208641e6109dd4d1b67bab1e39c9da86c4233b76b834`

The exact set comes from the same v13 coverage artifact that defines the 4,550 Active denominator.

## Metadata replay

All **14/14** identities decode from official ST Ordering Information with **0 metadata exceptions**.

The older 191-row H7 authority was incomplete for combinations that appeared later in the Active surface. The bounded extensions are:

- STM32H730: `A=169`, `I=176`, `Q=with SMPS`
- STM32H7A3: `Q=132`, `A=169`, `L=225`
- STM32H7B0: `A=169`
- STM32H7B3: `Q=132`, `A=169`, `L=225`

## Capability boundary

The existing 191-row STM32H7 catalog has historical OpenOCD routes. **Those routes are not inherited by this 14-row delta.**

This replay establishes identity and metadata only:

- backend scope: not evaluated
- backend mapping inheritance: false
- Programming Profile expansion: false
- Engineering Verified: false
- field evidence: false
- PS/HIL: false
- Production publication: not authorized

Next gate: prepare a 14-row Layer-1 admission proposal with backend state `no_mapping` unless separately qualified.
