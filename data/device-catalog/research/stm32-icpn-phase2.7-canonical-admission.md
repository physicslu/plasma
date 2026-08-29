# STM32 ICPN Phase 2.7 — Canonical Admission

## Decision

Phase 2.7 admits only the 26 exact commercial ICPNs retained by Phase 2.6.3
evidence package:

```text
evidence/stm32f1-phase2.6-browser-2026-08-29/
```

Evidence ID:
`stm32f1-phase2.6.3-browser-20260829T130248Z-075cb97`.

No live manufacturer acquisition occurs in this phase. The checked-in evidence,
canonical commercial CSV, OpenOCD mapping catalog and Phase 2.5 baseline are the
complete deterministic inputs.

## Admission result

The pre-write plan is retained in
`stm32f1-phase2.7-admission-plan.json` and records:

```text
candidates                  26
admit                       26
already_present              0
manual_review_required       0
reject                       0
conflicts                    0
canonical rows before       23
canonical rows after        49
```

Each candidate record links the exact ICPN to its base device, official ST URL,
evidence ID, rendered-DOM/evidence-section digests, unique canonical mapping,
OpenOCD CFG and proposed canonical row. Candidate order is fixed by manufacturer,
base device and ICPN.

## Evidence linkage

Canonical schema remains unchanged. Each admitted row uses the official ST
product URL with a `#plasma-evidence=<evidence_id>` fragment in
`source_reference`. The admission plan retains the complete row-to-evidence
digest linkage. Together these answer why a canonical ICPN exists without
creating a competing dataset or changing the CSV data contract.

## Fail-closed and idempotency contract

`plan_stm32f1_canonical_admission.py` validates retained evidence before making
any decision. It separates `admit`, `already_present`,
`manual_review_required` and `reject`. Mapping, integrity, duplicate or semantic
conflicts cannot be normalized into admission.

`write_stm32f1_canonical_admission.py` accepts only a clean plan tied to the
exact pre-write canonical hash. Reapplying the same plan to its already-applied
result is an explicit no-op. Replanning after write produces:

```text
admit                        0
already_present             26
manual_review_required       0
reject                       0
conflicts                    0
```

`validate_stm32f1_admission_plan.py` validates both the checked-in pre-write
decision and the post-write canonical result entirely offline. Normal CI does
not install a browser or contact ST.

## Scope boundary

This phase does not modify the retained evidence or Phase 2.5 baseline, infer
unlisted commercial identifiers, acquire other devices/vendors, modify runtime
Web/API code, deploy Plasma, restart services or operate FPGA/Z2/real IC
hardware.
