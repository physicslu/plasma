# ICPN Catalog Admission Separation Invariant

Status: architecture contract

## Purpose

Prevent future ICPN work from conflating catalog admission with physical validation.

## Non-negotiable rule

**Catalog admission is independent from PPU/Socket physical validation.**

An exact commercial ICPN may be admitted to the Production catalog when its manufacturer identity, normalized metadata, backend route/mapping state, provenance/integrity evidence, and catalog CI satisfy the admission contract. Missing PPU or Socket HIL evidence must not, by itself, block catalog publication.

Production-catalog membership therefore means **the exact ICPN is an admitted catalog identity**. It does not mean the device has passed physical programming validation and it does not authorize target execution.

## Four independent product status dimensions

Plasma keeps these dimensions separate:

1. catalog verification / manufacturer-part identity;
2. backend mapping / OpenOCD route state;
3. PPU physical validation;
4. Socket physical validation.

A valid admitted ICPN may therefore appear as:

```text
Catalog identity     confirmed
Backend mapping      mapped
PPU validation       not_verified / no_evidence
Socket validation    not_verified / no_evidence
```

That is a valid Production-catalog state.

## Physical validation boundary

PPU and Socket HIL evidence is required to promote the corresponding physical-validation dimension to `engineering_verified`. HIL must not be used as a prerequisite for exact-ICPN catalog admission unless a future architecture change explicitly replaces this contract.

Catalog admission must never be reported as proof of:

- erase/program/verify success on physical hardware;
- PPU compatibility;
- Socket/electrical compatibility;
- security-state mutation safety;
- pilot or production field use.

## Execution boundary

Catalog membership does not authorize target-touching execution. Production Mode / Engineering Mode policy, security-state policy, backend capability, PPU/Socket evidence, and other runtime requirements remain separate execution gates.

For security-sensitive families such as STM32L5/U3, fail-closed security/runtime gates may restrict execution without preventing a proven exact ICPN from existing in the Production catalog.

## Anti-regression rule for future ICPN work

Before holding an exact ICPN outside the Production catalog, an ICPN task must identify a **catalog-admission deficiency** such as unresolved identity, metadata conflict, ambiguous route, missing provenance/integrity evidence, lifecycle exclusion, or failed catalog CI.

`PPU HIL missing`, `Socket HIL missing`, `hardware not yet acquired`, or `real-target programming not yet executed` are **not catalog-admission deficiencies by themselves**.

The machine-readable contract is `docs/architecture/icpn-catalog-admission-policy.json` and is enforced by `scripts/ci/validate-icpn-catalog-admission-separation.py`.
