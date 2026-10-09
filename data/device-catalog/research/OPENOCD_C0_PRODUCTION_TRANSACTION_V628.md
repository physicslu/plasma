# OpenOCD C0 Production Backend Transaction Dry-Run v6.28

v6.28 prepares a dry-run Production backend-only transaction for the five STM32C0 exact ICPNs whose bounded routes were established through v6.24–v6.27.

## Explicit route source

This transaction does **not** read the immutable legacy snapshot as its route authority. It is hard-bound to the versioned successor:

- path: `data/device-catalog/research/openocd-parts-canonical-v627.csv`
- Git blob: `81e44f6a6df902f3b206d06bfac38e37ec74630b`
- SHA256: `39bb6f17765b8c95fdf1cdfa9831ac1c71ef3edd08ae899fcf6f67eae4234751`
- rows: **7,661**

The exact four pattern rows are independently bound to `openocd-c0-bounded-route-inventory-v6.25.csv`.

## Exact Production scope

Five exact ICPNs:

- `STM32C011D6Y6TR`
- `STM32C051D8Y6TR`
- `STM32C091ECY6TR`
- `STM32C092ECY3TR`
- `STM32C092ECY6TR`

For each row the current Production preimage must be `no_mapping` with empty backend-binding fields. The dry-run may change only:

- `existing_identifier`
- `existing_identifier_kind`
- `mapping_status`
- `openocd_target_config`
- `cmsis_device_name` remains empty.

Identity, lifecycle, package, flash, temperature, source authority and verification metadata are immutable.

## Frozen dry-run postimages

- STM32C0 postimage Git blob: `ea59d063349da59c433315d571a558ea166f7dd0`
- STM32C0 postimage SHA256: `0a54584b8873df1199268f1edb9069e9ed70a23ed08fa71cda2aeba559087b6e`
- Manifest postimage Git blob: `e5f13e0cb00273219e4d2496a616013868ed804a`
- Manifest postimage SHA256: `0a435204ac17db6f117d4adc80e7f62492025d60531305e70a3184be7a7d8308`

These values must be reproduced exactly by any later owner-approved Production write.

## Expected poststate if separately approved

- Production exact identities: **4,629 → 4,629**
- Production sources: **28 → 28**
- mapped: **4,054 → 4,059**
- no_mapping: **575 → 570**
- Active OpenOCD route: **3,975 → 3,980 / 4,550 = 87.4725%**

v6.28 does not write Production. It freezes before/after images and rollback preimages. A later write requires explicit owner approval and must reproduce the frozen postimages exactly.

No Programming Profile, erase/program/verify, Engineering Verified, or HIL claim is made.
