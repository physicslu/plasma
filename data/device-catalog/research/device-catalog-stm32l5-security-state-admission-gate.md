# STM32L5 — Security-State Admission Gate

Status: **security-state model complete; Production admission still blocked**

## Purpose

The prior STM32L5 transactions established manufacturer-authoritative identity, deterministic metadata, and a clean canonical row plan for 49 exact ICPNs. None of those results proves that a programming executor can safely mutate an STM32L5 security state.

STM32L5 TrustZone and readout-protection state are operationally coupled to debug access, option-byte semantics, erase side effects, and irreversible lockout boundaries. Therefore catalog identity and executable programming capability remain separate dimensions.

## Frozen security model

The gate models seven reachable policy states:

- TrustZone disabled: RDP 0, 1, 2
- TrustZone enabled: RDP 0, 0.5, 1, 2

RDP 0.5 is valid only when TrustZone is enabled. RDP2 is modeled as terminal with no debug access and no outbound transition.

Five security-sensitive transition classes are retained:

1. enable TrustZone (`TZEN` mutation) from RDP0 only;
2. RDP1 -> RDP0.5 under TrustZone;
3. TrustZone RDP regression to RDP0;
4. TrustZone deactivation coupled to RDP regression;
5. entry into RDP2 as an irreversible boundary.

All five transitions are **blocked** by Plasma policy in this transaction.

## Operation policy

The following remain blocked:

- option-byte writes;
- `TZEN` changes;
- RDP changes/regression;
- mass erase;
- entry into RDP2;
- Flash program/erase until programming algorithm + security-state validation exists;
- debug attach/read operations until state-aware runtime enforcement exists.

The canonical identity plan remains valid as a catalog/data-governance result, but it is not executable support.

## Evidence authority

Primary manufacturer authorities:

- ST RM0438 — STM32L5 reference manual, lifecycle/RDP/debug/Flash security sections;
- ST TrustZone development guidance — debug/regression constraints and TrustZone deactivation behavior;
- ST STM32L5 documentation index — identifies RM0438 as the family reference manual.

This gate freezes semantic policy, not live hardware behavior. Hardware behavior still requires HIL validation.

## Admission result

- modeled security states: **7**
- modeled transition classes: **5**
- canonical identity plan: **still valid**
- destructive transitions: **fail-closed**
- Production manifest admission: **not authorized**
- runtime programming: **not authorized**
- security mutation: **not authorized**

## Next gate

**STM32L5 runtime-enforcement admission gate**

That transaction must prove that runtime/executor policy actually enforces the security-state boundary before any STM32L5 Production publication can make an executable path reachable.
