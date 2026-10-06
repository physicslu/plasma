# STM32WB0 Layer-1 Catalog Admission Proposal v5.2

**Research proposal only. Production publication requires explicit owner approval.**

The merged v5.1 metadata replay establishes all **24 current-Active exact STM32WB0 MPNs** as Layer-1 metadata-ready from official ST Ordering Information.

## Proposal

- additions: **24**
- metadata-ready: **24/24**
- direct Ordering Information decode: **24**
- bounded metadata exceptions: **0**
- network-coprocessor identities: **4**
- backend scope evaluated: **false**
- backend type asserted: **none**
- backend state for all proposed rows: **`no_mapping`**
- Programming Profile: **unresolved**

## STM32WB0-specific metadata boundary

For STM32WB05xN, `N` means **network coprocessor** and is not treated as a Flash-density code.

For STM32WB06/07 `CCF`, the ordering pin code is `C = 48`, but the physical package is **WLCSP49**; the Layer-1 physical pin/ball count is therefore 49.

These semantics are metadata facts only and do not imply a programming backend.

## Projected state only if later explicitly approved

- STM32WB0 Active identity coverage: **0/24 → 24/24 = 100%**
- Production exact total: **4,565 → 4,589**
- Production source count: **27 → 28**
- whole-ST Active intersection: **4,486 → 4,510 / 4,550**
- whole-ST Active gap: **64 → 40**
- whole-ST Active identity coverage: **98.5934% → 99.1209%**

## Boundary

No Production file is changed by this proposal.

No backend route, Programming Profile support, Engineering Verified state, field evidence, or PS/HIL qualification is claimed.
