# STM32F2 bounded discovery batch workflow

This workflow exists to keep normal ICPN discovery batches deterministic and cheap.
A normal batch should not require a new phase-specific Python discovery or retained-
evidence validator.

## 1. Build a read-only plan

```bash
python data/device-catalog/research/stm32f2_bounded_discovery.py plan \
  --phase <PHASE> \
  --date YYYY-MM-DD \
  --output /tmp/stm32f2-next-batch-plan.json
```

The planner derives from the current canonical STM32F2 Production dataset and guarded
OpenOCD catalog:

- the complete current Production Base Device boundary;
- the normalized Production-boundary SHA-256;
- the lexicographically first unadmitted Base Device in each guarded STM32F2
  subfamily;
- official ST product-page URLs;
- the registry entry, manifest filename, baseline filename and evidence directory;
- input SHA-256 bindings for registry, OpenOCD catalog and canonical Production.

The planner does not write Production, the registry or a discovery manifest.

## 2. Materialize the research transaction

After reviewing the plan:

```bash
python data/device-catalog/research/stm32f2_bounded_discovery.py materialize \
  --plan /tmp/stm32f2-next-batch-plan.json
```

Materialization first rebuilds the plan from current inputs. Any Production, catalog,
registry or target-selection drift fails closed. On success it writes only:

- the new entry in `stm32f2-bounded-discovery-batches.json`;
- the new discovery manifest.

It does **not** write the canonical ICPN dataset and does not authorize admission.

## 3. Run the registered discovery

```bash
python data/device-catalog/research/stm32f2_bounded_discovery.py \
  --phase <PHASE> \
  --output /tmp/stm32f2-pilot-summary.json
```

Browser acquisition remains bounded, read-only and fail-closed.

## 4. Retain and validate evidence

Once immutable baseline/provenance/evidence packaging has been created, replay it with:

```bash
python data/device-catalog/research/stm32f2_bounded_evidence.py \
  --phase <PHASE>
```

Discovery evidence remains separate from policy and canonical admission.

## 5. Historical golden replay

The offline regression gate reconstructs the historical Production boundaries for
Phase 4.3E and Phase 4.3H from the current canonical dataset, re-runs the generic
planner against those boundaries, and requires the resulting registry state and
target identities to match the retained historical transactions.

```bash
python data/device-catalog/research/test_stm32f2_bounded_historical_golden_replay.py
```

This test uses only repository data. It does not access ST web pages and does not
write Production.

## 6. Live shadow comparison

A live shadow run reuses an already registered phase and writes only temporary output.
It compares current ST rendered-DOM results with retained evidence and classifies the
result as:

- `clean`: target identity and active/lifecycle data match retained evidence;
- `source_drift`: the bounded software contract remains valid, but ST active or
  lifecycle data changed;
- `software_regression`: target identity, authority claims, acquisition contract, or
  OpenOCD mapping invariants changed.

Example headed Chromium run:

```bash
python data/device-catalog/research/stm32f2_bounded_shadow.py acquire \
  --phase 4.3H \
  --output /tmp/stm32f2-phase4.3h-live-shadow.json \
  --report /tmp/stm32f2-phase4.3h-shadow-report.json
```

The live shadow command refuses to write its output under the retained `evidence/`
tree. Exit status is `0` for clean, `2` for source drift, and `1` for software or
acquisition regression. Because ST web availability is an external dependency, live
shadow acquisition is not a normal merge gate.

An already captured summary can be compared offline:

```bash
python data/device-catalog/research/stm32f2_bounded_shadow.py compare \
  --phase 4.3H \
  --live-summary /tmp/stm32f2-phase4.3h-live-shadow.json
```

## Governance boundary

Normal discovery automation may determine *what to inspect next* and may materialize
research metadata. It must not:

- admit an ICPN to canonical Production;
- claim programming-algorithm equivalence;
- enable runtime or REST support;
- claim hardware/socket qualification.

Those remain separate controlled transactions.
