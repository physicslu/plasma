# ST Final 9 — Layer-1 Catalog Admission Proposal v6.1

**Research proposal only. Production publication requires explicit owner approval.**

Merged v6.0 establishes metadata authority for the final nine exact identities in the locked 4,550-device ST eStore Active denominator.

## Proposal

- additions: **9**
- STM32F4: **3**
- STM32L4: **3**
- STM32L1: **2**
- STM32U3: **1**
- metadata-ready: **9/9**
- metadata blocked: **0**
- backend state for all new rows: **`no_mapping`**
- existing family backend mappings inherited: **false**
- Programming Profile: **unresolved**

The five `V/W/X` exact-product identities retain opaque manufacturer suffixes literally. No option semantics are invented.

## Frozen proposal locks

- exact-set SHA-256: `891831ec21f6f65e5332667bf30440f321039740709d697312afd38a821ac801`
- proposal CSV SHA-256: `682ec66ddff6eb880f4ff84e4c971177b2d8150021998fc78469e9b35911b223`
- source workflow run: `37572250038`
- source artifact: `11461201671`
- artifact SHA-256: `30a82373e31dd9da5ad93de1deaf52da56b56b6b8ca1f0f4206c7c427a0f951c`
- metadata authority Git blob: `9f260f83c9f81147f1c768c846abcc39c9fd2bc8`

## Projected state only if later explicitly approved

| Metric | Current | Projected |
|---|---:|---:|
| Production exact ICPNs | 4,620 | **4,629** |
| Production sources | 28 | **28** |
| mapped | 3,673 | **3,673** |
| no_mapping | 947 | **956** |
| scoped ST Active intersection | 4,541 / 4,550 | **4,550 / 4,550** |
| scoped Active gap | 9 | **0** |
| scoped Active identity coverage | 99.8022% | **100%** |

Family source rows would become:

- STM32F4: 384 → **387**
- STM32L4: 446 → **449**
- STM32L1: 144 → **146**
- STM32U3: 106 → **107**

## Boundary

This proposal does not modify Production.

100% here means **identity coverage against the locked 2026-10-01 4,550-device Active denominator**. It does **not** mean 100% programming support, backend coverage, Engineering Verified coverage, or HIL coverage.
