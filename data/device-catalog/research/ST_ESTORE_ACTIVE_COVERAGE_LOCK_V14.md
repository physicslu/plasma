# ST eStore Active Exact Coverage Lock v1.4

**Catalog-layer result only. No PS/backend/HIL implication and no Production write.**

The exhaustive official ST eStore audit merged in #685 establishes the current scoped STM32 MCU/wireless exact-set result:

| Metric | Result |
| --- | ---: |
| Official eStore Active exact MPNs | **4,550** |
| Plasma Production ST exact ICPNs | 2,683 |
| Production ∩ current Active | **2,604** |
| Active − Production | **1,946** |
| Current Active Catalog coverage | **57.2308%** |
| Production − current Active | 79 |
| Of those: explicitly NRND | 1 |
| Of those: not listed by eStore Active/NRND | 78 |

The correct numerator is 2,604, not 2,683. Therefore `2683 / 4550` would overstate current Active coverage.

## Family-level conclusion

The 1,946 exact Active gaps are not concentrated only in the five entirely absent families. Major gaps also exist inside already-published families.

Largest Active exact gaps:

| Family | Active exact | In current Active intersection | Missing | Coverage |
| --- | ---: | ---: | ---: | ---: |
| STM32G0 | 406 | 47 | **359** | 11.5764% |
| STM32G4 | 273 | 25 | **248** | 9.1575% |
| STM32F0 | 263 | 42 | **221** | 15.9696% |
| STM32F1 | 275 | 70 | **205** | 25.4545% |
| STM32H5 | 190 | 0 | **190** | 0% |
| STM32F3 | 192 | 10 | **182** | 5.2083% |
| STM32C5 | 172 | 0 | **172** | 0% |
| STM32F7 | 173 | 19 | **154** | 10.9827% |
| STM32F2 | 105 | 33 | **72** | 31.4286% |
| STM32WL3 | 47 | 0 | **47** | 0% |
| STM32N6 | 32 | 0 | **32** | 0% |
| STM32WB0 | 24 | 0 | **24** | 0% |

Full 28-family breakdown is retained in `st-estore-v13-family-coverage-v1.4.csv`.

## Catalog interpretation

All **1,946 `Active - Production` exact MPNs** are manufacturer-observed current **Catalog identity candidates**.

That statement is intentionally limited to Layer 1 (Device Catalog). It does **not** mean:

- Programming Backend/Profile is mapped;
- Engineering validation exists;
- Pilot/Production field evidence exists.

Those are independent support dimensions.

The 79 current Production rows outside the Active set must not be deleted automatically. One is explicitly eStore NRND; 78 are not listed in either Active or NRND and need ST Quality & Reliability lifecycle review.

## Evidence lock

Source: PR #685, workflow run `36797087427`, result artifact `11134202297`.

- Active set SHA-256: `47996537fcee11e2a9463487d430d12285cd2432b8d5c5443bcfc0544d9f1827`
- Missing Active set SHA-256: `64dc19927cb257ac3588367c92e0ccf4253995389d06e89556178fed1bc8714d`
- Result ZIP SHA-256: `663d733cd6112bcffa4f7cf3d436b8a6e98ea91039e17dfb8493d8c4dbaf7d1d`

Next gate: review/publish Catalog identity additions in bounded family batches, while lifecycle-rechecking the 79 Production-not-current-Active rows separately.
