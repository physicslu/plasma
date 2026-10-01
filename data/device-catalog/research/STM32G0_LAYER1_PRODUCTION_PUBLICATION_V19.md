# STM32G0 Layer-1 Production Publication v1.9

**Approved Production Catalog transaction.**

Owner approval was received for the complete v1.8 proposal: **359 current Active STM32G0 exact MPNs**.

The publication preserves the four-layer support model. Catalog identity is admitted independently from backend availability:

| State | Existing + added G0 |
| --- | ---: |
| Production exact ICPNs | **406** |
| Layer-2 mapped | **364** |
| Layer-2 `no_mapping` | **42** |
| Engineering Verified | not claimed |
| Field Evidence | not claimed |

The 42 `no_mapping` rows are valid manufacturer Active exact identities with verified ordering metadata. They carry no `existing_identifier`, no `existing_identifier_kind`, and no `openocd_target_config`. The runtime loader exposes them as `backend.mapping_status=no_mapping`; it does not synthesize a route.

## Approved effect

- STM32G0 Active identity coverage: **47/406 → 406/406 = 100%**
- Production exact total: **2,683 → 3,042**
- whole-ST current Active intersection baseline: **2,604 → 2,963**
- whole-ST Active gap baseline: **1,946 → 1,587**
- whole-ST current Active identity coverage baseline: **57.2308% → 65.1209%**

The whole-ST percentages refer to the retained 4,550-current-Active eStore audit baseline. This publication does not imply backend, engineering or field support for the 359 added identities.

## Integrity

- approved exact-set SHA-256: `a6240e4a34e3834cba7195be306d449386dcac1b3e66189f6bfac8fdc7557a5d`
- approved proposal CSV SHA-256: `5b18c64349dcdf273234b2a656ce3dee62d05d15959872753c6136c23f925ea2`
- published G0 canonical SHA-256: `48f097d7d06c1af4497fba4bc3e4b24b50bab120f4fdb98e4e584583ef90c233`
- published G0 Git blob: `48ee24d55581ebda1ac4386f1f73890b2db058a7`
