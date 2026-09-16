# STM32U5 HIL observer/debug matrix readiness gate

## Scope

Freeze the hardware-in-the-loop readiness contract for STM32U5 security-state observation and debug behavior. This transaction is research-only. It does not execute HIL, enable runtime debug, authorize programming, mutate security state, or write the Production catalog.

## Upstream boundary

- Active exact ICPNs: **265**
- quarantined Preview identity: `STM32U5G9ZJJ3Q`
- Active subfamilies: **12**
- Production exact ICPNs: **2,017**, unchanged
- upstream observer/debug gate: `stm32u5-security-state-observer-and-debug-validation-gate`
- canonical target config: `tcl/target/stm32u5x.cfg`

## Matrix design

All 12 Active-observed STM32U5 subfamilies are included:

`STM32U535`, `STM32U545`, `STM32U575`, `STM32U585`, `STM32U595`, `STM32U599`, `STM32U5A5`, `STM32U5A9`, `STM32U5F7`, `STM32U5F9`, `STM32U5G7`, `STM32U5G9`.

Each subfamily expands across 10 security/debug context templates:

- TZ0/RDP0
- TZ0/RDP1
- TZ0/RDP2
- TZ1/RDP0 secure
- TZ1/RDP0 nonsecure
- TZ1/RDP0.5 secure
- TZ1/RDP0.5 nonsecure
- TZ1/RDP1 secure
- TZ1/RDP1 nonsecure
- TZ1/RDP2

This gives a deterministic readiness matrix of **120 planned HIL cells**. A cell is a required evidence scenario, not a requirement for a dedicated physical IC. Physical fixture assignment is deliberately deferred to `stm32u5-hil-fixture-inventory-binding-gate`.

## U5-specific unresolved semantics

The readiness matrix preserves the merged U5 uncertainty boundary. RDP0.5 secure/nonsecure attach behavior and RDP1 debug behavior remain `unknown_requires_hil`; this gate must not convert those unknowns into allow/deny conclusions before physical evidence exists.

RDP2 normal debug remains closed, but RDP2 is not modeled as unconditionally terminal. RDP2 cells require a pre-provisioned dedicated fixture. Plasma and the test harness may not create RDP2, regress RDP2, execute OEM2 unlock, write option bytes, mass erase, or reset merely to discover state.

## Evidence contract

Each HIL cell requires 22 evidence fields, including fixture identity/provenance, exact Active ICPN and subfamily, pre-provisioned state, execution context, probe/backend identity and versions, canonical target config, raw attach result, observed TZEN/RDP/execution state, observed public OEM1/OEM2 provisioning and lock state, timestamp, actor identity, and evidence digest.

Secret OEM key material is explicitly outside the evidence model: no read, input, persistence, or logging is allowed.

## Stop conditions

Execution must stop if fixture provenance disagrees with observed state, required OEM metadata is unknown, a destructive/security transition would be required, the exact ICPN is missing or Preview, target config drifts from `tcl/target/stm32u5x.cfg`, probe/backend identity is unknown, evidence is stale or inferred-only, or secret OEM key material would be required.

## Readiness result

This gate establishes that the matrix plan and evidence schema are complete. It does **not** establish that fixtures exist, HIL can run, debug behavior has been validated, backend enforcement is integrated, programming is supported, or Production admission is authorized.

Expected result:

- matrix plan complete: `true`
- 12 Active subfamilies covered: `true`
- planned HIL cells: **120**
- fixture inventory bound: `false`
- HIL execution ready: `false`
- HIL executed: `false`
- observer/debug HIL validated: `false`
- runtime programming authorized: `false`
- Production admission authorized: `false`

## Next gate

`stm32u5-hil-fixture-inventory-binding-gate`
