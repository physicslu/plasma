# NXP KL25 Gate 5.4 — Citation Completeness Hardening

Target: `MKL25Z128VLK4`

## Objective

Gate 5.4 addresses the remaining provenance-quality defect observed after the retained Gate 5.3 semantic run passed manufacturer-evidence truth review.

The retained Gate 5.3 run remains immutable:

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

Six facts were semantically supported by the full deterministic Evidence Pack but had incomplete fact-local citations. This is not classified as a semantic contradiction. The narrower defect is that a compound fact can be correct against the full Evidence Pack while its own citation list fails to support every material clause.

## First-principles distinction

Gate 5.4 keeps two independent questions separate:

```text
semantic truth        = is the complete claim supported somewhere in the bounded manufacturer Evidence Pack?
citation completeness = do this fact's own cited pages support every material clause in that claim?
```

A semantic PASS does not erase a citation defect.

## Extraction policy v1

`semantic-extraction-contract.json` is revised to:

```text
contract_id = nxp-kl25-semantic-extraction-v1
```

The output contract requires:

- atomic facts where practical;
- every material clause to have complete evidence;
- multi-page claims to cite every necessary manufacturer page;
- materially disjoint clauses to be split when possible;
- irrelevant citation padding to remain forbidden.

The prompt includes only a generic locality example and does not expose KL25 per-unit answer keys.

## Deterministic trust boundary

The deterministic parser enforces representation, exact primary-unit coverage, global fact-id uniqueness, fact kinds, non-empty evidence arrays, duplicate-ref rejection, and Evidence Pack membership.

It deliberately does **not** infer whether natural-language content is fully supported by the cited pages. Manufacturer-evidence review remains mandatory for semantic and citation completeness.

## Qualification contract v4

Gate 5.4 originally used:

```text
contract_id          = nxp-kl25-live-model-qualification-v4
semantic_contract_id = nxp-kl25-semantic-extraction-v1
num_ctx               = 65536
max_tokens            = 8192
```

The first Gate 5.4 live run is retained immutably at:

```text
/storage/projects/plasma-benchmark/nxp-kl25/runs/20260909T010751Z
```

Observed provider telemetry:

```text
semantic_status      = error
qualification_status = REJECTED_INTEGRITY
input_tokens         = 23565
generation_tokens    = 8192
done_reason          = length
raw_json_complete    = false
```

The failure occurred exactly at the configured generation ceiling. The 64K context envelope was not exhausted:

```text
23565 + 8192 = 31757 < 65536
```

Therefore this retained run is classified as output-envelope negative evidence, not as a citation-completeness result. It must not be repaired or overwritten.

## Gate 5.4A corrective amendment

Gate 5.4A is a narrow, explicitly approved corrective amendment. It changes only the live output ceiling:

```text
contract_id          = nxp-kl25-live-model-qualification-v4.1
semantic_contract_id = nxp-kl25-semantic-extraction-v1
num_ctx               = 65536
max_tokens            = 16384
```

Frozen across v4 → v4.1:

- Gate-3 Evidence Packs;
- target-bundle digest;
- pre-AI manifest digest;
- source lock;
- applicability binding;
- semantic extraction contract and prompt;
- compact-context strategy;
- local model identity and digest;
- temperature, seed, and timeout;
- screening vocabulary;
- review policy;
- all retained prior runs.

The correction is driven by observed telemetry rather than speculative prompt tuning. With the observed input size, the revised worst-case envelope is:

```text
23565 + 16384 = 39949 < 65536
headroom             = 25587
```

Exactly one corrective live run is allowed after model-free CI passes. If it again ends with `done_reason=length`, stop and re-evaluate output granularity instead of automatically increasing the limit again.

## Model-free CI

Repository CI validates the citation contract and the frozen v4.1 runtime envelope without model weights or external inference. Tests verify:

- semantic contract remains `nxp-kl25-semantic-extraction-v1`;
- qualification contract is `nxp-kl25-live-model-qualification-v4.1`;
- `num_ctx` remains `65536`;
- `max_tokens` is exactly `16384`;
- atomic-fact and complete-citation requirements remain active;
- provider schema supports multi-page citations and split atomic facts;
- missing citation policy fails closed;
- live execution wiring propagates the frozen 16K output envelope into retained provenance.

## Corrective live acceptance

After model-free CI passes, run exactly one new `qwen3.8:27b-mlx` inference under the existing SWPC-to-Mac loopback/reverse-tunnel topology.

First-stage acceptance:

```text
FULL_JSON                         = PASS
semantic_status                   = success
provider_done_reason              = stop
integrity                         = PASS
semantic_screening                = PASS
qualification_status              = READY_FOR_REVIEW
```

Then manufacturer review requires:

```text
semantic_pass             = 8
semantic_fail             = 0
citation_pass             = 8
citation_needs_repair     = 0
```

Only after both semantic truth and citation completeness pass may an authoritative `kl25_reviewed_semantic_verdict` be issued for that exact semantic-run digest and deterministic requalification proceed toward `QUALIFIED`.

## Admission boundary

Gate 5.4 / 5.4A does not admit semantic extraction quality globally, model quality globally, canonical dataset content, HIL, production programming, or destructive security operations.

A future `QUALIFIED` result remains scoped to the exact retained KL25 live-model run and its reviewed manufacturer evidence.
