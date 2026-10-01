# STM32G4 Layer-1 Production Publication v2.1

**Approved Production Catalog transaction.**

Owner approval was received for the complete v2.0 proposal: **248 current Active STM32G4 exact MPNs**.

The publication preserves the four-layer support model:

| State | G4 post-state |
| --- | ---: |
| Production exact ICPNs | **273** |
| Layer-2 mapped | **272** |
| Layer-2 `no_mapping` | **1** |
| Engineering Verified | not claimed |
| Field Evidence | not claimed |

The one `no_mapping` row is `STM32G491RCY6TR`. It is an official Active exact identity with manufacturer-backed metadata but carries no synthesized OpenOCD route.

The metadata exception remains explicit and bounded:

- `STM32G484PEI6`: UFBGA121 is supported by DS12983 Rev 5 Section 6.9 because the Ordering Information table omits package code `I` for that combination.

## Approved effect

- STM32G4 Active identity coverage: **25/273 → 273/273 = 100%**
- Production exact total: **3,042 → 3,290**
- current Catalog backend partition: **3,247 mapped / 43 no_mapping**
- whole-ST current Active intersection baseline: **2,963 → 3,211**
- whole-ST Active gap baseline: **1,587 → 1,339**
- whole-ST current Active identity coverage baseline: **65.1209% → 70.5714%**

The whole-ST percentage retains the 4,550-current-Active eStore denominator locked by PR #685. This transaction does not claim programming readiness, Engineering Verified, field use, or PS/HIL qualification.

## Integrity

- approved exact-set SHA-256: `d6b7f8dbec3869b9e71d414773305b2d7bc2d9a57eb7a2987a8114f14b5bd270`
- approved proposal CSV SHA-256: `97d1c2725a45decfb4c0c43cb54e68c23e4c6e2b18e0452d7d8f51a47cb51be1`
- approved authority SHA-256: `9e8fb79ac60372c3caf4066d15a597ad8953a9043e18a70dcad98a85899c8d7a`
- published G4 canonical SHA-256: `e1d2b369e02560d52d56a91c230eef2cc65b93394a2cfdb41915d5b5407cb2fd`
- published G4 Git blob: `83a7e6f20256ca10e6fb1c3452bca8c5b9e39f56`
