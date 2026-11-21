# OpenOCD Tier A Backend Promotion Proposal v6.6

**Research proposal only. Production backend mapping changes require explicit owner approval.**

v6.5 qualified **320** exact Active identities to one policy-compatible OpenOCD identifier and target config.

## Proposed transaction

Change only backend-routing fields for those 320 existing Catalog rows:

- `cmsis_device_name` when the frozen route kind is CMSIS
- `existing_identifier`
- `existing_identifier_kind`
- `mapping_status`
- `openocd_target_config`

Identity, lifecycle, package, pin count, Flash size, temperature grade, source authority and verification provenance remain unchanged.

Affected families:

- F2: 72
- F3: 168
- F7: 62
- H7: 14
- C0: 1
- L1: 1
- L4: 1
- U3: 1

## Projected state if explicitly approved

| Metric | Current | Projected |
|---|---:|---:|
| Production exact identities | 4,629 | 4,629 |
| Production sources | 28 | 28 |
| mapped | 3,673 | **3,993** |
| no_mapping | 956 | **636** |
| Active OpenOCD route | 3,594 / 4,550 | **3,914 / 4,550** |
| Active OpenOCD route coverage | 78.9890% | **86.0220%** |
| Active route gap | 956 | **636** |

## Frozen proposal provenance

- promotion exact-set SHA-256: `32ca466183a44288c903c923b20df36ad25de0824397a98625550e53e245f69e`
- promotion delta CSV SHA-256: `b6671cdd17d9e6755920bd2d69a827891b70b02b697178640de009066a796d81`
- source workflow run: `37590758341`
- artifact ID: `11469080022`
- artifact SHA-256: `e66a9882e972e6c8458fcaa18e1070ab87485a7398af248ec1f0f4e7dcf9faa9`

The frozen lock also binds the exact proposed Git blob and SHA-256 for all eight affected family CSVs.

## Critical boundary

These OpenOCD route rows are still upstream `mapping_candidate` records with `validation_status=not_verified`.

Therefore promotion to Catalog backend mapping does **not** mean:

- erase/program/verify tested
- Programming Profile resolved
- Engineering Verified
- PS/HIL verified
- production programming capability proven

v6.6 does not modify Production.
