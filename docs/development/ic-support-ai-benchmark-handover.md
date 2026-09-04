# IC Support Local-AI Benchmark Handover

Status: Reference

Last updated: 2026-09-04

## Purpose

This handover captures the current state of the STM32F103C local-AI IC Support experiment so a later session can continue without reconstructing the reasoning from chat history.

This document is research and engineering guidance. It is not a runtime contract, not manufacturer ground truth, and not proof of hardware programming readiness.

## 1. Experiment target and authority

Targets:

- `STM32F103C8T6`
- `STM32F103CBT6`

Manufacturer authority:

- ST `DS5319 Rev 20`
- ST `PM0075 Rev 2`

The exact benchmark source set and digest lock remain defined by:

- `data/ic-support/benchmarks/stm32f103c/source-lock.json`

The answer keys remain:

- blind extraction: `data/ic-support/benchmarks/stm32f103c/extraction-ground-truth.json`
- normalization/profile binding: `data/ic-support/benchmarks/stm32f103c/ground-truth.json`

Do not expose either answer key to a model during a blind extraction/model-comparison run.

## 2. Qwen experiment boundary

Primary model under review:

```text
qwen3.8:27b-mlx
```

Important experimental fact: the manufacturer-grounded Qwen session that produced the reviewed technical decomposition did **not** receive the Plasma repository, Plasma ground truth, checked-in profiles/bindings, the later review corrections, or OpenOCD source as input.

This is evidence that the model can independently recover and reason over many of the required technical facts from the supplied ST documents. It does **not** prove what the base model saw during pretraining.

The immutable first grounded raw experiment retained in the repository is:

- `data/ic-support/benchmarks/stm32f103c/generated/qwen3.8-27b-mlx-grounded-run1.raw.json`

The later programming-decomposition and corrected-pseudocode outputs were manually reviewed outside the formal source-locked blind-candidate flow. Their defects are recorded in:

- `data/ic-support/benchmarks/stm32f103c/reviews/qwen3.8-27b-mlx-programming-decomposition-review.md`

Do not silently edit the original generated evidence to make it pass a later contract.

## 3. What the Qwen tests established

### Strong observed area: source-grounded IC knowledge modeling

When supplied with the exact ST datasheet/programming manual and constrained to use them as authority, Qwen performed strongly at:

- technical fact extraction;
- register, bit, key, timing, option-byte, geometry, and protection interpretation;
- cross-document reasoning;
- distinguishing shared programming behavior from different C8/CB memory geometry;
- evidence/provenance reporting;
- decomposing the target into Programming, Memory Geometry, Security, Option, Execution Policy, and Execution Backend concepts after explicit architecture guidance.

This is the highest-value role observed so far.

### Weaker observed area: executable program synthesis

When asked to turn the same understanding into detailed executable-style pseudocode, new internal-consistency defects appeared even though the underlying STM32 facts were often correct.

Examples include:

- correct symbolic bit definitions but an incorrect derived numeric mask;
- invalid mask-to-Boolean comparison;
- retry without final state verification;
- policy aliasing between blank-data optimization and erase verification;
- attempting normal cleanup after an unresolved `BSY` timeout;
- destructive RDP-unprotect behavior falling through into ordinary programming flow.

Therefore the current conclusion is:

> Use Qwen primarily as an IC Knowledge / Specification Agent. Do not use its detailed generated pseudocode or code as a production authority.

## 4. Architecture conclusion: specialize model roles

The preferred direction is not a single omnipotent model. Separate responsibilities and insert a deterministic trust boundary:

```text
Manufacturer documents
        |
        v
IC Knowledge / Specification Agent
(Qwen demonstrated useful capability here)
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
Driver / generic executor / tests candidate
        |
        v
Independent different-family reviewer
        |
        v
Compiler + static checks + simulation + HIL
```

The coding model should preferably consume a validated declarative specification instead of re-reading the manufacturer PDFs and independently rediscovering hardware semantics.

Longer-term, avoid one hand-written/generated imperative driver per commercial ICPN where the device behavior can be represented safely as reusable declarative programming profiles executed by a generic backend.

## 5. Trust boundary

The intended priority is:

```text
Manufacturer evidence
    > validated canonical IC Support specification
    > generated implementation
    > AI reviewer opinion
```

No AI output becomes production truth by agreement between two models. A second model can improve defect discovery, but it does not replace deterministic validation or HIL.

## 6. Regression knowledge accumulated from Qwen review

The detailed review currently records eighteen failure/invariant categories. The most important generic classes are:

- physical IC facts must not be mixed with Execution Policy;
- logical values must be separated from encoded storage/programming representations;
- `DIRECT` and `DERIVED` provenance must be mechanically defensible;
- no evidence must not be converted into an absolute negative claim;
- protection granularity and mapping algorithms must agree;
- W1C register handling must clear intended flags, not blindly replay a register snapshot;
- numeric masks must match symbolic bit definitions;
- bit-mask tests must use valid mask semantics;
- retries must end in observed verified state;
- unrelated policy decisions require separate fields;
- unresolved busy timeouts require an uncertain-state recovery path;
- destructive security transitions require explicit high-risk workflows and must not fall through into ordinary programming;
- context-sensitive reset requirements must not be collapsed into one unconditional reset type.

These should become deterministic validator/regression rules over time rather than permanent prompt reminders.

This handover PR intentionally does **not** implement those validators yet.

## 7. Open issues after Qwen correction round

Do not treat the corrected Qwen pseudocode as clean. The latest review still has open issues including:

1. `FLASH_CR` lock semantics overtranslated as generic read-only behavior.
2. Derived `CR_CLEAR_OPS` numeric mask mismatch (`0x37` is expected from the stated bits, not `0x3B`).
3. Invalid `CR_LOCK` mask comparison against literal `1`.
4. Lock retry path lacks final read-back verification.
5. `skip_blank` incorrectly controls erase verification.
6. Timeout paths can attempt register cleanup while controller busy state is unresolved.
7. RDP unprotect is still not modeled as a fully separate destructive security transition.
8. RDP/option reset semantics still require context-sensitive normalization.

Review record:

- `data/ic-support/benchmarks/stm32f103c/reviews/qwen3.8-27b-mlx-programming-decomposition-review.md`

## 8. Next experiment: independent Gemma comparison

The user is running a separate Gemma experiment. Treat it as an independent model-family comparison, not as a correction pass over Qwen.

### Required control conditions

Use a fresh model session and provide the same manufacturer sources:

```text
DS5319 Rev 20
PM0075 Rev 2
```

For the first independent pass, Gemma must **not** receive:

- Plasma repository contents;
- `ground-truth.json`;
- `extraction-ground-truth.json`;
- checked-in profiles/bindings;
- Qwen raw output;
- Qwen corrected output;
- the Qwen correction/review record;
- OpenOCD source or the OpenOCD comparison conclusions;
- a prompt that embeds the known correction answers.

Use the same task definition/prompt class as the original Qwen run as closely as practical. Record the exact model ID, quantization/runtime, prompt, source files, context configuration, and output artifact.

### What to compare

Do not judge only by prose quality. Compare at least:

| Dimension | Question |
|---|---|
| Manufacturer fact accuracy | Are addresses, bits, keys, timings and geometry correct? |
| Evidence discipline | Does each critical claim have valid document evidence? |
| Unsupported inference | Does the model invent facts outside the supplied documents? |
| Cross-document reasoning | Does it combine capacity/page-size/security facts consistently? |
| Profile decomposition | Does it separate Programming/Geometry/Security/Option correctly? |
| Physics vs policy | Does it avoid turning tool choices into IC facts? |
| Global consistency | Do later algorithms remain consistent with earlier extracted facts? |
| Security modeling | Are destructive transitions and debug restrictions represented safely? |
| Program synthesis | Are bit masks, retries, error paths, and state transitions mechanically correct? |

Particular Qwen failure categories should be used **after** Gemma produces its independent answer to classify differences. Do not leak those expected answers into the blind-generation prompt.

## 9. Candidate future model roles

Current hypotheses, not yet benchmark conclusions:

- `qwen3.8:27b-mlx`: IC document understanding / candidate specification generation.
- coding-specialized local model: implementation and test generation from a validated canonical specification.
- different-family model such as Gemma: independent implementation/specification reviewer.

A coding-specialized model has not yet been qualified by this experiment. Do not claim one is production-approved merely because it is marketed for coding.

## 10. Recommended next engineering steps after Gemma A/B

After the independent Gemma result exists:

1. Preserve the raw model output immutably with provenance.
2. Compare Qwen and Gemma against manufacturer evidence independently.
3. Classify common-mode versus model-specific failures.
4. Convert recurring mechanical errors into schema/semantic invariants.
5. Decide which rules belong in the existing blind extraction validator and which require a later programming-profile semantic validator.
6. Only then test a coding-specialized model using a validated specification as input.
7. Keep real programming, RDP transitions, option-byte operations, and other destructive behavior behind explicit security/HIL gates.

## 11. What this handover does not authorize

This document does not authorize or claim completion of:

- production STM32F103 driver generation;
- SWD transport implementation;
- OpenOCD runtime execution for this experiment;
- schema/ground-truth changes;
- automatic RDP or option-byte operations;
- validator admission of the corrected Qwen pseudocode;
- real-target/HIL programming readiness.

Continue to follow `AGENTS.md` for the exact two-gate engineering workflow and hardware/security scope control.
