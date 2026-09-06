# STM32F103C Semantic v6 — Programming Relationship Derivation Foundation

Status: Research / benchmark foundation

This phase removes `profile_relationships.programming` from AI generation.

## Architecture

```text
Manufacturer Evidence
  -> AI manufacturer-near programming facts
  -> retained semantic artifact

Evidence Pack Applicability Binding
  -> source-locked programming applicability projection
  -> deterministic programming relationship derivation

Both paths
  -> deterministic memory/package relationship derivation
  -> canonicalization
  -> Canonical IC Spec
```

## Programming relationship rule

Programming is not derived by raw equality of generated programming fields.

```text
same evidence-backed applicable contract      -> shared
different evidence-backed applicable contract -> different
insufficient applicability                     -> unknown
```

For the locked STM32F103C benchmark, both `STM32F103C8T6` and `STM32F103CBT6` bind the same `stm32f10xxx-programming-manual-v0` contract through applicability claim `pm-f10xxx`, so the expected relationship is:

```text
programming = shared
```

`programming-applicability-v0.json` is hidden from generation and is checked against `data/ic-support/evidence-pack/fixtures/stm32f103c-foundation-v0.json` before use.

## AI generation boundary

AI still extracts the manufacturer-near `programming_contract` facts. It does not emit:

```text
programming
memory_geometry
package_hardware
```

Only the still-unmigrated `option` and `security` profile relationships remain AI-emitted in v6.

## Fail-closed behavior

Missing or ambiguous programming applicability resolves to `unknown`. Invalid/tampered applicability provenance fails validation.

## Scope boundary

This phase does not admit the canonical dataset, production profiles, HIL, FPGA behavior, SWD runtime, real-target programming, option-byte writes, or security transitions.
