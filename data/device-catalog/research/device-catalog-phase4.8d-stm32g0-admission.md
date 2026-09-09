# STM32G0 Device Catalog Phase 4.8D — Capability / Canonical Admission Policy

Status: **admission-plan closure candidate**

Phase 4.8D adds an independent programming-routing capability gate to the 49 manufacturer-valid exact ICPNs closed by Phase 4.8B and decoded by Phase 4.8C. It plans canonical admission only; it does not write the canonical CSV or Production manifest.

## First-principles boundary

Four different claims remain separate:

1. **Commercial identity/lifecycle** — official ST evidence from Phase 4.8B.
2. **Ordering metadata** — official ST ordering information from Phase 4.8C.
3. **Programming routing capability** — deterministic current OpenOCD ordering-pattern mapping in Phase 4.8D.
4. **Physical/runtime qualification** — not claimed by this phase.

A failure at layer 3 is not allowed to erase a valid layer-1 manufacturer identity.

## Capability result

The current OpenOCD catalog provides one deterministic `tcl/target/stm32g0x.cfg` ordering-pattern mapping for **47** of the **49** manufacturer-valid Active exact ICPNs.

Those 47 identities form the bounded canonical-admission transaction:

- admit: **47**
- already present: **0**
- manual review inside the admission transaction: **0**
- reject: **0**
- canonical rows before: **0**
- canonical write applied: **false**
- Production write applied: **false**

## Capability-unresolved identities

Two manufacturer-valid Active exact ICPNs remain outside the canonical-admission transaction:

- `STM32G0B1CBT6N`
- `STM32G0B1CBU6N`

Their state is explicitly:

- identity: `manufacturer_verified_active`
- capability: `openocd_ordering_pattern_unresolved`
- action: `exclude_from_canonical_admission_until_positive_capability_evidence`

This is **not** an identity rejection.

The policy does not rewrite either identity to its non-N sibling. It also does not infer that the same target configuration is valid merely because both variants belong to STM32G0B1. Positive programming-capability evidence is required before these exact N identities can cross the canonical capability gate.

## Why the generic admission plan remains clean

The generic admission framework is responsible for duplicate/conflict/write mechanics. It expects every submitted candidate to have already passed family policy.

Therefore Phase 4.8D performs capability classification before invoking the generic framework:

- 49 manufacturer-valid identities are evaluated;
- 47 unique ordering-pattern mappings enter the generic admission transaction;
- 2 unresolved N identities remain in a separately retained capability-unresolved set.

This prevents `manual_review_required` from conflating an unresolved capability question with a malformed identity or canonical conflict.

## Frozen plan

Phase 4.8D one-off generation run: `34374662517`

Frozen admission-plan SHA-256:

`d5f83bb3a2417a368e2d0bfb66a146e47b7649675341dc44e9d28c0a5de39801`

Bound inputs include:

- Phase 4.8C policy baseline SHA-256: `953df55b097ad58c93738e2aeecc7c762cb464f882493bf622fefbb61fc3a787`
- OpenOCD canonical mapping catalog SHA-256: `43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`
- retained Phase 4.8B discovery baseline SHA-256: `ef059c3226b506aa0ff739abf8c6bf3e0f525ceaefb571693458dad6b706f10a`
- frozen Production prestate SHA-256: `4b05b3e3e7cb8e9b8cc426f9358d758f04d5bc4944b23e44ee0cad1d3bea1cd3`

Historical Production remains **563 exact ICPNs / 197 Base Devices / STM32G0 = 0**.

## Explicit non-claims

Phase 4.8D does not claim:

- canonical write completion,
- Production publication,
- N/non-N programming-algorithm equivalence,
- physical-target qualification,
- HIL qualification,
- runtime programming support,
- full STM32G0 coverage.

A later controlled canonical-write/publication transaction may publish only the 47 capability-admittable identities unless new positive evidence resolves the two N-version capability gaps.
