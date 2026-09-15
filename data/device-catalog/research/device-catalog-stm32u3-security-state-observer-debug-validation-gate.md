# STM32U3 security-state observer and debug validation gate

## Scope

This research-only gate defines the passive observer contract and the expected debug-access matrix for STM32U3. It does **not** enable debug attach, programming, OEM-key operations, security mutation, HIL execution, or Production admission.

## Observer contract

Debug classification requires fresh, directly observed values for:

- `tzen_state`
- `rdp_level`
- `cpu_security_execution_state`
- `debug_attach_outcome`

Unknown, inferred-only, or stale state is not sufficient for target enablement. Observation-cache reuse is not authorized. The observer may not mutate security state, reset the device for observation, write option bytes, regress RDP, execute OEM unlock, or mass erase.

## STM32U3 OEM boundary

STM32U3 requires a stricter distinction than STM32L5:

- RDP2 closes normal debug but is **not** unconditionally terminal.
- RDP2 -> RDP1 remains conditional on a previously provisioned and active OEM2 mechanism plus successful authentication.
- Public observer metadata may include OEM1/OEM2 lock state and public CRC status.
- Secret OEM key material is never read, accepted, persisted, or logged by this contract.
- Public OEM metadata alone does not prove authentication success and cannot authorize an OEM transition.
- Unknown OEM state fails closed.

## Debug expectation matrix

Seven lifecycle states are modeled:

- `TZ0_RDP0`: open debug class; runtime attach still unauthorized.
- `TZ0_RDP1`: conditioned nonsecure debug class; runtime attach still unauthorized.
- `TZ0_RDP2`: normal debug none; not modeled terminal; OEM2-conditional lifecycle exit remains separate.
- `TZ1_RDP0`: secure/nonsecure debug class with the documented RSS exception; runtime attach still unauthorized.
- `TZ1_RDP0_5`: nonsecure-only; secure execution attach expected deny; nonsecure attach remains HIL-gated.
- `TZ1_RDP1`: conditioned nonsecure; secure execution attach expected deny; nonsecure attach remains HIL-gated.
- `TZ1_RDP2`: normal debug none; not modeled terminal; OEM2-conditional lifecycle exit remains separate.

These are manufacturer-derived expectations, not measured Plasma behavior.

## Validation boundary

This gate performs offline contract validation only. It does not claim:

- hardware observation executed
- HIL debug matrix executed
- OEM-state observer HIL validation
- OpenOCD or ST-Link debug behavior validation
- OEM2 authentication-path validation
- programming-algorithm validation
- flash-geometry validation
- security-mutation validation

## Negative controls

The validator rejects fail-open mutations including unknown-state allow, stale-cache reuse, RDP2 debug enablement, false terminal RDP2 semantics, secure attach at TrustZone/RDP1, unknown OEM state allow, secret-key read enablement, observer-only OEM transition authorization, premature HIL claims, and premature Production admission.

## Next gate

`stm32u3-hil-observer-debug-matrix-readiness-gate`

## Production invariant

**Exact ICPN count: 1,862**, unchanged.
