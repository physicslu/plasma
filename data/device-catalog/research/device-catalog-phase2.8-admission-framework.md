# Device Catalog Phase 2.8 — Admission Framework Generalization

## Decision

Phase 2.8 generalizes the admission mechanics proven by STM32F1 Phase 2.4–2.7 without changing canonical data. The goal is to separate reusable system-of-record controls from manufacturer/family commercial-identity rules before any scale-out.

This phase is a refactor only:

- canonical STM32F1 rows remain 49;
- the Phase 2.6.3 retained evidence package is unchanged;
- the Phase 2.7 checked-in admission plan remains the historical admission record;
- no new manufacturer evidence is acquired;
- no ICPN is added or removed.

## Architecture inventory before refactor

The Phase 2.7 module combined two different ownership domains.

### Reusable admission mechanics

- deterministic candidate ordering;
- canonical input SHA-256 binding;
- `admit` / `already_present` / `manual_review_required` / `reject` decisions;
- duplicate detection;
- semantic conflict detection;
- clean-plan gating;
- writer refusal after unexpected canonical changes;
- idempotent second write (`no_op`).

### STM32F1/ST-specific policy

- `STMicroelectronics` manufacturer identity;
- approved ST product-page URL validation;
- STM32F1 base-device regular expression;
- exact ICPN prefix/suffix rules;
- package-code decoding (`T`, `U`, `Y`, `H`);
- pin-count decoding from STM32F1 base identity;
- flash-size decoding from STM32F1 base identity;
- temperature-grade decoding (`6`, `7`);
- STM32F1 CMSIS/base-device mapping;
- requirement for one OpenOCD target mapping;
- STM32F1 canonical metadata construction.

A third assumption, `candidate_count == 26`, is not a manufacturer rule and not a reusable admission rule. It is a historical Phase 2.7 batch invariant. Phase 2.8 removes it from the generic clean gate while retaining it in the historical STM32F1 Phase 2.7 wrapper/validator.

## Resulting boundary

```text
Retained / normalized manufacturer evidence
                    |
                    v
         Manufacturer-family policy
         - identity validity
         - metadata derivation
         - source authority
         - programming mapping
                    |
                    v
       Generic admission framework
       - deterministic ordering
       - duplicate/conflict decisions
       - canonical input binding
       - clean-plan gate
       - idempotent writer
                    |
                    v
           Canonical system-of-record
```

Implementation ownership:

- `device_catalog_admission_framework.py` — generic deterministic admission mechanics;
- `stm32f1_admission_policy.py` — STM32F1/ST commercial identity and canonical-row policy;
- `stm32f1_canonical_admission.py` — STM32F1 retained-evidence orchestration plus the historical Phase 2.7 26-candidate boundary.

## Evidence contract

The generic admission framework treats `authoritative_evidence` as an opaque, retained provenance envelope. It does not assume a specific acquisition transport.

This intentionally permits future normalized evidence from sources such as:

- `raw_http`;
- `chromium_rendered_dom`;
- official CSV;
- official JSON/XML;
- other manufacturer-controlled machine-readable sources.

Transport qualification, extraction, and manufacturer authority remain adapter/policy responsibilities. Phase 2.8 does not implement another vendor source adapter and does not introduce a universal scraper.

STM32F1 continues to use the retained `chromium_rendered_dom` evidence from Phase 2.6.3.

## Admission contract

The generic framework owns four decisions only:

- `admit`;
- `already_present`;
- `manual_review_required`;
- `reject`.

A generic clean plan requires:

- decision counts sum to the actual candidate count;
- no `manual_review_required`;
- no `reject`;
- zero semantic conflicts;
- no aggregate issues.

It intentionally does **not** require a fixed candidate count.

Historical Phase 2.7 validation still requires exactly 26 candidates because that number is part of the immutable 2026-08-29 admission event, not a framework rule.

## Fail-closed writer contract

The generic writer:

1. accepts only a clean plan;
2. binds the plan to the canonical dataset semantic SHA-256 observed during planning;
3. refuses a changed canonical dataset unless every planned `admit` row is already present with exactly matching semantics;
4. returns explicit `no_op` when the same plan has already been applied;
5. refuses duplicate ICPNs and malformed canonical rows.

Manufacturer-specific code does not own these controls.

## Regression requirements

Phase 2.8 is accepted only if all of the following remain true:

- current canonical STM32F1 row count: 49;
- current Phase 2.7 evidence candidates: 26;
- post-write planning: 26 `already_present`, 0 `admit`;
- historical pre-write plan semantics match the checked-in Phase 2.7 candidate decisions and proposed rows;
- Phase 2.7 writer remains idempotent;
- retained evidence and canonical CSV content have no Phase 2.8 semantic change.

Generic framework tests additionally cover arbitrary candidate counts, deterministic ordering, duplicate/conflict separation, policy reject/manual-review propagation, canonical-state binding, idempotency, and transport-agnostic evidence envelopes.

## Deliberately retained technical debt

Phase 2.8 does not generalize or implement:

- STM32F1 acquisition scale-out;
- ST browser transport behavior;
- other manufacturer adapters;
- a universal part-number grammar;
- a universal programming-capability resolver;
- a new canonical CSV schema.

Those require evidence from actual next-vendor or next-family integration. Abstracting them now would be speculative.

## Scope boundary

No live ST access, Chromium/Playwright execution, canonical row mutation, Phase 2.5 baseline mutation, retained-evidence mutation, other-device/vendor data, runtime Web/API changes, deployment, service restart, FPGA/Z2 operation, or real-IC operation are part of Phase 2.8.
