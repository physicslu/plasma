# STM32U3 security-scope foundation

## Purpose

Establish a fail-closed research boundary before STM32U3 commercial identity discovery. STM32U3 is the rank-2 TrustZone cohort candidate and became the next software-only research target only because STM32L5 is paused on an external physical-HIL dependency. This transaction does not infer programming support from that succession decision.

## Manufacturer evidence

Official ST evidence used by this transaction:

- STM32U3 product selector: Arm Cortex-M33 + TrustZone family scope.
- STM32U3 documentation index: RM0487 and family datasheet/security-document authority.
- RM0487: RDP levels 0/0.5/1/2, security-state-dependent debug behavior, and optional password-based RDP regressions.
- ST `RDP for STM32U3` guidance: OEM1/OEM2 key and lock semantics that affect permitted RDP regressions.

These sources establish that STM32U3 security state has more dimensions than only `TZEN + RDP`.

## Critical U3/L5 semantic difference

STM32U3 RDP level 2 must **not** be copied from the STM32L5 model as an unconditional terminal state.

For STM32U3, normal debug is closed at RDP2, but an RDP2-to-RDP1 regression can be authorized when the OEM2 unlocking mechanism was provisioned/activated beforehand. Conversely, without that mechanism, the regression is not granted. Therefore any future STM32U3 runtime model must include the relevant OEM key/lock state and must fail closed when that state is unknown.

Plasma does not infer OEM key state and does not provision or execute OEM unlock flows in this foundation gate.

## Research/runtime partition

Allowed next:

- manufacturer identity discovery;
- exact commercial ICPN discovery;
- read-only evidence retention and deterministic normalization.

Still blocked:

- Production admission;
- option-byte writes;
- OEM1/OEM2 key provisioning;
- OEM unlock execution;
- TZEN/RDP mutation or regression;
- mass erase;
- Flash geometry and programming-algorithm claims;
- debug-attach support claims;
- runtime programming;
- HIL claims.

## Result

Status: `eligible_for_identity_discovery_under_security_fence`.

Next research gate: `stm32u3-manufacturer-identity-discovery`.

No Production catalog write is authorized by this transaction.

**Exact ICPN count: 1,862.**
