# STM32F2 Current Active Exact Gap Lock v3.8

Research-only preparation for the next ST Device Catalog Layer-1 expansion.

## Current state

- official ST eStore current Active exact STM32F2 MPNs: **105**
- current Production STM32F2 exact ICPNs: **33**
- current Active exact gap: **72**
- current F2 Active identity coverage: **33 / 105 = 31.4286%**

The exact set is regenerated from the same frozen ST eStore v1.3 artifact that defines the project-wide **4,550 current-Active denominator**:

- workflow run: `36797087427`
- artifact: `11134202297`
- artifact ZIP SHA-256: `663d733cd6112bcffa4f7cf3d436b8a6e98ea91039e17dfb8493d8c4dbaf7d1d`

CI re-downloads that artifact, derives the F2 Active and gap sets, and byte-compares them to the committed locks.

## Exact-set locks

- 105-row Active set SHA-256:
  `60bf4cfcc07c5ec13bb11b290ea5e71da95f56f0fc4b1cdc2a05beaabe17986a`
- 72-row gap SHA-256:
  `1ba037ac5bba68ab4907742e97be0d9d56fd15f5e32b89899a67359c6703f584`

Gap distribution:

| Series | Gap |
| --- | ---: |
| STM32F205 | 35 |
| STM32F207 | 25 |
| STM32F215 | 7 |
| STM32F217 | 5 |

## Boundary

This establishes only the exact Layer-1 candidate set. It does **not** claim metadata readiness, backend/OpenOCD applicability, Programming Profile support, Engineering Verified status, field evidence, HIL qualification, or Production authorization.

## Potential coverage effect

Only if all 72 later pass metadata replay and receive explicit Production approval:

- Production exact ICPNs: **4,242 → 4,314**
- whole-ST Active intersection: **4,163 → 4,235**
- whole-ST Active gap: **387 → 315**
- whole-ST Active identity coverage: **91.4945% → 93.0769%**

## Next gate

Replay all 72 missing exact identities against official ST STM32F2 Ordering Information authority.
