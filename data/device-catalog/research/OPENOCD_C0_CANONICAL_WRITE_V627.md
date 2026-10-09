# OpenOCD C0 Canonical Route-Inventory Write v6.27

This PR performs the owner-approved canonical route-inventory write for the bounded STM32C0 scope prepared in v6.25 and frozen in v6.26.

## Actual write transaction

A single Git commit writes both required artifacts:

- `openocd-parts-canonical.csv`: **7,657 → 7,661 rows**
- `openocd-c0-bounded-route-inventory-v6.25.csv`: materialized 4-row provenance source

Frozen postimage:

- Git blob: `81e44f6a6df902f3b206d06bfac38e37ec74630b`
- SHA256: `39bb6f17765b8c95fdf1cdfa9831ac1c71ef3edd08ae899fcf6f67eae4234751`

The validator also removes those exact four rows in memory and requires the result to reconstruct the previous canonical blob exactly:

`0ef056e3363e20bb527590c4a4cc1cc0d7afb810`

This proves the canonical mutation is exactly the approved four-row delta.

## Production boundary

This is **not** a Production mapping write. The five exact ICPNs remain `no_mapping` in Production:

- mapped: **4,054**
- no_mapping: **575**
- Active OpenOCD route: **3,975 / 4,550 = 87.3626%**

A separate owner approval is still required before any Production mapping transaction.

No Programming Profile, erase/program/verify, Engineering Verified, or HIL claim is made.
