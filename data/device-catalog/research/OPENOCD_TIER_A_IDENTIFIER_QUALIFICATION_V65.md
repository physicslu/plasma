# OpenOCD Tier A Identifier Qualification v6.5

This is a research-only qualification of the **389** Tier A route candidates from v6.4.

## Qualification rule

A candidate is identifier-qualified only if the existing family admission-policy semantics produce exactly **one** compatible row from `openocd-parts-canonical.csv`.

The route inventory is pinned to Git blob:

`0ef056e3363e20bb527590c4a4cc1cc0d7afb810`

Only rows with all of the following are eligible:

- STMicroelectronics
- `upstream-openocd`
- `mapping_candidate`
- `validation_status=not_verified`
- target config equal to the v6.4 same-series candidate target
- identifier kind allowed by the existing family policy

## Result

- Tier A input: **389**
- identifier-qualified: **320**
- blocked: **69**
- ambiguous: **0**

Qualified identifier kinds:

- `ordering_pattern`: **307**
- `cmsis_device_name`: **13**

### Blocked partition

- STM32G0: **42**
- STM32C0: **16**
- STM32F3: **4**
- STM32F4: **3**
- STM32L4: **2**
- STM32G4: **1**
- STM32L1: **1**

These rows stay fail-closed. In particular, opaque F4 `V/W` suffixes are not collapsed into an existing identifier.

## Frozen qualification provenance

- qualified exact-set SHA-256: `32ca466183a44288c903c923b20df36ad25de0824397a98625550e53e245f69e`
- blocked exact-set SHA-256: `d1b2d9bebc71ba10160c422b4e4c76367ea21f9419618c40ccffc7e543b5c4c6`
- qualified CSV SHA-256: `b74136d7a9ede1671ac0174425e84904dc1f355ad9307b9ee0a1ddaa052e5d6e`
- blocked CSV SHA-256: `ac28754afab3e17f4cd71e4b55f41d79577ff67cc62a1632c9b672648ece6b17`
- source workflow run: `37590248210`
- artifact ID: `11467978681`
- artifact SHA-256: `818d603070d314ce136a5642d5a304e3734fd40f6bf9d6d4474ef29840d2fcb8`

## Coverage implication

Current OpenOCD Active route coverage:

**3,594 / 4,550 = 78.9890%**

If the 320 identifier-qualified rows later pass a separate backend promotion gate:

**3,914 / 4,550 = 86.0220%**

Remaining gap: **636**.

This v6.5 qualification does **not** change Production, does not create a Programming Profile, and does not claim erase/program/verify or HIL success.
