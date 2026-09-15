# STM32U3 runtime-enforcement admission gate

## Scope

This research-only gate converts the merged STM32U3 security-state model into an explicit runtime execution boundary. It does not enable programming, debug attach, OEM-key operations, security mutation, HIL, or Production admission.

## Plane separation

Allowed host-only control-plane operations:

- `catalog_resolve`
- `metadata_resolve`
- `route_resolve`

These operations perform no device I/O.

Modeled target-plane operations: **15**. Every target-plane decision remains `deny` across all **7** lifecycle states, yielding **105 / 105 deny** decisions.

## STM32U3-specific OEM boundary

STM32U3 differs materially from the earlier STM32L5 model:

- RDP2 closes normal debug but is **not** modeled as unconditionally terminal.
- RDP2 regression remains conditional on a previously provisioned/activated OEM2 mechanism and successful authentication.
- OEM1/OEM2 provisioning and lock state are orthogonal security inputs.
- Unknown or unobserved OEM state fails closed.
- OEM key material is not accepted, persisted, or logged by this runtime contract.
- OEM provisioning and OEM unlock execution remain blocked.

This gate therefore does not infer RDP2 reversibility from lifecycle state alone.

## Fail-closed invariants

- unknown operation => deny
- unknown/unobserved lifecycle state => deny
- unknown/unobserved OEM state for OEM-dependent decisions => deny
- no force or bypass override
- control plane cannot touch the target
- all 15 target operations remain denied
- all security/OEM mutations remain denied
- RDP2 normal debug remains denied without falsely declaring the state terminal

## Admission result

- runtime enforcement contract defined: **yes**
- control/target plane separation defined: **yes**
- lifecycle observation required before target operation: **yes**
- OEM observation policy fail-closed: **yes**
- security-state observer validated: **no**
- OEM-state observer validated: **no**
- backend enforcement integrated: **no**
- target-touching operation authorized: **no**
- Production admission: **no**
- runtime programming: **no**
- OEM key operation: **no**
- HIL validated: **no**

## Negative controls

The validator rejects fail-open mutations including Flash-program allow, force override, unknown lifecycle/OEM state allow, false terminal RDP2 semantics, OEM key logging, OEM unlock execution, and premature Production admission.

## Next gate

`stm32u3-security-state-observer-and-debug-validation-gate`

## Production invariant

**Exact ICPN count: 1,862**, unchanged.
