# STM32F103C v7 Option Relationship Derivation Benchmark

## Scope

v7 moves `profile_relationships.option` out of AI generation.

The AI continues to extract manufacturer-near `option_contract` facts, including region address, region size, and structured storage encoding. It does not decide whether the option profile relationship is `shared`, `different`, or `unknown`.

## Relationship authority

The benchmark relationship is derived from source-locked, evidence-backed applicability:

```text
EvidencePack
    -> ApplicabilityBinding
    -> benchmark option applicability projection
    -> deterministic relationship derivation
```

Rules:

```text
same applicable option contract      -> shared
different applicable option contract -> different
insufficient applicability            -> unknown
```

For the locked STM32F103C8T6 / STM32F103CBT6 benchmark, both targets are bound through the PM0075 `STM32F10xxx` applicability claim to the same programming-manual Evidence Pack. Therefore the benchmark-level expected option relationship is `shared`.

## Important trust boundary

The current `contract_id` is Evidence Pack identity used only for this benchmark relationship projection. It is **not** a production Option Profile identity and does not admit production compatibility.

The relationship is not derived from raw equality of AI-generated option fields. Those facts remain useful for deterministic canonicalization of the option storage representation, but they are not the authority for cross-target applicability.

## Expected v7 ownership

```text
AI:
  option_contract facts
  security relationship (legacy, still AI-owned in v7)

Deterministic Plasma code:
  programming relationship
  option relationship
  memory_geometry relationship
  package_hardware relationship
```

## Fail-closed behavior

- missing applicability -> `unknown`
- invalid/tampered applicability evidence -> canonicalization error
- AI attempt to emit `option` relationship -> schema rejection
- free-form/regex/fuzzy inference -> prohibited

## Non-goals

v7 does not prove or admit:

- production Option Profile compatibility
- option-byte write safety
- RDP/security transition safety
- OpenOCD behavior
- FPGA behavior
- HIL correctness
- canonical dataset admission
- production admission

Retained v0-v6 benchmark artifacts remain unchanged.
