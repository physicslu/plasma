# STM32N6 Layer-1 Catalog Admission Proposal v4.9

**Research proposal only. Production publication requires explicit owner approval.**

The merged v4.8 metadata replay establishes all **32 current-Active exact STM32N6 MPNs** as Layer-1 metadata-ready from official ST DS14791 Rev 11 Ordering Information.

## Proposal

- additions: **32**
- metadata-ready: **32/32**
- direct Ordering Information decode: **32**
- bounded metadata exceptions: **0**
- backend scope evaluated: **false**
- backend type asserted: **none**
- backend state for all proposed rows: **`no_mapping`**
- Programming Profile: **unresolved**

## STM32N6-specific capability boundary

STM32N6 does not follow the ordinary "internal MCU Flash" assumption used by many other STM32 families.

Therefore this proposal intentionally does **not** bind:

- OpenOCD as a programming backend,
- any target configuration,
- internal-Flash programming semantics,
- external-memory programming procedures,
- boot/loader provisioning behavior,
- a Programming Profile.

The known external-memory / special programming-profile question remains a separate Layer-2 capability gate.

Catalog identity metadata and programming capability are independent dimensions.

## Frozen proposal locks

- exact-set SHA-256: `f3ae0640f7e28c14b40b7b2ff83570e0bd95c7d0bd3bd98baac6edbcfc78bd50`
- proposal CSV SHA-256: `af1badb6c8ae555b0364421c1e88b7117d07a8e0bc362e6bce71f3df02c8a81e`
- metadata authority SHA-256: `a1abca6e300936583198e73053d1894496fb1764a2fb7874a489f9e5cc3dbe2f`
- source workflow run: `37434384862`
- source artifact: `11397719001`
- artifact ZIP SHA-256: `2a122b622d25822e57d391700d1d36ae140533253ee65be135da77fd4757d9f6`

## Projected state only if later explicitly approved

- STM32N6 Active identity coverage: **0/32 → 32/32 = 100%**
- Production exact total: **4,533 → 4,565**
- Production source count: **26 → 27**
- whole-ST Active intersection: **4,454 → 4,486 / 4,550**
- whole-ST Active gap: **96 → 64**
- whole-ST Active identity coverage: **97.8901% → 98.5934%**

## Boundary

No Production file is changed by this proposal.

No backend route, Programming Profile support, Engineering Verified state, field evidence, or PS/HIL qualification is claimed.
