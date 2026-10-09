# OpenOCD STM32C0 Production Backend Write v6.29 — Write-Ready Gate

v6.29 is the final approval gate for the five exact STM32C0 backend mappings frozen by v6.28.

This PR is intentionally opened in **prewrite** state. It does not modify Production until the owner explicitly approves the final combined action.

## Frozen write

The only permitted data mutations are the exact v6.28 postimages:

- `data/device-catalog/research/stm32c0-commercial-icpn.csv`
  - pre blob: `c015e131082a3f9fe32ca226a9b2ada71a5c350d`
  - post blob: `ea59d063349da59c433315d571a558ea166f7dd0`
- `data/device-catalog/production/icpn-v1-manifest.json`
  - pre blob: `f3c65c166e49b107d0bd25050062f8084aeeda30`
  - post blob: `e5f13e0cb00273219e4d2496a616013868ed804a`

No alternative postimage is permitted.

## Historical compatibility

The five v6.29 rows are part of the later C0 backend evolution, while older C0 publication validators replay historical backend state. `openocd_backend_evolution_v629.py` therefore:

- accepts only a complete pre-v6.29 state or the complete frozen poststate;
- rejects partial/mixed application;
- validates the exact five post-bindings before rewinding them;
- reconstructs the historical `no_mapping` backend view without changing identity or metadata.

## Final expected state after approved write

- Production exact identities: **4,629**
- sources: **28**
- mapped: **4,059**
- no_mapping: **570**
- Active OpenOCD route: **3,980 / 4,550 = 87.4725%**

No Programming Profile, erase/program/verify, Engineering Verified, or HIL claim is made.

## Approval semantics

Once this PR is green in prewrite state, one explicit owner approval may authorize both:

1. writing the two exact frozen Production postimages; and
2. merging this PR after the postwrite CI is fully green and the final head/mergeability lease check passes.

Any content drift outside those frozen postimages or deterministic receipt/compatibility records invalidates that approval.
