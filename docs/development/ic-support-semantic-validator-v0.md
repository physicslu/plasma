# IC Support Semantic Validator v0

Status: engineering pilot

## Purpose

This workstream converts recurring Qwen/Gemma IC-support failures into deterministic engineering invariants.

The validator is not an AI reviewer and does not replace manufacturer evidence, schema validation, compiler/static checks, simulation, or HIL. Its purpose is to create a stable trust boundary between probabilistic IC knowledge extraction and later implementation generation.

Trust order remains:

```text
Manufacturer evidence
> validated canonical IC Support specification
> generated implementation
> AI reviewer opinion
```

## Pipeline position

```text
Manufacturer documents
        |
        v
Evidence Pack
        |
        v
Qwen primary Knowledge / Specification Agent
        |
        v
Candidate canonical profiles
        |
        v
Schema / source / catalog validation
        |
        v
Semantic Validator
        |
        v
Validated canonical specification
        |
        v
Coding-specialized model
        |
        v
Implementation checks / simulation / HIL
```

## Why this layer exists

The Qwen and Gemma experiments showed a repeatable capability split:

- both model families were strong at manufacturer-grounded fact extraction;
- both became less reliable when facts were converted into stateful imperative programming logic;
- their failure modes differed, so switching model family did not remove the need for deterministic checks;
- AI self-review could claim coverage while missing known defects.

The desired engineering property is therefore:

```text
model changes -> validator remains
```

A discovered mechanical failure should become a permanent regression rule, not only a prompt reminder.

## Rule registry

The machine-readable registry is:

- `data/ic-support/semantic-rules-v0.json`

Rules `V001` through `V014` are retained even when the current canonical representation cannot yet enforce them. This prevents future work from silently treating an unimplemented check as covered.

### Implemented now

#### V001 — numeric mask consistency

The programming profile now explicitly records symbolic `FLASH_CR` control bits, the operation-mode bit set, and the derived numeric mask.

Invariant:

```text
declared operation_mode_mask == OR(operation_mode_bits)
```

The known-bad Qwen value `0x3B` is rejected; the correct symbolic OR is `0x37`.

#### V007 — representation separation

The STM32F1 security profile now separates:

```text
logical RDP byte        = 0xA5
complement byte         = 0x5A
encoded [nRDP:RDP]      = 0x5AA5
programming halfword    = 0x00A5
```

The validator derives the complement and encoded representation mechanically and rejects semantic mixing.

#### V008 — memory geometry consistency

Invariant set includes:

```text
flash_size % page_size == 0
flash_size == page_size * page_count
flash_end == flash_start + flash_size - 1
erase_granularity == page_size   # current STM32F103C pilot
```

#### V009 — target address bounds (partial)

The validator exposes a deterministic access check enforcing:

- exact target Flash start/end;
- access width containment;
- programming alignment.

The helper is covered by negative tests for unaligned, out-of-range, and end-crossing accesses. Full enforcement over generated operations requires an execution IR and is intentionally marked `partial`.

## Rules requiring a later execution IR

The current canonical profiles are declarative and do not represent enough control flow to prove the following properties:

- `V002` bit-mask predicate semantics;
- `V003` retry requires terminal observation;
- `V004` timeout enters uncertain state;
- `V005` uncertain state forbids normal cleanup;
- `V006` destructive security transition does not fall through;
- `V010` policy semantic isolation;
- `V011` sub-operation error propagation;
- `V012` operation-mode lifecycle;
- `V013` status/W1C flag lifecycle.

These are not marked PASS. Their registry status is `requires_execution_ir`.

`V014` requires a future review-artifact contract so an AI self-check cannot claim PASS without explicit coverage evidence.

## Regression strategy

`data/ic-support/test_semantic_validate.py` intentionally mutates known-good canonical profiles and verifies deterministic rejection of representative bad states:

- Qwen-style `0x3B` operation mask;
- mixed RDP logical/encoded representation;
- inconsistent Flash page count;
- unaligned and out-of-range STM32F103C8 accesses.

The IC Support GitHub Actions workflow runs both:

```text
python data/ic-support/semantic_validate.py
python data/ic-support/test_semantic_validate.py
```

This makes the implemented invariants CI admission gates rather than review guidance.

## Engineering benefit

The main benefit is not this specific Python script. It is accumulation of reusable engineering knowledge:

```text
AI failure
   -> classified failure mode
   -> deterministic invariant
   -> regression fixture
   -> permanent CI gate
```

Over time this makes local AI replaceable while preserving Plasma's validated knowledge and acceptance criteria.

It also supports profile reuse: multiple ICPNs can share one validated programming/security profile while binding different memory geometry, package, or other orthogonal profiles. New part support can increasingly become data admission instead of duplicated driver implementation.

## Non-goals for v0

This phase does not claim to validate executable pseudocode or production driver control flow. In particular, it does not yet prove retry, timeout cleanup, W1C lifecycle, cross-function error propagation, or destructive-security workflow isolation.

Those checks require a deliberately designed execution contract/IR rather than brittle parsing of arbitrary generated source code.

## Next step

Design a minimal programming execution IR that is generated from the validated canonical specification or by the coding stage and is rich enough to express:

- operation states and preconditions;
- register/flag observations;
- bounded polling and timeout transitions;
- sub-operation results and propagation;
- destructive security transitions;
- explicit terminal-state verification.

Then promote `V002`-`V006` and `V010`-`V013` from `requires_execution_ir` to deterministic CI checks one rule at a time.
