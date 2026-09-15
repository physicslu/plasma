# STM32U3 security-state admission gate

## Scope

This research-only gate defines the fail-closed STM32U3 security-state admission model above the merged 106-exact-ICPN canonical admission plan. It does not authorize Production admission, runtime programming, debug attach, option-byte writes, OEM-key operations, RDP regression, mass erase, or HIL claims.

## Security-state model

The lifecycle dimension contains seven states:

- TrustZone disabled: RDP 0 / 1 / 2;
- TrustZone enabled: RDP 0 / 0.5 / 1 / 2.

RDP 0.5 is valid only with TrustZone enabled.

OEM1/OEM2 key-provisioning and lock state are modeled as orthogonal security attributes. Key material itself must never be stored or logged. Unknown OEM state is deny-by-default.

## STM32U3-specific RDP2 boundary

STM32U3 must **not** inherit the STM32L5 assumption that RDP2 is unconditionally terminal.

The model preserves both facts simultaneously:

- normal debug access is closed at RDP2;
- an RDP2 to RDP1 regression is only a conditional security transition when an OEM2 unlocking mechanism was already provisioned/activated and the required authentication succeeds.

Plasma does not authorize that regression. It merely models the dependency so a future runtime implementation cannot silently treat RDP2 as either always reversible or always irreversible.

## Modeled mutation classes

Lifecycle mutation classes are:

1. TrustZone enable;
2. raise to RDP1;
3. RDP1 to RDP0 regression with OEM1-state dependency;
4. TrustZone RDP1 to RDP0.5 regression with OEM2-state dependency;
5. entry into RDP2;
6. conditional RDP2 to RDP1 regression with OEM2 authentication.

OEM1/OEM2 transition-mechanism provisioning is separately modeled as non-freely-reversible configuration. Every security mutation remains `blocked`.

Exact TrustZone deactivation semantics and exact destructive effects of OEM-authenticated regressions are deliberately left unresolved rather than guessed. They remain blocked pending later validation.

## Admission result

- security-state admission model complete for fail-closed gating: **yes**;
- all security transition semantics validated: **no**;
- RDP2 conditional-regression boundary modeled: **yes**;
- OEM transition dependency modeled: **yes**;
- unknown OEM state fail-closed: **yes**;
- canonical 106-identity plan remains valid: **yes**;
- Production manifest admission: **no**;
- runtime programming: **no**;
- security mutation: **no**;
- OEM-key operation: **no**;
- HIL required before runtime enablement: **yes**.

## Negative controls

The validator must reject at least these fail-open/incorrect models:

- RDP2 falsely modeled as unconditionally terminal;
- RDP2 regression without an OEM2 prerequisite;
- RDP0.5 admitted while TrustZone is disabled;
- OEM2 key provisioning allowed;
- unknown OEM state treated fail-open;
- premature Production admission.

## Next gate

`stm32u3-runtime-enforcement-admission-gate`

## Production invariant

**Exact ICPN count: 1,862**, unchanged.
