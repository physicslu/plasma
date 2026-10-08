# OpenOCD Route-Inventory Authority Review v6.24

Research-only authority review for the seven C0/L4 exact ICPNs separated from the remaining v6.23 A residual.

## Result

### STM32C0 — 5 exact ICPNs

The locked official ST `STM32_open_pin_data` MCU tree contains exact-base pattern authority:

- `STM32C011D6Yx.xml`
- `STM32C051D8Yx.xml`
- `STM32C091ECYx.xml`
- `STM32C092ECYx.xml`

These four authoritative patterns cover the five C0 exact ICPNs in scope. They are eligible for a **bounded canonical route-inventory expansion proposal**. This review does not itself modify the canonical inventory.

### STM32L4 — 2 exact ICPNs

The same official ST source lock contains `STM32L496WGYxP.xml`. DS11585 Rev 20 p274 and the locked L4 ordering grammar independently confirm:

- W = 115 pins
- Y = WLCSP
- temperature code 6 = -40..85 C
- `PTR` and `PST` are valid L496 tails

However the route pattern cannot be admitted yet:

- `STM32L496WGY6PTR`: after removing terminal `TR`, the core `STM32L496WGY6P` matches `STM32L496WGYxP`, but the current L4 prefix resolver only consumes patterns ending in `x`.
- `STM32L496WGY6PST`: requires an additional bounded suffix transform preserving the authoritative `P` route shape before the non-terminal-`x` pattern can be consumed.

Therefore the two L4 identities remain blocked from route-inventory promotion.

## Governance

This review does not authorize:

- canonical inventory modification;
- a generic pattern rule;
- an L4 resolver policy change;
- an L496 suffix transform;
- a Production write;
- Programming Profile binding;
- erase/program/verify, Engineering Verified, or HIL status.

The G4 ambiguity `STM32G491RCY6TR` remains outside this v6.24 scope.
