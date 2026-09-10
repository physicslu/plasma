# NXP KL25 Gate 5.7A — Primary-Scoped Bounded Extraction

Target: `MKL25Z128VLK4`

## Why Gate 5.7A exists

The single Gate 5.7 live bounded experiment is retained at:

```text
/storage/projects/plasma-benchmark/nxp-kl25/bounded-runs/20260909T061908Z
```

It produced seven successful child runs and one integrity failure:

```text
failed unit         nxp-kl25-debug-security-interaction-v0
error               model_output_invalid_json
done_reason         length
input_tokens        17496
generation_tokens   8192
raw_bytes           29145
aggregate            REJECTED_INTEGRITY
qualification        REJECTED_INTEGRITY
```

This is not a context-window failure: `17496 + 8192 = 25688`, well below the
frozen `num_ctx=65536`. The output budget was exhausted for one child while the
other seven stopped normally. The retained Gate 5.7 artifact is immutable
negative evidence and is not repaired or rerun in place.

The failed primary unit has a deliberately broad deterministic dependency
closure. Its PRIMARY Evidence Unit is RM pages 149-150, while its Evidence Pack
also carries SWD/MDM-AP, Flash Security, Command Sequencing, and FTFA Register
Model dependencies. Dependency closure is necessary evidence context, but it is
not itself permission to emit dependency-only semantic facts.

Gate 5.7A therefore changes semantic fact authority instead of increasing the
model output budget.

## Frozen inputs and runtime

Gate 5.7A leaves these unchanged:

```text
evidence release     nxp-kl25-evidence-boundary-release-v1
bundle digest        ffe9bfaa8a6ed47c8edd6d952fe1ca2cc114513c2a1f0832892ab9484e7322bf
manifest digest      03155ede421cddb7c2ab64e079ef43b1124a7c78cbedf1e7a08c60c29796bb6e
model                qwen3.8:27b-mlx
num_ctx              65536 per unit
max_tokens           8192 per unit
temperature          0
seed                 0
timeout              1800 seconds per unit
automatic retries    0
primary units        8
```

No Evidence Unit boundary, dependency graph, source lock, Evidence Pack, Gate
5.6 release, or semantic fact schema is expanded by this gate.

## Primary-scoped semantic policy

The new contract is:

```text
nxp-kl25-live-bounded-qualification-v1.1
```

Its semantic scope is:

```text
fact_generation_authority          PRIMARY_ONLY
dependency_pages                   SUPPORTING_CONTEXT_ONLY
every_fact_requires_primary_citation true
dependency_only_fact_forbidden     true
primary_origin                     PRIMARY
```

The complete Evidence Pack remains visible to the model. The distinction is in
what may become a semantic fact:

```text
PRIMARY pages
  -> define the semantic subject and may generate facts

DEPENDENCY pages
  -> remain available as supporting context
  -> may supplement citations for a primary-scoped fact
  -> must not independently generate dependency-only facts
```

Every emitted fact must contain at least one citation to a page belonging to the
PRIMARY Evidence Unit. The provider-facing JSON Schema expresses this with an
evidence-array `contains` constraint, and the deterministic bounded parser
rechecks it after generation and again during retained-artifact replay.

This rule is a scope/integrity constraint, not proof of natural-language support.
A model could still pad a dependency-derived claim with an irrelevant PRIMARY
citation; manufacturer-evidence semantic review remains required to detect that.

## Historical compatibility

Gate 5.7 remains reproducible through:

```text
live-bounded-qualification-contract.json
nxp-kl25-live-bounded-qualification-v1
```

Gate 5.7A uses a separate file:

```text
live-bounded-primary-qualification-contract.json
nxp-kl25-live-bounded-qualification-v1.1
```

The shared provider-neutral bounded core supports the optional primary scope, but
its default Gate 5.5 profile remains `mock_only` and Gate 5.7 v1 does not acquire
the new policy retroactively.

## Model-free acceptance

Before any Gate 5.7A inference, repository CI must prove without network/model
weights that:

- the Gate 5.6 bundle/manifest binding is unchanged;
- `num_ctx=65536`, `max_tokens=8192`, and zero retries are unchanged;
- PRIMARY-only facts pass;
- a fact with PRIMARY plus dependency citations passes;
- dependency-only facts fail closed before semantic screening;
- provider JSON Schema requires at least one PRIMARY citation per fact;
- Program Longword p446 remains admitted and p447 remains excluded;
- the historical Gate 5.7 v1 contract remains valid and has no primary-scoped policy;
- no repository CI path creates a real network/model request.

## Live experiment boundary

After model-free CI passes, Gate 5.7A permits one corrective live bounded
experiment using the same model and frozen generation envelope. It is retained
under:

```text
/storage/projects/plasma-benchmark/nxp-kl25/bounded-primary-runs/<UTC-run-id>
```

No automatic retry is permitted. If the debug/security child again reaches the
8192-token limit, stop. The next question is Evidence Unit/fact ontology
granularity, not another blind token increase.

Gate 5.7A can reach at most `READY_FOR_REVIEW`. It does not admit semantic
correctness, model quality, canonical data, HIL, production programming, or
destructive security operations.
