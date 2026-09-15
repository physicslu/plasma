# STM32L5 security-state observer and debug validation gate

## Purpose

Define a fail-closed observation contract for STM32L5 security state and a manufacturer-evidence-backed debug expectation matrix without claiming HIL or runtime support.

## Evidence boundary

Manufacturer authority is STMicroelectronics only. Current evidence binds to RM0438 Rev 8, ST TrustZone disable guidance, and ST RDP security guidance.

Key constraints:

- RDP0.5 exists only with TrustZone enabled.
- TrustZone-enabled RDP0.5 and RDP1 debug availability depends on secure vs non-secure CPU execution state.
- Secure execution at TrustZone-enabled RDP0.5/RDP1 must be treated as debug-connect denied.
- RDP2 has no debug and is terminal for this policy.
- ST's documented RDP1 development procedure uses hot-plug; this is retained as evidence, not generalized into a Plasma runtime capability claim.

## Observer contract

A target-touching operation may never rely on catalog identity or static assumptions alone. The observer contract requires these dimensions:

1. TZEN state
2. RDP level
3. CPU security execution state
4. debug attach outcome

Unknown, stale, inferred-only, or partially observed security state remains deny. Observation caching is not authorized.

Observation itself may not mutate state. Reset, option-byte writes, RDP regression, mass erase, or any other security transition are forbidden as a means of discovering state.

## Debug matrix

The seven security states from the prior gate are covered exactly once. Every row keeps `runtime_debug_attach_authorized=false`.

This transaction validates the contract and expectation matrix only. It does **not** execute JTAG/SWD, ST-LINK, OpenOCD, option-byte reads/writes, Flash access, or a physical HIL matrix.

## Admission result

- observer contract defined: **yes**
- seven-state debug expectation matrix complete: **yes**
- unknown/stale state fail-closed: **yes**
- security mutation for observation blocked: **yes**
- observer HIL validated: **no**
- debug attach HIL validated: **no**
- backend enforcement integrated: **no**
- Production admission: **no**
- runtime programming: **no**

## Exact ICPN count

Production is untouched by this transaction: **1,862 exact ICPNs**.

## Next gate

**STM32L5 HIL observer/debug matrix readiness gate**

That transaction should define the fixture, probe/backend, target samples, exact non-destructive test matrix, evidence capture format, and abort criteria required before any physical debug-state validation is attempted.
