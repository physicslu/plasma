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

## Governance boundary

Normal discovery automation may determine *what to inspect next* and may materialize
research metadata. It must not:

- admit an ICPN to canonical Production;
- claim programming-algorithm equivalence;
- enable runtime or REST support;
- claim hardware/socket qualification.

Those remain separate controlled transactions.
