# OpenOCD Production Bounded-Bridge Transaction v6.20

This is a **dry-run transaction package**, not a Production write.

It freezes the current Production preimages and proposed postimages for the **17 exact ICPNs** admitted to the v6.19 bounded-bridge evidence policy.

## Scope

Affected families:

- STM32F3: 4
- STM32G0: 12
- STM32L1: 1

Affected Production integrity objects:

- 3 family CSVs
- `data/device-catalog/production/icpn-v1-manifest.json`

## Expected poststate if separately approved

- Production exact identities: **4,629 → 4,629**
- Production sources: **28 → 28**
- mapped: **4,037 → 4,054**
- no_mapping: **592 → 575**
- Active OpenOCD route: **3,958 → 3,975 / 4,550 = 87.3626%**

## Transaction controls

The dry-run freezes:

- current CSV and manifest SHA-256 / Git blob preimages;
- proposed CSV and manifest postimages;
- rollback preimages;
- v6.19 exact-set and binding digests;
- a backend-fields-only mutation boundary;
- identity and commercial metadata immutability.

The only allowed CSV mutations are:

- `existing_identifier`
- `existing_identifier_kind`
- `mapping_status`
- `openocd_target_config`
- `cmsis_device_name` remains empty for this exact set.

The manifest postimage may change only to update integrity hashes for the three affected source files.

## Governance

This package does **not** authorize the Production write. A later write requires explicit owner approval and must reproduce the frozen postimages exactly.

The generic one-character rule remains unauthorized. No Programming Profile, erase/program/verify, Engineering Verified, or HIL claim is made.
