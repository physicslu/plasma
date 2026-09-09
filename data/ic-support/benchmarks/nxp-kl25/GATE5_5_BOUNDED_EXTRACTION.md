# NXP KL25 Gate 5.5: bounded extraction, model-free evaluation

Gate 5.5 adds an experimental injected-mock execution path. It does not replace
the existing monolithic runner, v4.1 live qualification contract, or provider
wiring. No live CLI is provided and no Local AI/model execution is admitted.

## Repository status

Gate 5.5 was merged with Gate 5.4/5.4A in PR #421. The merge commit on `main` is:

```text
d9651fc3c7d2386974f0e8c0688131b6a65c01c4
```

This corrects the earlier stacked-PR wording that described the Gate 5.4/5.4A
foundation as unmerged. Gate 5.5 remains experimental and `mock_only` after the
merge; merge status does not convert its integrity checks into semantic,
canonical, HIL, production, or destructive-security admission.

## Retained failure evidence

| Run | Contract | Input tokens | Generated / limit | Completion | Failure |
|---|---|---:|---:|---|---|
| 20260909T010751Z | v4 | 23565 | 8192 / 8192 | length | incomplete JSON |
| 20260909T022843Z | v4.1 | 23565 | 12079 / 16384 | stop | out-of-pack citation |

The first raw response is 27734 bytes and stops within the sixth unit result.
Its SHA256 is
`d801687e62cf640fb6e334cd3811186b2d01ea8f96cdddc8620ed0c48bd663e2`.
The second is complete JSON: eight units and 105 facts, 40353 bytes, SHA256
`6bd0daf4a5a272885ea0fe6054216aececb3218b388a833c6221f2e0d18e9ba8`.
Neither run exhausted the 65536-token context envelope.

The second semantic-run error names
`nxp-kl25-program-longword-v0.facts[9]`, fact
`nxp-kl25-program-longword-v0-010`, citing `nxp_kl25_rm_rev3:p446`.
The historical Program Longword pack allowed 422–431, 435–439 and 444–445.
The retained response's only out-of-pack reference was page 446. The error
prevented the runner from publishing a parsed response, so the qualification
report's all-units-missing screening errors were consequential, not evidence
that the raw response omitted all units.

Manufacturer page 445 ends Table 27-36 with a continuation notice. Page 446
contains the continued Program Longword verify-error/MGSTAT0 row before the
Erase Flash Sector section. That page was visible in monolithic context through
the Erase Sector pack but was outside the historical Program Longword pack.
The citation therefore violated the frozen contract even though this particular
statement matched the manufacturer continuation. This does not establish
semantic or citation correctness for the other facts.

The experiment exposes output-budget coupling, cross-pack visibility and
whole-response rejection. These observations justify evaluating unit isolation;
they do not prove live semantic quality.

## Experimental contract and execution

`bounded-extraction-contract.json` freezes eight sequential injected-mock calls,
one primary pack per call, a 65536 context envelope, 8192 output tokens,
temperature 0, seed 0 and no automatic retries. It identifies execution as
`mock_only`. The callback is a trusted test dependency; the library does not
sandbox arbitrary callback code or supply a provider client.

`bounded_extraction.prepare_requests` validates the complete original pre-AI
manifest and all pack/evidence/page digests before constructing requests.
No fake subset pre-AI manifest is created. Each request carries the full admitted
pack text, including deterministic dependencies, and a one-unit schema.
Citation alternatives encode exact source/page pairs, not their cross-product.
The existing deterministic parser remains authoritative.

`execute_bounded_run` invokes the injected transport once per unit, then retains
each raw response and unit record before continuing. It creates an exclusively
new output directory and never overwrites an existing directory. Unit records
retain request/pack/bundle/manifest/contract/model identity, prompt/schema/evidence
digests, generation settings, raw text/hash, provider usage/timing, and failure
classification. Caller inputs and transport options are copied defensively.
No response repair or token escalation occurs. A transport timeout must be
raised by the injected transport; this synchronous library cannot forcibly
interrupt arbitrary callback code.

`aggregate_results` independently regenerates expected request bindings and
revalidates child hashes, raw/parsed equality, normal completion, token telemetry,
citation membership and exact eight-unit coverage. It rejects missing/duplicate
units, mixed provenance, failed children, duplicate global fact IDs and raw
mutation. Only whole-unit ordering changes. Statements, fact IDs and citations
are not rewritten, deduplicated, supplemented or synthesized.

The output is a `kl25_bounded_aggregate` artifact, not a fabricated monolithic
semantic run. `INTEGRITY_PASS` means structural aggregation passed; it is never
`QUALIFIED` or proof of semantic correctness. All admissions remain false.
Failed aggregates retain valid children as diagnostic artifacts without a
partial admitted response. Digest consistency is not cryptographic authentication.

Eight requests may increase total input processing and latency because dependency
pages recur. Provider support for the pair-specific schema and live output sizes
remain untested. The existing live qualification path is not wired to this
experimental artifact.

## Program Longword boundary blocker and Gate 5.6

The historical definition's 444–445 range excluded Table 27-36's continuation on
physical PDF page 446. Gate 5.6 is the separately approved evidence-boundary
release that corrects the active Program Longword range to 444–446 while keeping
the source lock, unit identity, dependency graph, semantic admissions and prior
retained artifacts unchanged.

On the Gate 5.6 branch, `bounded-extraction-contract.json` records:

```text
evidence_boundary_release_id = nxp-kl25-evidence-boundary-release-v1
known_acceptance_blockers     = []
```

and retains the former blocker in `resolved_acceptance_blockers`. Model-free
regression now requires the isolated Program Longword request to admit p446 and
continue to reject p447. This resolution is not retroactive: the retained
20260909T022843Z run remains rejected against the historical pack that actually
bounded that run.

## Model-free validation and approval boundaries

The repository validation path includes:

```text
python data/ic-support/benchmarks/nxp-kl25/test_bounded_extraction.py
python data/ic-support/benchmarks/nxp-kl25/test_evidence_boundary_gate56.py
```

Tests use synthetic manufacturer text and injected transport only, with network
access blocked in the bounded-extraction tests. They exercise isolated prompts,
pair-specific schemas, pre-AI corruption, retained failure classes,
completion/usage failures, missing/duplicate units, provenance/raw tampering,
global fact-ID collisions, UNKNOWN, output retention, deterministic aggregation,
and the corrected Program Longword p446 boundary.

Passing model-free CI at the exact revision must precede any future inference.
Gate 5.5/Gate 5.6 do not by themselves authorize model execution, live provider
integration, HIL, hardware, deployment, canonical admission, production
programming, or destructive security operations.
