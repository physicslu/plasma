# STM32L5 security-scope foundation

## Purpose

Establish a fail-closed research boundary before STM32L5 commercial identity discovery. STM32L5 was selected by the TrustZone cohort qualification because it has the smallest bounded research surface, not because programming/security support has been proven.

## Manufacturer evidence

The transaction uses ST-controlled sources only:

- STM32L5x2 product page: STM32L552 / STM32L562 and Cortex-M33 + TrustZone scope.
- ST STM32L5 TrustZone development guidance: TZEN, RDP regression, mass erase, and debug-state coupling.
- STM32CubeProgrammer 2.23.x errata: tool limitations that depend on TrustZone/TZEN state.
- STM32L5 documentation index: RM0438, DS12736, and DS12737 document locators.

These sources establish that security state is operationally relevant. They do **not** establish Plasma programming support.

## Research/runtime partition

Identity work is allowed to continue because commercial part-number discovery is a read-only catalog activity and does not require changing a target device's security state.

Allowed in the next transaction:

- manufacturer identity discovery;
- exact commercial ICPN discovery;
- read-only evidence retention and deterministic normalization.

Still blocked:

- Production admission;
- option-byte writes;
- TZEN changes;
- RDP regression;
- mass erase;
- Flash geometry or programming-algorithm claims;
- external-Flash capability claims under TZEN;
- incremental-programming capability claims under TrustZone;
- runtime/HIL support claims.

## First-principles boundary

A vendor tool limitation is evidence that the state space matters; it is not proof that every implementation has the same limitation. Therefore this transaction records the limitation as a reason to block capability claims, rather than converting it into a universal `unsupported` statement.

## Result

Status: `eligible_for_identity_discovery_under_security_fence`.

Next research gate: `stm32l5-manufacturer-identity-discovery`.
