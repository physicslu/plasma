# STM32U5 security-state observer and debug validation gate

## Scope

This transaction defines the read-only observer/debug contract above the merged STM32U5 runtime-enforcement gate. It is **research-only** and does not authorize target access.

## Identity boundary

- retained exact identities: 266
- Active canonical identities: 265
- quarantined Preview identity: `STM32U5G9ZJJ3Q`
- Production exact ICPNs: 2,017, unchanged

## Passive observer contract

Debug classification requires a fresh observed tuple:

1. TZEN state
2. RDP level
3. CPU secure/nonsecure execution state
4. debug-attach outcome

Unknown, inferred-only, or stale observations fail closed. Observation-cache reuse is not authorized. The observer may not reset or mutate the target, write option bytes, regress RDP, execute OEM unlock, or mass erase merely to discover state.

## OEM boundary

Only OEM state metadata is modeled: OEM1/OEM2 provisioning/key-state classification and lock state. Secret OEM key material may not be read, accepted as input, persisted, or logged. Public metadata never proves successful OEM authentication and cannot by itself authorize an OEM transition.

## Debug expectation matrix

Seven lifecycle states are modeled:

- `TZ0_RDP0`: debug class `open`, but runtime attach is still unauthorized.
- `TZ0_RDP1`: exact debug behavior remains `requires_runtime_validation`.
- `TZ0_RDP2`: normal debug `none`; RDP2 is not modeled unconditionally terminal.
- `TZ1_RDP0`: upstream model says open, but runtime behavior remains unvalidated and execution-state observation is required.
- `TZ1_RDP0_5`: execution-state-conditioned; secure and nonsecure outcomes both remain `unknown_requires_hil`.
- `TZ1_RDP1`: execution-state-conditioned; secure and nonsecure outcomes both remain `unknown_requires_hil`.
- `TZ1_RDP2`: normal debug `none`; conditional lifecycle exit still requires verified OEM2 semantics.

The key difference from the STM32U3 gate is deliberate: the U3-specific nonsecure-debug conclusions are **not** imported into STM32U5 without U5-specific evidence and HIL validation.

## Validation boundary

This gate validates only the deterministic/offline contract. It does not claim:

- hardware observation executed
- HIL debug matrix executed
- OpenOCD or ST-LINK behavior validated
- OEM2 authentication path validated
- backend state enforcement integrated
- programming algorithm or Flash geometry validated
- security mutation validated
- runtime programming or debug enabled
- Production catalog admission

## Fail-closed negative controls

Permanent validation rejects twelve fail-open mutations, including unknown-state allow, stale-cache reuse, RDP2 debug enablement, terminal RDP2 semantics, falsely resolved RDP0.5/RDP1 debug behavior, unknown OEM allow, secret-key read, observer-only OEM transition authorization, premature HIL claims, Preview quarantine removal, and premature Production admission.

## Next gate

`stm32u5-hil-observer-debug-matrix-readiness-gate`
