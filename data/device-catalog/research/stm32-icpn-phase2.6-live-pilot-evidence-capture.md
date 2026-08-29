# STM32 ICPN Phase 2.6 — Live Pilot Evidence Capture

**Research date:** 2026-08-29

## Decision target

Phase 2.6 closes the evidence gap left by Phase 2.5: the controlled pilot logic is already deterministic and fail-closed, but scale-out must not be approved until the repository's real HTTP transport captures auditable evidence from the six official ST product pages.

This phase deliberately does **not** add commercial ICPNs to `stm32f1-commercial-icpn.csv` and does not expand the manifest beyond the existing six targets.

## Control-plane split

Two validation planes remain intentionally separate:

```text
normal PR CI
    |
    +--> no live st.com access
    +--> parser tests
    +--> bounded-pilot tests
    +--> live-evidence evaluator tests
    +--> manual-workflow contract tests

manual GitHub Actions workflow
    |
    +--> workflow_dispatch only
    +--> bounded six-target manifest
    +--> rate-limited official ST HTTP fetch
    +--> raw response SHA-256
    +--> evidence-section SHA-256
    +--> ETag / Last-Modified capture when supplied
    +--> candidate-set drift evaluation
    +--> 90-day workflow artifact
    +--> scale-ready or fail-closed result
```

The manual workflow is `.github/workflows/stm32f1-live-acquisition-pilot.yml`. It has no `push` or `pull_request` trigger and uses read-only repository permissions.

## Conservative live transport

`run_stm32f1_live_pilot.py` wraps the Phase 2.5 batch runner with an explicit inter-request delay. The default delay is two seconds and the wrapper rejects values below one second.

The existing protections remain in force:

- manifest hard limit: 10 targets;
- checked-in pilot size: 6 targets;
- sequential acquisition;
- approved host: `www.st.com` only;
- HTTPS only;
- canonical English product HTML page only;
- redirect destination revalidated;
- accepted content type limited to HTML/XHTML;
- response size capped at 5 MiB;
- parser fails closed on missing or foreign evidence tokens.

This is a research acquisition path, not a general crawler.

## Candidate-drift baseline

`stm32f1-acquisition-pilot-baseline.json` records the 26 exact strings observed from the official ST source surface during Phase 2.5.

The baseline has an explicit:

```json
"canonical_dataset_admission": false
```

It exists only to detect source drift. It is not commercial dataset admission evidence and must never be copied automatically into `stm32f1-commercial-icpn.csv`.

The evaluator compares exact candidate sets per base device rather than only the total candidate count. A 26-to-26 replacement therefore still fails closed and requires review.

## Scale-readiness evaluator

`evaluate_stm32f1_live_pilot.py` requires all of the following for `scale_ready = true`:

1. pilot ID matches the checked-in baseline;
2. all six targets were attempted;
3. acquisition success is 6/6 with zero acquisition failures;
4. `manual_intervention_required = 0`;
5. canonical mapping is unique for 6/6 targets;
6. OpenOCD CFG mapping is complete for 6/6 targets;
7. every target has an approved ST source/final URL;
8. every target has a retrieval timestamp;
9. every target has a valid raw-response SHA-256;
10. every target has a valid evidence-section SHA-256;
11. every target uses the expected `quality_and_reliability_part_number` evidence surface;
12. the exact candidate set for every base device matches the checked-in Phase 2.5 research baseline.

`ETag` and `Last-Modified` availability is reported but is **not** a hard success requirement. Those response headers are controlled by the origin/CDN and may legitimately be absent. The raw-response and evidence-section digests are the mandatory integrity records.

## Artifact contract

A manual run uploads a 90-day artifact named from the GitHub run ID and attempt. It contains, when produced:

- `live-summary.json` — Phase 2.5 runner KPI and per-target evidence;
- `live-evaluation.json` — Phase 2.6 scale-readiness decision, candidate drift and run metadata;
- `stm32f1-acquisition-pilot-manifest.json` — exact target manifest used by the run;
- `stm32f1-acquisition-pilot-baseline.json` — research-only candidate baseline used for drift detection.

The evaluation record carries the GitHub run ID, run attempt, repository and Git SHA supplied by the workflow environment.

The artifact is evidence for research review. It does not mutate the repository or canonical dataset.

## Bootstrap sequencing

GitHub `workflow_dispatch` workflows must exist on the repository's default branch before they can be used as the normal manual Actions entry point. Therefore the Phase 2.6 control-plane implementation must merge before the first authoritative manual run can be captured through this workflow.

That sequencing creates two distinct claims:

1. **Before merge:** deterministic CI can prove the live-evidence contract, evaluator, request pacing, workflow trigger boundary and fail-closed logic.
2. **After merge and manual workflow execution:** the resulting artifact can prove or disprove live transport/evidence scale-readiness.

This implementation PR must therefore **not** claim that the six-target live run has already succeeded.

## Current agent-environment limitation

During Phase 2.6 implementation, a direct transport attempt from the agent's execution container failed at DNS resolution for `www.st.com`. The environment therefore cannot substitute for the GitHub-hosted live runner and cannot produce the required raw-response evidence locally.

Web-visible source inspection is not equivalent to the raw HTTP evidence contract and is not accepted as a replacement.

## Post-merge decision gate

After the workflow exists on `main`, run **STM32F1 live acquisition pilot** once and inspect its artifact.

A scale-out decision requires:

```text
attempted                         6
acquisition_success               6
acquisition_failure               0
canonical_mapping.unique          6
canonical_mapping.ambiguous       0
canonical_mapping.unmapped        0
openocd_cfg_mapping               6 / 6
manual_intervention_required      0
transport evidence records        6 / 6
candidate baseline match          true
scale_ready                       true
```

If any condition fails, classify the failure before changing the dataset or parser:

- network/origin availability;
- redirect/content-type behavior;
- source-layout/parser assumption;
- exact commercial candidate drift;
- canonical mapping ambiguity;
- OpenOCD capability mapping;
- provenance/integrity-record failure.

Do not normalize a failure away merely to recover a green result.

## Explicitly out of scope

Phase 2.6 does not:

- admit the 26 candidate strings into the commercial ICPN dataset;
- sweep the remaining STM32F1 base devices;
- infer commercial order codes from datasheet grammar;
- change production runtime, Web UI or APIs;
- deploy or restart Plasma services;
- operate Z2, FPGA or real IC hardware.
