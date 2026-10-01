# STM32G0 Layer-1 Catalog Admission Proposal v1.8

**Research proposal only. Owner approval is required before any Production Catalog write.**

The current official Active STM32G0 exact set contains 406 MPNs. Production contains 47. The previous gates established:

- 359 current Active exact gaps;
- all 359 are Layer-1 manufacturer identity candidates;
- all 359 have per-subfamily official ST Ordering Information metadata decode;
- Layer-2 OpenOCD observation: 317 `mapping_candidate`, 42 `no_mapping`.

This proposal therefore treats backend state as an independent support dimension instead of rejecting the 42 identities from the Device Catalog.

## Proposed Layer-1 transaction

If explicitly approved:

- add **359** normalized STM32G0 exact identities;
- G0 Catalog becomes **406/406 current Active exact MPNs = 100% identity coverage**;
- Production ST exact total would move **2,683 → 3,042**;
- whole-ST current Active intersection would move **2,604 → 2,963**;
- whole-ST Active exact gap would move **1,946 → 1,587**;
- whole-ST Active coverage would move **57.2308% → 65.1209%**.

Layer-2 status remains explicit:

| Backend mapping state | Exact MPNs |
| --- | ---: |
| `mapping_candidate` | 317 |
| `no_mapping` | 42 |

No Engineering Verified or field-use evidence is created by this transaction.

The CI job generates the full 359-row proposal CSV and machine-readable proposal summary as review artifacts. No canonical/Production file is modified by this PR.
