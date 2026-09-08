# Gate 5.3 — Semantic Coverage & Deterministic Screening Robustness

## Decision basis

The first real Gate 5.2 v2 run (`20260908T004912Z`) reached `semantic=success` with runtime/integrity PASS but `REJECTED_SCREENING`.

Observed runtime evidence:

- context strategy: `cross_pack_physical_page_dedup_v1`
- page occurrences: 127
- unique physical pages: 33
- duplicate occurrences removed: 94
- context bytes: 107386
- prompt bytes: 112662
- input tokens: 23237
- generation tokens: 3266
- requested context: 65536
- requested max output tokens: 8192
- provider done reason: `stop`
- semantic contract: PASS
- integrity: PASS

Observed screening failures:

1. Erase All Blocks: required protection concept did not match the emitted word `protected`.
2. FTFA register model: required `FTFA`, `FSTAT`, and `FCCOB` did not match structured identifiers such as `FTFA_FSTAT` and `FTFA_FCCOB`.
3. Program Longword: `FCCOB` was genuinely absent from the emitted facts.
4. SWD / MDM-AP: `SWD` was genuinely absent from the emitted facts.

The retained v2 run remains negative evidence and is not rewritten or reclassified as PASS.

## Gate 5.3 scope

Gate 5.3 separates deterministic screening robustness from model semantic coverage.

Implemented policy:

- keep exact compound-term matching;
- allow a single alphanumeric concept to match an underscore/punctuation-delimited identifier component, e.g. `FTFA_FSTAT` satisfies `FTFA` and `FSTAT`;
- do not introduce fuzzy matching, stemming, embeddings, or AI-assisted screening;
- represent known protection morphology explicitly in the deterministic contract vocabulary;
- strengthen the generic extraction instruction to preserve programming-relevant named mechanisms established by primary evidence, without injecting per-unit required-term answer keys into the prompt;
- preserve Gate-3 evidence and all prior retained run artifacts unchanged.

## First real Gate 5.3 v3 run

Run `20260908T032923Z` is retained as negative evidence and must not be mutated or rerun in place.

Observed execution evidence:

- qualification contract: `nxp-kl25-live-model-qualification-v3`
- context strategy: `cross_pack_physical_page_dedup_v1`
- page occurrences: 127
- unique physical pages: 33
- duplicate occurrences removed: 94
- context bytes: 107386
- prompt bytes: 113205
- input tokens: 23326
- generation tokens: 4458
- requested context: 65536
- requested max output tokens: 8192
- provider done reason: `stop`
- full JSON document: PASS
- semantic status: error
- error class: `model_output_schema_error`
- error: `duplicate fact_id: f1`
- qualification: `REJECTED_INTEGRITY`

This run did not reach semantic screening. The provider completed normally and emitted one valid JSON document, but the deterministic parser rejected globally duplicated `fact_id` values. The parser's fail-closed rule is retained. The prompt is hardened instead to state that `fact_id` must be globally unique across the complete response and should not restart numbering for each Evidence Unit.

This is an output-contract guidance defect exposed by the broader Gate 5.3 extraction response, not evidence that the two target coverage omissions passed or failed. Semantic coverage remains unevaluated for this run.

## Second real Gate 5.3 v3 run

Run `20260908T052459Z` is retained unchanged. It reached the semantic screening boundary successfully:

- qualification contract at inference time: `nxp-kl25-live-model-qualification-v3`
- context strategy: `cross_pack_physical_page_dedup_v1`
- page occurrences: 127
- unique physical pages: 33
- duplicate occurrences removed: 94
- context bytes: 107386
- prompt bytes: 113393
- input tokens: 23362
- generation tokens: 4498
- requested context: 65536
- requested max output tokens: 8192
- provider done reason: `stop`
- full JSON document: PASS
- semantic contract: PASS
- semantic status: success
- integrity: PASS
- qualification: `REJECTED_SCREENING`

The only reported screening errors were `FCCOB` for the FTFA register-model unit and Program Longword unit. Inspection of the retained semantic facts showed that the required mechanism was in fact present:

- FTFA register model emitted `FTFA_FCCOBn` and described the Flash Common Command Object register family.
- Program Longword emitted `FCCOB0`, `FCCOB1-3`, and `FCCOB4-7` and described command code, address, and data placement.
- The prior SWD omission was corrected in this run.

Therefore these two remaining errors are deterministic vocabulary-normalization false negatives, not semantic coverage omissions.

## Screening policy revision v3.1

The qualification contract is revised to `nxp-kl25-live-model-qualification-v3.1` for deterministic requalification. This revision does not change the retained model output, context, generation envelope, or manufacturer evidence.

Rather than introduce generic prefix/fuzzy matching, the screening vocabulary explicitly recognizes the manufacturer-defined indexed FCCOB register family:

- `FCCOB`
- generic `FCCOBn`
- indexed `FCCOB0` through `FCCOB11`

This allows `FTFA_FCCOBn`, `FCCOB0`, and indexed FCCOB references to satisfy the FCCOB concept through the existing punctuation-delimited exact-token matcher, while unrelated extensions such as `FCCOBX` remain rejected. `FSTATUS` also remains invalid for the `FSTAT` concept.

This explicit-vocabulary approach is intentionally narrower than a general `concept + arbitrary suffix` rule and therefore preserves the fail-closed screening boundary.

## Acceptance boundary

Gate 5.3 model-free CI must demonstrate all of the following:

- prior lexical false negatives remain corrected;
- the retained v2 genuine `Program Longword/FCCOB` and `SWD/MDM-AP/SWD` omissions remain omissions when the concept is actually absent;
- the retained v3 forms `FTFA_FCCOBn` and indexed `FCCOB0..11` satisfy the FCCOB concept;
- unrelated prefix extensions such as `FCCOBX` do not satisfy the concept;
- global `fact_id` uniqueness remains a deterministic parser invariant;
- no Gate-3 evidence or retained run artifact is modified.

After CI is green, run `20260908T052459Z` must be requalified deterministically under contract v3.1 without invoking the local model. `READY_FOR_REVIEW`, if reached, is not semantic correctness. Manufacturer-evidence review remains mandatory before `QUALIFIED`, and all canonical/HIL/production/security admissions remain denied.
