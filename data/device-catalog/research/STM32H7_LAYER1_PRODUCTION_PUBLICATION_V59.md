# STM32H7 Layer-1 Production Publication v5.9

Owner approval was received on **2026-10-07** for the frozen v5.8 proposal.

## Transaction

- STM32H7 Production rows: **191 → 205**
- approved delta: **14 exact MPNs**
- all 14 additions: **no_mapping**
- Production exact total: **4,606 → 4,620**
- Production source count: **28 → 28**
- backend partition: **3,673 mapped / 933 no_mapping → 3,673 mapped / 947 no_mapping**

## Historical mapping boundary

The pre-existing 191 STM32H7 rows retain their historical OpenOCD routes. The v5.9 validator reconstructs those 191 rows from the 205-row canonical file and requires their bytes to remain identical to:

- historical Git blob: `fda7d9a4eaa9978d0a67416e8b339fc9aab4e5cc`
- historical SHA-256: `35b9d2bc13da3a01809ea62b62557f5419b8d6f7139574ca4715a127f1e86465`

No route from that historical set is inferred for the 14 new rows.

## Current canonical integrity

- Git blob: `a0ca2521a196e4e7f3d87560b05e830611e85b32`
- SHA-256: `ae0fbffecb9f978f6195ded06fcecfc5a048b71ef8c307548a3298b35889af07`

## Coverage

- STM32H7 current Active coverage: **205 / 205 = 100%**
- whole-ST Active intersection: **4,541 / 4,550**
- residual gap: **9**
- whole-ST Active identity coverage: **99.8022%**

This is Catalog Layer-1 publication only for the 14-row delta. No Programming Profile, Engineering Verified, field-evidence, or PS/HIL claim is added.
