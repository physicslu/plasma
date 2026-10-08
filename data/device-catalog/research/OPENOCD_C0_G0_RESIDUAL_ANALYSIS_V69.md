# OpenOCD C0/G0 Residual Analysis v6.9

Research-only analysis of the largest remaining Tier A residual block:

- STM32C0: **16**
- STM32G0: **12**
- total: **28 / 36** Tier A residual identities

The analysis distinguishes whether each row is blocked because:
1. route inventory exists for the same base but current policy shape does not match;
2. the series exists but the base variant is absent;
3. the series itself is absent from the canonical route inventory.

No identifier is invented, no route inventory is changed, and no Production mapping is modified.
