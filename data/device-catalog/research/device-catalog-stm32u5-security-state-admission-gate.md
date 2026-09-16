# STM32U5 security-state admission gate

## Scope

This research-only gate freezes the STM32U5 security-state model that must exist before any runtime observer, debug, programming, erase, option-byte, RDP, or OEM-key path can be considered.

It inherits the merged canonical admission plan:

- retained exact identities: **266**;
- Active canonical identities: **265**;
- quarantined Preview identity: **1** (`STM32U5G9ZJJ3Q`);
- Production exact ICPNs: **2,017**, unchanged.

No Production catalog write is performed by this gate.

## First-principles boundary

A catalog route answers **which target family/configuration an exact identity maps to**. It does not answer **whether a concrete device is safe to attach, read, program, erase, regress, unlock, or mutate in its current security state**.

STM32U5 therefore needs an explicit lifecycle model over:

- TrustZone enablement (`TZEN`);
- RDP levels `0`, `0.5`, `1`, and `2`;
- secure/nonsecure execution context where relevant;
- OEM1/OEM2 provisioning and lock state;
- debug-access consequences;
- destructive transition boundaries.

## Frozen lifecycle states

Seven lifecycle states are admitted for reasoning:

- `TZ0_RDP0`
- `TZ0_RDP1`
- `TZ0_RDP2`
- `TZ1_RDP0`
- `TZ1_RDP0_5`
- `TZ1_RDP1`
- `TZ1_RDP2`

RDP `0.5` is valid only with TrustZone enabled.

RDP2 is **not modeled as unconditionally terminal**. Normal debug is closed, while the only modeled conditional exit is RDP2 -> RDP1 through a verified OEM2 unlocking mechanism. Execution remains blocked.

## Deliberately unresolved RDP1 regression semantics

The merged STM32U5 security foundation establishes that OEM key provisioning/lock state affects RDP regression policy, but it does not provide enough frozen authority to claim one exact OEM1/OEM2 rule for every RDP1 regression target.

Accordingly this gate does **not** copy the more specific STM32U3 transition model.

`RDP1 -> lower protection` remains:

- modeled as a possible lifecycle boundary;
- dependent on observed OEM1/OEM2 state;
- potentially destructive;
- `unresolved_fail_closed`;
- blocked from execution.

This is intentional. Missing semantics are not converted into an implementation rule.

## OEM-key governance

OEM key material must never be stored or logged by catalog admission logic. Provisioning and lock state must be observed before any future regression decision. Unknown OEM state is deny-by-default.

The gate does not authorize:

- OEM1/OEM2 key provisioning;
- OEM unlock execution;
- RDP mutation or regression;
- TrustZone mutation;
- option-byte writes;
- mass erase.

## Runtime boundary

The following remain blocked:

- security-state reads until a bounded observer contract exists;
- debug attach until state-aware enforcement exists;
- flash read until state-aware enforcement exists;
- flash program/verify/erase until programming algorithm, Flash geometry, and security-state behavior are validated;
- all destructive security mutations.

The canonical identity plan remains valid, but catalog membership does not authorize execution.

## Negative controls

Permanent validation rejects at least these fail-open mutations:

1. treating RDP2 as unconditionally terminal;
2. removing the OEM2 prerequisite from RDP2 regression;
3. inventing RDP0.5 without TrustZone;
4. falsely marking the unresolved RDP1 regression semantics as validated;
5. allowing OEM2 provisioning;
6. treating unknown OEM state as acceptable;
7. opening Production admission.

## Result

The security-state **admission model** is complete enough to define a fail-closed runtime boundary. This does not mean all security transitions are semantically validated.

Production remains **2,017** exact ICPNs. The Preview identity remains quarantined.

## Next gate

`stm32u5-runtime-enforcement-admission-gate`

That gate may design an observer/enforcement contract, but may not infer device security state, enable destructive operations, or claim HIL without separate evidence.
