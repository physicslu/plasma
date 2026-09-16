# STM32U5 runtime-enforcement admission gate

## Transaction

`stm32u5-runtime-enforcement-admission-gate`

Authority: `research_only`.

This gate defines the runtime decision boundary above the merged STM32U5 security-state model. It does **not** enable device programming, debug, erase, option-byte mutation, RDP mutation, OEM-key operations, or HIL claims.

## Upstream identity boundary

- retained exact identities: 266
- Active canonical identities: 265
- quarantined Preview identity: `STM32U5G9ZJJ3Q`
- Production exact ICPNs: 2,017, unchanged

The Preview identity remains outside runtime admission scope.

## Plane separation

Three host-only control-plane operations are admitted:

- `catalog_resolve`
- `metadata_resolve`
- `route_resolve`

All three have `device_io=false`.

Fifteen target-plane operations are modeled. Across seven lifecycle states this produces a 105-decision matrix. The required result for this gate is **105 / 105 DENY**.

## Runtime fail-closed rules

- default decision: deny
- unknown operation: deny
- unknown or unobserved lifecycle state: deny
- unknown or unobserved OEM state for OEM-dependent decisions: deny
- force/bypass override: unsupported
- control plane may not touch target
- target operations require an observed lifecycle state
- OEM-dependent operations require observed OEM metadata
- OEM key material input, persistence, and logging are prohibited

## STM32U5-specific regression boundary

The merged security-state gate intentionally leaves exact RDP1 lowering semantics unresolved. This runtime gate preserves that uncertainty rather than converting it into a permissive rule.

For `TZ0_RDP1` and `TZ1_RDP1`:

`rdp_regression -> DENY / rdp1_regression_semantics_unresolved_fail_closed`

For RDP2 states, normal debug remains closed. RDP2 -> RDP1 is modeled only as a conditional OEM2-dependent path and remains runtime-unauthorized:

`rdp_regression -> DENY / rdp2_conditional_regression_not_authorized`

RDP2 is therefore not modeled as unconditionally terminal, but no regression execution is authorized.

## Target-plane operations

All remain denied:

- `read_security_state`
- `debug_attach`
- `flash_read`
- `flash_program`
- `flash_verify`
- `flash_erase`
- `option_byte_write`
- `tzen_change`
- `rdp_change`
- `rdp_regression`
- `oem1_key_provision`
- `oem2_key_provision`
- `oem_unlock_execute`
- `mass_erase`
- `enter_rdp2`

## Validation

Permanent validation checks:

1. merged upstream STM32U5 security-state model remains research-only and fail-closed;
2. 265 Active / 1 quarantined Preview / 2,017 Production counts remain frozen;
3. all three control-plane operations remain host-only;
4. all 105 target-plane state/operation combinations deny;
5. RDP1 regression remains explicitly unresolved and denied;
6. RDP2 normal debug remains closed and conditional regression remains unauthorized;
7. unknown lifecycle/OEM state defaults to deny;
8. nine fail-open negative controls are rejected;
9. runtime/programming/security/OEM/HIL and Production-admission claims remain false.

## Next gate

`stm32u5-security-state-observer-and-debug-validation-gate`

That next gate may define a passive observer/debug evidence contract. This gate itself does not validate an observer or enable target access.
