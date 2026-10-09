# OpenOCD C0 Canonical Successor v6.27

v6.27 preserves the historical `openocd-parts-canonical.csv` snapshot byte-for-byte and writes a new versioned canonical successor containing the bounded STM32C0 route delta approved through v6.25/v6.26.

## Architecture correction

The first branch commit attempted to write the four rows directly into the legacy canonical snapshot. CI exposed that this file is an immutable input for many retained historical gates. Rewriting dozens of historical validators to accept mutable history would violate the repository's existing evidence model.

The branch therefore corrects the architecture without rewriting Git history:

- legacy snapshot remains exactly `0ef056e3363e20bb527590c4a4cc1cc0d7afb810` / **7,657 rows**;
- successor `openocd-parts-canonical-v627.csv` is exactly the v6.26 frozen postimage:
  - Git blob `81e44f6a6df902f3b206d06bfac38e37ec74630b`
  - SHA256 `39bb6f17765b8c95fdf1cdfa9831ac1c71ef3edd08ae899fcf6f67eae4234751`
  - **7,661 rows**;
- `openocd-c0-bounded-route-inventory-v6.25.csv` materializes the exact four-row provenance source.

The validator removes the four provenance rows from the successor in memory and requires byte-for-byte reconstruction of the legacy snapshot.

## Activation boundary

The successor is not silently substituted for historical research. A future Production mapping transaction must explicitly name `openocd-parts-canonical-v627.csv` as its route-inventory source.

Production remains unchanged:

- mapped: **4,054**
- no_mapping: **575**
- Active OpenOCD route: **3,975 / 4,550 = 87.3626%**
- the five C0 exact ICPNs remain `no_mapping`

No Programming Profile, erase/program/verify, Engineering Verified, or HIL claim is made.
