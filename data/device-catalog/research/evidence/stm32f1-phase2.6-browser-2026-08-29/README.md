# STM32F1 Phase 2.6.3 retained browser evidence

Evidence ID: `stm32f1-phase2.6.3-browser-20260829T130248Z-075cb97`

This package retains the successful Phase 2.6.2 authoritative ST browser
acquisition executed from `physicslu/plasma` commit
`075cb979e1c9e5fd5a75f8e11b81d0aa6bfdfaa7`.

Observed result:

- control target: 1/1 successful;
- bounded pilot: 6/6 successful;
- exact ICPN candidates: 26;
- Phase 2.5 exact baseline match: true;
- candidate drift: zero;
- evaluator decision: `scale_ready`;
- `canonical_dataset_admission`: false.

## Files

- `control-summary.json`: successful `STM32F100C8` control acquisition.
- `pilot-summary.json`: six per-target evidence records and aggregate mappings.
- `evaluation.json`: deterministic baseline and scale-readiness evaluation.
- `provenance.json`: acquisition environment, source commit and baseline identity.
- `manifest.json`: SHA-256 integrity records for every other retained file.

The package does not contain rendered DOM bodies or raw HTTP bodies. Each browser
record retains `rendered_dom_sha256` and `evidence_section_sha256` integrity
identifiers. Browser evidence never claims `raw_sha256`.

Validate offline from the repository root:

```bash
python data/device-catalog/research/validate_stm32f1_retained_evidence.py
```

This evidence is research provenance only. It must not be interpreted as adding
rows to `stm32f1-commercial-icpn.csv`; canonical admission remains a separate
Phase 2.7 decision.
