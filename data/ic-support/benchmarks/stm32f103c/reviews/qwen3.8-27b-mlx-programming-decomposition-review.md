# Qwen 3.8 27B MLX STM32F103C Programming Decomposition Review

Status: review / regression record

Targets:

- `STM32F103C8T6`
- `STM32F103CBT6`

Authoritative manufacturer sources used by the experiment:

- ST `DS5319 Rev 20`
- ST `PM0075 Rev 2`

Independent implementation reference used during human review:

- OpenOCD `src/flash/nor/stm32f1x.c`

## Purpose and evidence boundary

This file records defects, ambiguities, provenance problems, and architecture lessons found while reviewing Qwen-generated STM32F103C programming-profile and programming-flow outputs.

It is **not ground truth** and does not override manufacturer documentation. The original grounded Qwen output retained under `../generated/` remains immutable evidence of what the model produced. Later manually reviewed outputs may be discussed here without being promoted to a formal benchmark candidate.

The Qwen session under review did not consume the Plasma repository, Plasma ground truth, checked-in profiles/bindings, this review record, or OpenOCD source while producing the manufacturer-grounded decomposition. That makes the experiment useful for evaluating source-grounded extraction and reasoning, but it does not prove model pretraining provenance or absence of prior public STM32 knowledge.

## Current capability assessment

The experiment shows a repeatable separation between two capability classes:

### Stronger observed capability

Qwen performed well when asked to convert authoritative manufacturer documentation into an evidence-backed engineering model:

- register, bit, key, timing, option-byte, geometry, and protection extraction;
- cross-document reasoning;
- C8/CB shared-vs-different profile decomposition;
- separation of Programming, Memory Geometry, Security, Option, Execution Policy, and Execution Backend concepts after explicit architecture guidance;
- explicit `DIRECT`, `DERIVED`, `POLICY`, `IMPLEMENTATION`, and `UNSUPPORTED` provenance categories.

### Weaker observed capability

Error rate increased when the same model converted the structured understanding into detailed executable-style pseudocode. The failures were mostly not missing STM32 facts; they were program-synthesis and global-consistency defects such as:

- a correct symbolic bit expression paired with an incorrect numeric mask;
- comparing a bit mask against literal `1` instead of the mask value;
- retry paths that return success without re-verifying terminal state;
- using one policy flag for an unrelated verification decision;
- attempting normal register cleanup after an unresolved busy timeout;
- allowing a destructive security transition to fall through into ordinary programming flow.

The working conclusion is therefore:

> Qwen is a strong IC Knowledge / Specification Agent candidate when grounded in exact manufacturer documents. Its detailed executable output is not a production authority and must pass deterministic semantic validation before implementation admission.

## Correction ledger

### CORRECTION-001 — Option-byte complement mapping

Failure class: `REPRESENTATION_ERROR`

Incorrect relationship observed in the first decomposition:

```text
bits[31:24] = NOT(bits[15:8])
bits[23:16] = NOT(bits[7:0])
```

Correct relationship:

```text
bits[31:24] = NOT(bits[23:16])
bits[15:8]  = NOT(bits[7:0])
```

Example layout:

```text
31:24   23:16   15:8   7:0
nUSER   USER    nRDP   RDP
```

Regression rule: logical option-byte values and physical encoded representations must be modeled separately.

Current status: `RESOLVED` in the reviewed second-round decomposition.

### CORRECTION-002 — RDP logical value versus encoded/programming representation

Failure class: `SEMANTIC_REPRESENTATION_MIX`

Required separation:

```text
logical RDP byte   = 0xA5
complement byte    = 0x5A
encoded [nRDP:RDP] = 0x5AA5
programming input  = 0x00A5
```

Regression rule: do not use one field for logical value, complement, encoded storage, and programming transaction representation.

Current status: `RESOLVED` in the reviewed second-round decomposition.

### CORRECTION-003 — RDP external-debug behavior

Failure class: `OVERLY_BROAD_UNKNOWN`

The first decomposition collapsed external-debug behavior under active RDP into a generic unknown. PM0075 documents a more specific operation matrix, including blocked Flash reads over debug paths, continued JTAG/SWD connection, allowed SRAM load/execute behavior, IAP behavior, write/erase restrictions in debug mode, and a mass-erase exception.

Regression rule: represent security states as operation capabilities where evidence exists; reserve `UNSUPPORTED` for the remaining unspecified behavior instead of erasing known restrictions.

Current status: `PARTIAL`. The second-round decomposition improved this substantially but still requires canonical review before admission.

### CORRECTION-004 — Exact page-count provenance

Failure class: `PROVENANCE_CLASSIFICATION_ERROR`

For exact ICPNs, both page counts are deterministic derivations:

```text
C8:  65536 / 1024 = 64 pages
CB: 131072 / 1024 = 128 pages
```

Regression invariant:

```text
page_count == flash_size_bytes / page_size_bytes
```

Current status: `RESOLVED`.

### CORRECTION-005 — Erased-value provenance

Failure class: `PROVENANCE_DIRECTION_ERROR`

Canonical evidence distinction:

```text
erased_program_unit_value = 0xFFFF  DIRECT
erased_byte_value         = 0xFF    DERIVED
program_unit_bytes        = 2
```

Regression rule: preserve the direction of evidence even when Plasma normalizes the fact to a more generic byte representation.

Current status: `RESOLVED`.

### CORRECTION-006 — Unlock failure recovery wording

Failure class: `UNSUPPORTED_NARROWING`

Avoid:

```text
hardware_reset_only
```

Prefer the evidence-backed statement:

```text
reset_required
```

Current status: `RESOLVED`.

### CORRECTION-007 — FLASH_CR lock semantics

Failure class: `SEMANTIC_OVERTRANSLATION`

Avoid converting the controller state into a generic register access-type assertion such as:

```text
FLASH_CR becomes read-only; no further register writes possible
```

Prefer manufacturer-semantic wording such as:

```text
FPEC_and_FLASH_CR_locked
```

with the documented unlock sequence represented separately.

Current status: `UNRESOLVED` in the reviewed second-round decomposition.

### CORRECTION-008 — WRP page mapping

Failure class: `CROSS_FIELD_CONSISTENCY_ERROR`

Medium-density mapping:

```text
1 WRP bit = 4 Flash pages

group_index = floor(page_index / 4)
byte_index  = floor(group_index / 8)
bit_index   = group_index mod 8
```

For the full 32-bit register, `global_bit_index == group_index`.

Regression invariant:

```text
wrp_pages_per_bit == 4
=> protection_group(page) == floor(page / 4)
```

Current status: `RESOLVED`.

### CORRECTION-009 — Option layout terminology

Failure class: `DATA_LAYOUT_AMBIGUITY`

Use explicit bit ranges instead of ambiguous `high_word` / `low_word` labels inside one 32-bit word.

Current status: `RESOLVED`.

### CORRECTION-010 — Normal-Flash reset wording

Failure class: `ARGUMENT_FROM_SILENCE`

Avoid turning absence of a reset step into an absolute device claim:

```text
reset_after_normal_programming = not required
```

Prefer:

```text
reset_after_normal_programming = not_part_of_documented_standard_programming_sequence
```

Regression rule:

```text
no evidence of requirement != evidence of no requirement
```

Current status: `RESOLVED`.

### CORRECTION-011 — Generic option reload versus RDP-specific reset behavior

Failure class: `PROFILE_BOUNDARY_ERROR`

Generic option-byte reload behavior and security-transition reset behavior must be modeled separately. RDP transitions can have context-specific reset and destructive-erase semantics that do not belong in one generic option field.

Current status: `PARTIAL`.

### CORRECTION-012 — Derived numeric mask consistency

Failure class: `DERIVED_NUMERIC_INCONSISTENCY`

The reviewed second-round pseudocode correctly defined:

```text
CR_PG    = bit 0
CR_PER   = bit 1
CR_MER   = bit 2
CR_OPTPG = bit 4
CR_OPTER = bit 5
```

but annotated their OR mask as `0x3B`. The correct value is:

```text
0x01 | 0x02 | 0x04 | 0x10 | 0x20 = 0x37
```

Regression invariant:

```text
declared_numeric_mask == OR(all declared symbolic bits)
```

Current status: `NEW / UNRESOLVED`.

### CORRECTION-013 — Bit-mask comparison semantics

Failure class: `BOOLEAN_MASK_LOGIC_ERROR`

The reviewed second-round pseudocode used a lock test equivalent to:

```text
(fcr & CR_LOCK) != 1
```

For `CR_LOCK == 0x80`, the masked result is `0x00` or `0x80`, not `1`.

Preferred forms:

```text
(fcr & CR_LOCK) == 0
```

or

```text
(fcr & CR_LOCK) != CR_LOCK
```

Regression rule: bit-mask predicates must compare against zero or the mask value, not an unrelated Boolean literal unless the expression has been normalized to Boolean first.

Current status: `NEW / UNRESOLVED`.

### CORRECTION-014 — Retry must end in a verified state

Failure class: `UNVERIFIED_RETRY_SUCCESS`

The reviewed second-round lock pseudocode retried a lock write but returned `OK` without reading back and verifying the second attempt.

Regression rule:

```text
retry -> action -> observation -> terminal-state verification
```

A bounded retry count is Execution Policy and must not be silently hard-coded in a primitive when the policy is already modeled elsewhere.

Current status: `NEW / UNRESOLVED`.

### CORRECTION-015 — Blank-skip policy is not erase verification policy

Failure class: `POLICY_ALIASING_ERROR`

The reviewed second-round pseudocode used `policy.skip_blank` to decide whether to verify an erase operation. These are separate decisions.

Required conceptual separation:

```text
skip_blank_programming
verify_after_erase
```

Regression rule: one policy field must not control semantically unrelated operations.

Current status: `NEW / UNRESOLVED`.

### CORRECTION-016 — Unresolved BSY timeout forbids normal register cleanup

Failure class: `UNSAFE_ERROR_PATH`

If `flash_wait_ready()` times out, the target may still have `BSY=1`. A normal cleanup sequence that immediately writes operation-control or lock bits cannot assume those writes are valid or effective.

Required state transition:

```text
TARGET_BUSY_TIMEOUT
-> controller_state_uncertain
-> no normal register cleanup
-> explicit recovery/reset policy
```

Regression rule: error paths must preserve the hardware state uncertainty that caused the timeout.

Current status: `NEW / UNRESOLVED`.

### CORRECTION-017 — Destructive security transition must not fall through normal programming

Failure class: `SECURITY_TRANSITION_FALLTHROUGH`

A read-unprotect operation is a destructive security transition with its own authorization, mass-erase, reset, reconnect, and re-identification requirements. It must not be represented as an ordinary `rdp_policy` branch that simply continues into normal `UNLOCK -> ERASE -> PROGRAM` flow.

Required conceptual flow:

```text
RDP detected
-> SECURITY_TRANSITION_REQUIRED
-> explicit high-risk authorization
-> separate read-unprotect operation
-> destructive mass erase
-> required reset
-> reconnect / re-identify
-> normal programming flow
```

Current status: `NEW / UNRESOLVED`.

### CORRECTION-018 — Reset requirements are context-sensitive

Failure class: `CONTEXT_COLLAPSE`

Do not reduce RDP transitions to one unconditional reset type. The canonical model should preserve the relevant execution context and evidence, including distinctions between generic option reload, RDP enable, RDP unprotect, debugger-attached cases, and bootloader/SRAM paths where documented.

Regression rule: security-transition reset requirements require a condition table when the manufacturer documentation makes the requirement context-sensitive.

Current status: `NEW / PARTIAL`.

## Cross-cutting regression rules

The following rules should become generic IC Support generation invariants rather than Qwen-specific prompt reminders:

1. IC physical constraint != Execution Policy.
2. Logical value != encoded representation.
3. `DIRECT` claims require direct evidence.
4. `DERIVED` claims require deterministic derivation from cited direct facts.
5. No evidence != false and no evidence != not required.
6. Security state should be represented as an operation capability matrix where possible.
7. Mapping algorithms must be internally consistent with their documented granularity.
8. Do not blindly write a complete status-register snapshot back to a W1C register; clear explicitly intended flags.
9. Cleanup of operation-control bits must respect controller accessibility and lock state.
10. Programming-unit alignment constraints must not automatically become image-length constraints.
11. Manufacturer timing evidence != programmer timeout policy.
12. Declared numeric masks must equal their symbolic bit expressions.
13. Bit-mask predicates must use valid mask semantics.
14. Retries must terminate in an observed and verified state.
15. One policy field must not control unrelated semantics.
16. An unresolved busy timeout moves the controller into an uncertain-state recovery path.
17. High-risk destructive security transitions require an explicit separate operation and must not fall through ordinary programming.
18. Reset requirements must preserve documented execution context.

## Recommended model-role separation

The current experiment supports a role-specialized pipeline rather than a single-model authority:

```text
Manufacturer documents
        |
        v
IC Knowledge / Specification Agent
        |
        v
Candidate IC Support
        |
        v
Deterministic schema + semantic validation
        |
        v
Validated canonical specification
        |
        v
Coding-specialized model
        |
        v
Driver / executor / tests candidate
        |
        v
Independent different-family reviewer
        |
        v
Compiler / static checks / simulation / HIL
```

The trust chain remains:

```text
manufacturer evidence
> validated canonical specification
> generated implementation
> AI review
```

No AI model is a replacement for manufacturer authority, deterministic admission checks, or real-target validation.

## Admission status

Current reviewed Qwen decomposition status:

```text
Manufacturer-grounded extraction       strong / useful
Profile decomposition                  strong / useful
Architecture layering                  strong after guidance
Executable-style pseudocode            not admission-ready
Security transition handling           not admission-ready
Production driver authority            rejected
```

Do not promote the reviewed pseudocode into a runtime driver or canonical profile without resolving the open corrections and passing deterministic validation plus the normal Plasma software/HIL acceptance path.
