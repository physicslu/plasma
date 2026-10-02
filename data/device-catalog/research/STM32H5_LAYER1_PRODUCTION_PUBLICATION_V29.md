# STM32H5 Layer-1 Production Publication v2.9

**Owner approval received. This change publishes Device Catalog Layer-1 identity/metadata only.**

## Approved source

The publication consumes the merged STM32H5 Layer-1 admission proposal v2.8 from PR #705.

Approved locks:

- candidate exact MPNs: **190**
- exact-set SHA-256: `33b3d084b635a39f71e9d724aae3456bfb65c1e7e904b0b6547a849bd9dbee9b`
- proposal CSV SHA-256: `07e1c05a60e0eb19d00b61fa9a092e754752aeb9475a4fe7f3403eab7a0749cd`
- ordering authority SHA-256: `2cd9372151db5997adaf44aaf5e029a0f8c566a3fa09daa0095fbeea258454a6`

The final approved proposal workflow artifact is retained in the publication audit.

## Production transaction

This publication adds one Production source:

- family: `STM32H5`
- exact ICPNs: **190**
- canonical SHA-256: `cdee4a1f765b3f345e89dc21d2b56d5344dd6345973a1013ec45feffebeec194`
- canonical Git blob: `5d95f712445e94ef800dd54a26739203b2f2b412`

Production moves:

- sources: **23 → 24**
- exact ICPNs: **3,716 → 3,906**
- STM32H5 exact ICPNs: **0 → 190**
- whole-ST current Active intersection: **3,637 → 3,827 / 4,550**
- whole-ST current Active gap: **913 → 723**
- whole-ST Active identity coverage: **79.9341% → 84.1099%**

## Layer separation

All 190 published H5 identities deliberately remain:

- backend mapping state: **`no_mapping`**
- OpenOCD target config: empty
- Programming Profile applicability: unresolved
- Engineering Verified: not claimed
- Field Evidence: not claimed
- PS/HIL qualification: not claimed

Therefore this publication means **“Plasma knows the exact ST identity and manufacturer-backed metadata”**, not **“Plasma can program this device.”**

After publication the Production backend partition is:

| State | Exact ICPNs |
| --- | ---: |
| mapped | 3,673 |
| `no_mapping` | 233 |
| total | 3,906 |

## Bounded metadata exceptions

The exact-only H5E package-code exception remains limited to:

- `STM32H5E4ZJJ6`
- `STM32H5E4ZJJ7Q`
- `STM32H5E4ZKJ6`

No family-wide `J` package inference is introduced.

## IC Support numeric pin-count derivation

The canonical Device Catalog preserves ST's manufacturer notation such as `64/68`, `100/105`, and `176/176+25`. The derived IC Support inventory requires a single numeric physical count, so v2.9 resolves only package-qualified combinations proven by the same ST product surfaces:

- `64/68`: LQFP → 64, VFQFPN → 68;
- `176/176+25`: LQFP → 176, UFBGA 10x10 → 201 physical balls;
- `100/105`: current admitted LQFP rows → 100;
- `144/144`: identical alternatives collapse to 144.

Any unknown slash/package combination fails closed. This derivation does not alter the approved canonical H5 metadata rows.

## Validation

The v2.9 validator must prove:

1. the Production H5 exact set equals the approved 190 identities;
2. the Production rows reconstruct the approved proposal CSV hash;
3. all 190 rows remain route-free `no_mapping`;
4. manifest SHA-256 / Git blob bindings match;
5. Production totals and backend partition are coherent;
6. IC Support remains limited to the existing evidence-backed bindings.
