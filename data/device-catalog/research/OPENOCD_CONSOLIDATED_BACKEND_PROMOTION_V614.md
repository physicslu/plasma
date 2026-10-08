# OpenOCD Consolidated Backend-Promotion Proposal v6.14

Research-only consolidation of three independently frozen Tier A routing authorities:

- v6.5 identifier qualification: **320**
- v6.13 bounded Catalog-suffix normalization: **33**
- v6.12 bounded STM32C0 identifier bridge: **11**

Total proposed backend-routing updates: **364 exact ICPNs**.

## Transaction boundary

If later explicitly approved, v6.14 changes only backend-routing fields:

- `cmsis_device_name` when the frozen identifier kind is CMSIS
- `existing_identifier`
- `existing_identifier_kind`
- `mapping_status`
- `openocd_target_config`

It does not change exact identity, lifecycle, package, pin count, Flash size, temperature grade, source authority, or manufacturer metadata.

The proposal requires all 364 current Production rows to still be `no_mapping` with empty backend-binding fields. Any prestate drift fails closed.

## Expected projection

| Metric | Current | If later approved |
|---|---:|---:|
| Production exact identities | 4,629 | 4,629 |
| Production sources | 28 | 28 |
| mapped | 3,673 | **4,037** |
| no_mapping | 956 | **592** |
| Active OpenOCD route | 3,594 / 4,550 | **3,958 / 4,550** |
| Active route coverage | 78.9890% | **86.9890%** |

## Governance

This PR is a proposal generator only.

It does **not**:

- modify Production CSVs;
- authorize a Production write;
- claim Programming Profile resolution;
- claim erase/program/verify success;
- claim Engineering Verified;
- claim HIL qualification.

The upstream OpenOCD route evidence remains a routing capability observation, not proof of complete programming semantics.
