# STM32U3 HIL observer/debug matrix readiness gate

## Purpose

Define the minimum fixture and evidence contract required before any STM32U3 security-state observer/debug HIL execution may be authorized.

This gate is **research-only**. It does not execute hardware tests, authorize runtime debug attach, mutate security state, execute OEM unlock flows, publish STM32U3 to Production, or claim programming support.

## Matrix

The readiness matrix expands deterministically to **40 HIL test cells**:

- 4 commercially observed series: STM32U375, STM32U385, STM32U3B5, STM32U3C5
- 7 logical lifecycle/security states
- 10 debug/security-context cells per commercial series
- TrustZone-enabled RDP0 / RDP0.5 / RDP1 are split into Secure and Non-secure execution contexts
- RDP2 normal debug is closed, but RDP2 is **not** modeled as unconditionally terminal
- RDP2 requires a pre-provisioned dedicated fixture; Plasma may not create RDP2 or execute OEM2 regression

STM32U335/U345/U356/U366 remain outside the physical matrix because the retained manufacturer identity evidence currently has no exact commercial ICPN for those candidate-only subfamilies. This is not an unsupported-device claim.

## Required evidence

Each future HIL result must bind fixture identity and provenance, commercial series and exact ICPN, pre-provisioned security state, execution context, probe/backend identity and versions, raw attach outcome, observed TZEN/RDP/execution state, public OEM lock/CRC metadata, timestamp, operator/automation identity, and an evidence digest.

Secret OEM key material must never be read, entered, persisted, or logged by Plasma.

Unknown, stale, inferred-only, internally inconsistent, or provenance-free observations are fail-closed.

## Readiness result

- HIL matrix plan complete: **yes**
- expanded HIL cells: **40**
- required evidence fields: **21**
- destructive/security-state creation blocked: **yes**
- RDP2 dedicated-fixture policy defined: **yes**
- public OEM metadata evidence required: **yes**
- secret OEM key material excluded: **yes**
- fixture inventory bound: **no**
- HIL execution ready: **no**
- HIL executed: **no**
- observer/debug HIL validated: **no**
- Production admission: **no**
- runtime programming support: **no**

## Exact ICPN count

**1,862** — Production catalog unchanged.

## Next gate

**STM32U3 HIL fixture inventory binding gate**

That transaction must bind real, traceable fixtures and tooling to the 40-cell plan before any physical HIL execution can be considered.
