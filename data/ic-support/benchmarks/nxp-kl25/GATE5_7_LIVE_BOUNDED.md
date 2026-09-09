# NXP KL25 Gate 5.7 — Live Bounded Semantic Qualification

Target: `MKL25Z128VLK4`

## Objective

Gate 5.7 moves the already model-free Gate 5.5 per-Evidence-Unit architecture to
a separately governed live qualification path. It does not modify the historical
monolithic v4.1 contract or retained Gate 5.4/5.4A runs, and it does not promote
Gate 5.5's `mock_only` contract to live execution.

The execution failure domain is aligned with the manufacturer-evidence authority
domain:

```text
8 admitted primary Evidence Packs
  -> 8 sequential isolated prompts / schemas
  -> 8 independently retained child outputs
  -> deterministic all-units aggregation
  -> deterministic semantic defect screening
  -> READY_FOR_REVIEW at most
```

No child output is repaired, retried, merged at fact level, citation-supplemented,
or assigned a replacement fact ID.

## Frozen Gate 5.6 input

Gate 5.7 binds the corrected manufacturer-evidence release:

```text
evidence release  nxp-kl25-evidence-boundary-release-v1
bundle digest     ffe9bfaa8a6ed47c8edd6d952fe1ca2cc114513c2a1f0832892ab9484e7322bf
manifest digest   03155ede421cddb7c2ab64e079ef43b1124a7c78cbedf1e7a08c60c29796bb6e
Program Longword  p444-p446
p447               not admitted
```

The historical pre-AI path under `/storage/projects/plasma-benchmark/nxp-kl25/pre-ai`
is not overwritten. Gate 5.7 uses:

```text
/storage/projects/plasma-benchmark/nxp-kl25/pre-ai-boundary-v1
```

This keeps prior monolithic run provenance reproducible while allowing the
corrected evidence release to have its own workspace identity.

## Live bounded contract

`live-bounded-qualification-contract.json` is a new contract, not a revision of
`live-model-qualification-contract.json`.

Its runtime is frozen to:

```text
execution mode     live_bounded_sequential
transport          ollama_native_chat
model              qwen3.8:27b-mlx
primary units      8
automatic retries  0
num_ctx             65536 per unit
max_tokens          8192 per unit
temperature         0
seed                0
timeout              1800 seconds per unit
endpoint policy     loopback only
```

The contract also binds the unchanged Gate 5.5 bounded base contract by both ID
and canonical digest. The provider-neutral `bounded_extraction.py` still defaults
to Gate 5.5 `mock_only`; a live caller must explicitly supply a separately hashed
execution profile.

## Execution and retention

`run_live_bounded_qualification.py`:

1. validates the full corrected pre-AI workspace and all deterministic digests;
2. validates the separate Gate 5.7 contract and Gate 5.5 base-contract digest;
3. validates the loopback Ollama endpoint, model identity and model digest;
4. executes exactly one sequential call for each of the eight primary units;
5. retains every raw child response and unit record before aggregation;
6. deterministically reaggregates all children without fact-level rewriting;
7. retains live runtime provenance and a qualification report.

A child failure does not trigger an automatic retry. The scheduled eight-unit
experiment may complete to retain a complete failure map, but no second experiment
is automatically started.

The retained layout is:

```text
bounded-runs/<UTC-run-id>/
  request-manifest.json
  unit-01/raw-response.txt
  unit-01/unit-run.json
  ...
  unit-08/raw-response.txt
  unit-08/unit-run.json
  aggregate-report.json
  live-bounded-provenance.json
  qualification-report.json
```

## Qualification states

Gate 5.7 emits only:

```text
REJECTED_INTEGRITY
REJECTED_SCREENING
READY_FOR_REVIEW
```

`READY_FOR_REVIEW` requires all of the following:

- exact eight child records and exact request provenance;
- all children structurally successful;
- provider `done=true` and `done_reason=stop` for every child;
- positive token telemetry within the per-unit context/output envelope;
- exact in-pack citations only;
- globally unique fact IDs after deterministic aggregation;
- full eight-unit response coverage;
- deterministic semantic screening pass;
- at least one primary-unit citation per unit.

It is not semantic correctness, model-quality admission, or `QUALIFIED`.
Manufacturer review is a separate later gate.

## Model-free CI before inference

Repository CI must run without network or model weights. Gate 5.7 tests inject a
fake runtime identity and fake transport while blocking socket creation. Coverage
includes:

- exact Gate 5.6 bundle/manifest binding;
- exact Gate 5.5 base-contract digest binding;
- eight isolated sequential requests;
- zero automatic retries;
- loopback-only enforcement;
- model identity/digest binding;
- `length` completion rejection;
- out-of-pack p447 rejection while p446 remains allowed;
- distinction between aggregate integrity failure and semantic-screening failure;
- raw child retention and deterministic aggregate replay;
- preservation of Gate 5.5 default `mock_only` behavior.

No real Ollama/Qwen request is part of repository CI.

## Operator helper

The existing `scripts/ic-support-kl25-live.sh` is extended rather than creating a
new shell helper:

```text
bounded-build
bounded-status
bounded-run
bounded-diagnose
```

The normal Gate 5.7 path is therefore one helper surface with `set -Eeuo pipefail`.
`bounded-run` itself performs no automatic retry.

## Trust boundary

Gate 5.7 does not admit:

- semantic extraction correctness;
- model quality;
- canonical dataset content;
- HIL behavior;
- real IC programming;
- production programming;
- destructive security operations;
- automatic semantic repair;
- citation synthesis.

If one live Gate 5.7 experiment reaches `READY_FOR_REVIEW`, the next scope is a
manufacturer-evidence semantic and citation review. If it fails, the retained
child/aggregate artifacts are negative evidence and must not be rewritten in
place.
