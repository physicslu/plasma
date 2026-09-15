# STM32L5 HIL observer/debug matrix readiness gate

## Purpose

Define the minimum evidence and fixture contract required before any STM32L5 security-state observer/debug HIL execution may be authorized.

This gate is **research-only**. It does not execute hardware tests, authorize debug attach, mutate security state, publish STM32L5 to Production, or claim programming support.

## Matrix

The readiness matrix contains **20 HIL test cells**:

- device lines: STM32L552, STM32L562
- logical security states: 7
- 10 cells per device line
- TrustZone-enabled RDP0 / RDP0.5 / RDP1 are split into Secure and Non-secure execution contexts where required
- RDP2 uses only pre-provisioned terminal sacrificial fixtures

Plasma is forbidden from creating RDP2, writing option bytes, regressing RDP, mass erasing, or resetting a target merely to discover security state.

## Required evidence

Each HIL result must bind fixture identity, exact commercial ICPN, pre-provisioned state, execution context, debug probe identity/firmware, backend identity/version, connection mode, raw attach result, observed TZEN/RDP/execution state, timestamp, operator/automation identity, and an evidence digest.

Unknown, stale, inferred-only, internally inconsistent, or provenance-free observations are fail-closed.

## Readiness result

- HIL matrix plan complete: **yes**
- evidence schema complete: **yes**
- destructive state creation blocked: **yes**
- fixture inventory bound: **no**
- HIL execution ready: **no**
- HIL executed: **no**
- observer/debug HIL validated: **no**
- Production admission: **no**
- runtime programming support: **no**

## Exact ICPN count

**1,862** — Production catalog unchanged.

## Next gate

**STM32L5 HIL fixture inventory binding gate**

That transaction must bind real, traceable fixtures and tooling to the 20-cell plan before any physical HIL execution can be considered.
