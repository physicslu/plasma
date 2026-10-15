# ST ADR-0002 Phase 1 — field-level IC Information baseline v1

**Scope:** ADR-0002 **Phase 1 / 01 IC Information only** for all currently admitted
STMicroelectronics Production exact ICPNs.

This transaction does not change Production admission, public Catalog eligibility,
Programming Profile, OpenOCD software qualification, VPP, PPU/Site/Socket state, or HIL.

## Why this exists

The historical ST Manufacturer Device Basic Profile program used an all-or-nothing M1
family admission rule and allowed only Product Selector/eStore derivation. That program
finished with 1,622 admitted exact ICPNs and 3,007 exact ICPNs in
`blocked_evidence_gap`.

ADR-0002 changed the active information model. Phase 1 requires **independent per-field
manufacturer evidence** with `VERIFIED / PARTIAL / UNKNOWN / CONFLICT` states. A missing
VDDA, incomplete family RAM table, or a Basic Profile representation limitation must not
erase already-known Flash, package, temperature, RAM, or VDD fields.

Therefore:

> `blocked_evidence_gap` is retained only as historical review context. It is not an
> ADR-0002 Phase 1 field state.

## Deterministic baseline

`st_phase1_information_v1.py` replays:

1. the Production manifest and all ST exact-ICPN source CSVs, verifying each manifest
   SHA-256 and row count;
2. the existing ST Device Basic Profile exact bindings;
3. the historical remaining-ST M1 disposition ledger as context only.

The baseline denominator is **4,629 exact ST Production ICPNs**.

For every exact ICPN it emits these Phase 1 fields:

- manufacturer
- exact ICPN
- Base Device
- Package
- Pin Count
- Flash
- RAM
- Working VDD
- I/O Supply
- VDDA
- Temperature

The existing Production exact identity rows provide manufacturer source references for
identity/package/pin/Flash/temperature. The 1,622 existing exact Basic Profile bindings
supply already-admitted source-backed RAM/Working-VDD evidence and optional rails.

The other 3,007 rows initially remain `UNKNOWN` for RAM/Working VDD in this baseline.
That means **not yet projected into the ADR-0002 Phase 1 ledger**, not “ST has no such
specification”. Their official Product Page/Datasheet/Product Selector/eStore sources can
be acquired or replayed field-by-field in later bounded Phase 1 transactions.

## Important correction versus legacy M1

For example, `STM32H503CBT7` was blocked by the old Basic Profile model because the
Production temperature text contains conditional semantics:

`-40..105; up to 125 at low dissipation`

ADR-0002 Phase 1 explicitly requires preserving original manufacturer wording instead of
forcing every field into a simplified numeric range. The new baseline therefore keeps that
temperature field `VERIFIED` while RAM/VDD can remain independently `UNKNOWN`.

Likewise, `STM32F407VGT6` keeps its exact Production identity, package, pins, Flash and
temperature evidence even while RAM/VDD await Phase 1 source projection.

## Source policy

Phase 1 authority is **manufacturer official evidence**, not the historical
Product-Selector/eStore-only M1 rule. Official source types already present in Production
include retained ST Product Pages, ordering information and ST Datasheets.

A future field acquisition may use a targeted official ST Datasheet or equivalent official
source when its applicability and locator are recorded. It must preserve the exact source
scope and must not infer a value solely from a family name.

OpenOCD, Programming Guides used for programming semantics, VPP requirements, erase/program
algorithms, Socket information and HIL are outside this transaction.

## Run

From the repository root:

```bash
python data/device-catalog/research/st_phase1_information_v1.py
python data/device-catalog/research/st_phase1_information_v1.py \
  --ledger /tmp/st-phase1-ledger.json \
  --summary /tmp/st-phase1-summary.json

python -m pytest -q \
  data/device-catalog/research/test_st_phase1_information_v1.py
```

## Acceptance boundary

This baseline is the starting point for ST Phase 1 field acquisition. It is intentionally
conservative: it reuses evidence already present in the repository, quantifies remaining
field gaps, and does not invent RAM/VDD values from naming patterns.

The next ST Phase 1 work should consume the per-family/per-field `UNKNOWN` counts and
close them from official manufacturer sources, prioritizing reusable official datasheet or
parametric evidence with explicit exact-ICPN applicability. Phase 2 Programming and
External VPP remain deferred.
