# STM32 TrustZone cohort Gate 1 qualification

## Purpose

Open a bounded research/governance transaction for the TrustZone STM32 cohort after the standard non-wireless cohort was exhausted.

Candidates are limited to `STM32L5`, `STM32U3`, and `STM32U5`, which the frozen cross-family inventory already classifies as `trustzone_requires_security_scope`.

## Deterministic qualification

A candidate must retain all of the following properties in the frozen inventory:

- TrustZone cohort classification;
- structural gate pass;
- complete mapping metadata;
- exactly one target config;
- at least one ordering-pattern row.

Eligible candidates are ranked lexicographically by research-surface complexity, not by an arbitrary weighted score:

1. subfamily count ascending;
2. inventory row count ascending;
3. ordering-pattern row count ascending;
4. series name ascending as deterministic tie-breaker.

Result:

| Rank | Series | Subfamilies | Inventory rows | Ordering-pattern rows | Target config |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | STM32L5 | 1 | 38 | 15 | `tcl/target/stm32l5x.cfg` |
| 2 | STM32U3 | 8 | 171 | 75 | `tcl/target/stm32u3x.cfg` |
| 3 | STM32U5 | 12 | 162 | 63 | `tcl/target/stm32u5x.cfg` |

`STM32L5` is therefore selected only as the next family for bounded security-scope research.

## Authority boundary

This transaction is **research-only**. It does not modify `data/device-catalog/production/` and does not assert any of the following:

- Production admission;
- programming-algorithm equivalence;
- Flash geometry validation;
- TrustZone/security semantic support;
- option-byte semantic support;
- HIL validation;
- runtime programming support.

A later STM32L5 foundation/security-scope transaction must establish those research prerequisites independently before any discovery/admission/publication sequence can be considered.
