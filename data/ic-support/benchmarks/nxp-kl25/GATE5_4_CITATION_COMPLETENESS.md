# NXP KL25 Gate 5.4 — Citation Completeness Hardening

Target: `MKL25Z128VLK4`

## Objective

Gate 5.4 addresses the remaining provenance-quality defect observed after the retained Gate 5.3 semantic run passed manufacturer-evidence truth review.

The retained run remains immutable:

```text
/storage/projects/plasma-benchmark/nxp-kl25/runs/20260908T052459Z
```

The local manufacturer-evidence Review v3 of that unchanged run observed:

```text
unit_count              = 8
semantic_pass           = 8
semantic_fail           = 0
citation_pass           = 3
citation_needs_repair   = 5
```

Six facts were semantically supported by the full deterministic Evidence Pack but had incomplete fact-local citations:

- `nxp-kl25-debug-security-interaction-v0-1`
- `nxp-kl25-ftfa-command-sequencing-v0-4`
- `nxp-kl25-ftfa-register-model-v0-2`
- `nxp-kl25-program-longword-v0-1`
- `nxp-kl25-swd-mdm-ap-v0-2`
- `nxp-kl25-swd-mdm-ap-v0-3`

This is not classified as a semantic contradiction. The evidence showed a narrower failure mode: a compound fact could be correct when checked against the full Evidence Pack while its own citation list did not cover every material clause.

## First-principles distinction

Gate 5.4 keeps two independent questions separate:

```text
semantic truth       = is the complete claim supported somewhere in the bounded manufacturer Evidence Pack?
citation completeness = do this fact's own cited pages support every material clause in that claim?
```

A semantic PASS does not erase a citation defect.

## Extraction policy v1

`semantic-extraction-contract.json` is revised to:

```text
contract_id = nxp-kl25-semantic-extraction-v1
```

The output contract now requires a citation-completeness policy with these properties:

- facts should be atomic;
- every material clause requires complete evidence;
- a multi-page claim must cite every manufacturer page needed for complete support;
- materially disjoint clauses should be split into separate facts;
- irrelevant citation padding is forbidden.

The semantic prompt gives one generic locality example only: if one page establishes a register address and another establishes a field meaning, a statement claiming both must cite both pages or be split into atomic facts with local citations.

No KL25 per-unit answer key or expected page list is injected into the model prompt.

## Deterministic trust boundary

The deterministic parser continues to enforce:

- one structured semantic response;
- exact primary-unit coverage;
- globally unique `fact_id` values;
- allowed fact kinds;
- non-empty evidence arrays;
- no duplicate evidence refs inside a fact;
- every citation must belong to that unit's admitted Evidence Pack.

It deliberately does **not** claim to infer whether a natural-language clause is completely supported by a particular page. That would require semantic interpretation and would turn deterministic code into a hidden fuzzy reviewer.

Manufacturer-evidence review therefore remains mandatory for citation completeness.

## Qualification contract v4

The live qualification contract is revised to:

```text
contract_id          = nxp-kl25-live-model-qualification-v4
semantic_contract_id = nxp-kl25-semantic-extraction-v1
```

The review policy now explicitly records that semantic truth and citation quality are independent, and that complete fact citations are required for review acceptance.

Gate 5.4 does not alter:

- Gate-3 Evidence Packs;
- target-bundle digest;
- pre-AI manifest digest;
- source lock;
- applicability binding;
- compact-context strategy;
- local model identity;
- 64K context / 8192 output envelope;
- retained prior runs.

## Model-free CI

Repository CI validates the Gate 5.4 policy without model weights or external inference.

Synthetic tests prove that:

- the versioned contracts enable all Gate 5.4 citation policies;
- the rendered model prompt contains the atomic-fact and complete-citation requirements;
- the structured output schema supports a compound fact citing multiple pages;
- the schema also supports splitting that compound statement into atomic facts with local citations;
- deleting the Gate 5.4 citation policy fails closed before provider schema use;
- the parser does not pretend that citation membership alone proves semantic completeness.

## Live acceptance

After model-free CI passes, exactly one new `qwen3.8:27b-mlx` live semantic run is allowed under the established SWPC-to-Mac reverse-tunnel topology.

The new run is a new experiment because the semantic extraction contract and prompt changed. It must be retained separately and must not overwrite `20260908T052459Z`.

The post-run manufacturer review acceptance target is:

```text
semantic_pass             = 8
semantic_fail             = 0
citation_pass             = 8
citation_needs_repair     = 0
```

If any semantic fact fails, investigate the fact; do not tune the prompt to force PASS.

If semantic truth passes but citation completeness still fails, retain the run as negative provenance evidence and diagnose the remaining locality defect. Do not repair the model response in place.

Only after both semantic truth and citation completeness pass may an authoritative `kl25_reviewed_semantic_verdict` be issued for that exact semantic-run digest and deterministic requalification proceed toward `QUALIFIED`.

## Admission boundary

Gate 5.4 does not admit:

- semantic extraction quality globally;
- model quality globally;
- canonical dataset content;
- HIL;
- production programming;
- destructive security operations.

A future `QUALIFIED` result is scoped to the exact retained KL25 live-model run and its reviewed manufacturer evidence.
