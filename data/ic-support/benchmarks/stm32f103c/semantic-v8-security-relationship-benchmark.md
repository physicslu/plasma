# STM32F103C Semantic v8 — Security Relationship Derivation Foundation

## Scope

This benchmark removes the last AI-emitted STM32F103C profile relationship: `security`.

Generation now emits manufacturer-near facts only. Plasma owns all benchmark profile relationships through deterministic derivation.

## Security relationship authority

The relationship is derived from source-locked, evidence-backed applicability:

```text
same evidence-backed applicable security contract      -> shared
different evidence-backed applicable security contract -> different
insufficient applicability                              -> unknown
```

For the locked STM32F103C8T6 / STM32F103CBT6 benchmark, both targets bind the same PM0075 Evidence Pack through `pm-f10xxx`, so the benchmark-level expected result is:

```text
security = shared
```

## Critical safety boundary

`security = shared` does **not** mean that destructive security transitions are safe, equivalent, or admitted for execution.

The Evidence Pack identity is used only as a benchmark relationship projection. It does not establish production Security Profile admission, RDP transition safety, write-protection transition safety, recovery guarantees, or authorization to perform any destructive operation.

Explicit trust-boundary results remain:

```text
security_transition_safety_admission = false
destructive_security_operation_admission = false
canonical_dataset_admission = false
production_admission = false
```

The relationship is not derived from equality of AI-generated fields such as `read_unprotect_is_destructive` or `write_protection_granularity_bytes`.

## Generation boundary

The v8 semantic schema keeps `profile_relationships` as an empty object. AI cannot emit:

- `programming`
- `option`
- `security`
- `memory_geometry`
- `package_hardware`

AI continues to extract manufacturer-near programming, option, security, per-target memory, and per-target package facts with evidence citations.

## Deterministic stack

```text
AI manufacturer-near facts
        ↓
security applicability derivation
        ↓
option applicability derivation
        ↓
programming applicability derivation
        ↓
memory geometry deterministic comparison
        ↓
package hardware deterministic comparison
        ↓
canonicalization
```

## Regression requirements

v8 validates:

- generation isolation from hidden applicability/ground truth/canonicalization contracts;
- security applicability projection against the existing Evidence Pack foundation authority;
- `shared`, `different`, and fail-closed `unknown` derivation;
- proof that generated security fields are not relationship authority;
- explicit rejection of destructive-security-operation admission;
- retained v7/v6/v5 derivation behavior;
- canonical evidence propagation and exact scoring;
- rejection of AI attempts to add any profile relationship.

No HIL, FPGA, SWD runtime, real IC programming, option-byte write, RDP transition, destructive security operation, canonical dataset admission, or production admission is part of this benchmark.
