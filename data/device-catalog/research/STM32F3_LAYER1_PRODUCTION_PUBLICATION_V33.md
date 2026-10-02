# STM32F3 Layer-1 Production Publication v3.3

**Owner approval received. This publication expands Device Catalog Layer-1 only.**

## Approved proposal

The publication consumes merged proposal #710 (`stm32f3-layer1-admission-proposal-v3.2`).

Approved locks:

- additions: **182 exact MPNs**
- addition exact-set SHA-256: `1514c8edd3d190a8fd2bc9c27960c47f05ab4536640e008d73e4d5ab2f5a01d7`
- proposal CSV SHA-256: `de8938da114c261b55aee191a6d0916f4ef8e7d0f1cc16f08d3b870074fe3e47`
- metadata authority SHA-256: `5d1f2d565450387b3e4c4074483dea40bfd8c9576e75df88c862da9790c03137`

## Production transaction

The existing STM32F3 Production source is expanded:

- STM32F3 exact ICPNs: **10 → 192**
- canonical SHA-256: `d453efd0720c6aa2d3a246815ffe6eafd8ee9f924fd09c88b0dd4f64387806cc`
- canonical Git blob: `ac580b7df62a18ad3c418845a3087fdac10f4e6d`
- Production exact total: **3,906 → 4,088**
- Production source count: **24 → 24**

## Layer separation

The original ten STM32F3 rows retain their previously admitted deterministic OpenOCD route to `tcl/target/stm32f3x.cfg`.

The newly published 182 rows remain:

- backend mapping state: **`no_mapping`**
- backend scope evaluated for these additions: **false**
- OpenOCD target config: empty
- Programming Profile applicability: unresolved
- Engineering Verified: not claimed
- field evidence: not claimed
- PS/HIL qualification: not claimed

Therefore `no_mapping` means **no route is bound**, not that backend suitability was exhaustively disproven.

After publication, the full Production backend partition is:

| State | Exact ICPNs |
| --- | ---: |
| mapped | 3,673 |
| `no_mapping` | 415 |
| total | 4,088 |

## Coverage effect

- STM32F3 current Active identity coverage: **192 / 192 = 100%**
- whole-ST current Active intersection: **3,827 → 4,009 / 4,550**
- whole-ST current Active gap: **723 → 541**
- whole-ST Active identity coverage: **84.1099% → 88.1099%**

## Validation

The v3.3 publication validator proves that:

1. all 192 published F3 identities equal the locked current-Active F3 set;
2. the original 10 mapped rows remain exactly the legacy mapped set;
3. the 182 new rows equal the approved gap and remain route-free `no_mapping`;
4. those 182 rows reconstruct the approved proposal CSV hash;
5. manifest SHA-256 / Git blob bindings match;
6. Production totals and global backend partition are coherent;
7. no Programming Profile, Engineering Verified, field evidence or HIL scope is widened.
