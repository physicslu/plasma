# STM32H5 Layer-1 Catalog Admission Proposal v2.8

**Research proposal only. Owner approval is required before any Production Catalog write.**

The previous STM32H5 gates established:

- current official Active exact set: **190 MPNs**;
- deterministic structural crosswalk: **190/190**;
- metadata authority replay: **190/190**;
- direct Ordering Information decode: **187**;
- exact-identity-bounded ST exception: **3**;
- current Plasma OpenOCD backend state: **190 `no_mapping`**.

This proposal treats Device Catalog identity/metadata as Layer-1 and backend support as an independent Layer-2 dimension. It does not synthesize an STM32H5 programming route.

## Proposed Layer-1 transaction

If explicitly approved for Production publication:

- add **190** normalized STM32H5 exact identities;
- H5 Catalog identity coverage becomes **190/190 current Active = 100%**;
- Production ST exact total would move **3,716 → 3,906**;
- whole-ST current Active intersection would move **3,637 → 3,827**;
- whole-ST Active exact gap would move **913 → 723**;
- whole-ST Active identity coverage would move **79.9341% → 84.1099%**.

Layer-2 remains unchanged:

| Backend mapping state | Exact MPNs |
| --- | ---: |
| `mapping_candidate` | 0 |
| `no_mapping` | 190 |

No Programming Profile applicability, Engineering Verified, field evidence, PS/HIL qualification, or Production authorization is created by this proposal.

## Metadata exception boundary

The only bounded metadata exceptions remain:

- `STM32H5E4ZJJ6`
- `STM32H5E4ZJJ7Q`
- `STM32H5E4ZKJ6`

These exact identities use the official ST Quality & Reliability row to resolve package code `J`, which is omitted from the DS14971 Rev 1 Ordering Information package table. This does not globally authorize package code `J` for STM32H5E.

## Review artifact

CI generates:

- the complete 190-row proposal CSV;
- the machine-readable proposal summary;
- deterministic SHA-256 locks for the candidate exact set, generated CSV, and authority file.

No canonical Production Catalog file is modified by this PR.
