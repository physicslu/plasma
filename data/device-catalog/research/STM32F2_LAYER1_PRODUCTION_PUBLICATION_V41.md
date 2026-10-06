# STM32F2 Layer-1 Production Publication v4.1

**Owner approval received. This publication expands Device Catalog Layer-1 only.**

## Approved proposal

The publication consumes merged proposal #722 (`stm32f2-layer1-admission-proposal-v4.0`).

Approved locks:

- additions: **72 exact MPNs**
- addition exact-set SHA-256: `1ba037ac5bba68ab4907742e97be0d9d56fd15f5e32b89899a67359c6703f584`
- proposal CSV SHA-256: `8bd6dce8d0e6f1d976a7708ac7afef785d214797567c12ef6a56bbc63d31e2a3`
- metadata authority SHA-256: `b4dbee7bc5c22d9b4d472637af9d32fdb54c22fb5e554a3e817db4ec716b4abd`

## Production transaction

- STM32F2 exact ICPNs: **33 → 105**
- canonical SHA-256: `c2e07ea181b88cfeca2772e7d0c4b00d1a0529805e5e82f3d9af8a7a981de5b6`
- canonical Git blob: `15072e5a816f1749cd476aa85c6d27b94ae4aa74`
- Production exact total: **4,242 → 4,314**
- Production source count: **24 → 24**

## Layer separation

The original 33 STM32F2 rows retain their deterministic OpenOCD route to `tcl/target/stm32f2x.cfg`.

The newly published 72 rows remain:

- backend mapping state: **`no_mapping`**
- backend scope evaluated: **false**
- OpenOCD target config: empty
- Programming Profile applicability: unresolved
- Engineering Verified: not claimed
- field evidence: not claimed
- PS/HIL qualification: not claimed

After publication:

| State | Exact ICPNs |
| --- | ---: |
| mapped | 3,673 |
| `no_mapping` | 641 |
| total | 4,314 |

## Coverage effect

- STM32F2 current Active identity coverage: **105 / 105 = 100%**
- whole-ST current Active intersection: **4,163 → 4,235 / 4,550**
- whole-ST current Active gap: **387 → 315**
- whole-ST Active identity coverage: **91.4945% → 93.0769%**
