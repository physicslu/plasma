# STM32U3 canonical admission plan under security fence

## Scope

This research-only transaction binds the 106 retained STM32U3 manufacturer-observed exact ICPNs to the existing upstream OpenOCD/CMSIS route surface. It does **not** authorize Production admission, programming, debug attach, option-byte mutation, OEM-key operations, RDP regression, mass erase, or HIL claims.

## Frozen result

- retained exact ICPNs: **106**
- retained Base Devices: **33**
- marketing status observations: **100 Active / 6 Evaluation**
- OpenOCD route evidence rows: **171**
  - ordering pattern: **75**
  - CMSIS device name: **96**
- unique exact-to-route assignments: **106 / 106**
  - ordering pattern assignments: **49**
  - CMSIS device name assignments: **57**
- unresolved / ambiguous: **0**
- required target config: `tcl/target/stm32u3x.cfg`
- route evidence digest: `c08a8a6ab303619012be96eb9197a2f10956b13ecc380cd682ed8d6c8d9cc459`
- exact-to-route binding digest: `bb48d4cf660bc151d53f20f399b8ed3a8438796a5592b6f2570b5cf8119da328`

## Evidence semantics

The OpenOCD/CMSIS rows remain `mapping_candidate` / `not_verified` evidence. A deterministic route assignment proves only that an existing catalog identifier and target config can be selected without ambiguity. It does not prove Flash geometry, programming algorithm equivalence, security semantics, debug availability, or physical programming success.

The 6 identities observed by ST as `Evaluation` are retained as manufacturer identity observations only. Evaluation status is not Production admission authority.

## Security fence

All of the following remain blocked:

- Production admission and Production writes;
- security semantics and option-byte mutation;
- OEM1/OEM2 key provisioning or unlock execution;
- RDP regression and mass erase;
- Flash geometry / programming algorithm equivalence;
- runtime programming and debug attach;
- HIL validation.

STM32U3-specific RDP2 behavior remains explicitly unresolved at runtime: RDP2 is not modeled as unconditionally terminal because an OEM2 unlock mechanism can affect regression behavior. That state must be handled by the next security-state gate rather than inferred from catalog routing.

## Next gate

`stm32u3-security-state-admission-gate`

## Production invariant

**Exact ICPN count: 1,862**, unchanged.
