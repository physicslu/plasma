# OpenOCD Production Backend-Mapping Transaction v6.15

This is a **dry-run transaction package**, not a Production write.

It freezes the exact Production preimages and proposed postimages for the 364 backend-routing promotions already qualified by v6.14.

## Scope

Affected families: **10**

- STM32C0
- STM32F2
- STM32F3
- STM32F4
- STM32F7
- STM32G0
- STM32H7
- STM32L1
- STM32L4
- STM32U3

Expected backend partition if later explicitly approved:

- mapped: **3,673 → 4,037**
- no_mapping: **956 → 592**
- Active OpenOCD route: **3,594 → 3,958 / 4,550 = 86.9890%**

## Transaction controls

The package freezes:

- current Production file preimage SHA-256 and Git blob SHA;
- proposed postimage SHA-256 and Git blob SHA;
- rollback preimages;
- v6.14 exact-set, binding, and delta hashes.

A later Production-write PR must reproduce these hashes exactly. Any drift in source files, mappings, or cardinality must fail closed and require a fresh qualification.

## Governance

This PR does **not** modify Production CSVs and does **not** authorize a Production write.

No Programming Profile, erase/program/verify, Engineering Verified, or HIL claim is made.
