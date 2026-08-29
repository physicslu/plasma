# STM32 ICPN Phase 2.5 — Controlled Batch Acquisition Pilot

**Research date:** 2026-08-29

## Decision target

Phase 2.5 tests whether the Phase 2.4 official-ST-page acquisition architecture can scale beyond the four already-admitted STM32F103 base devices without turning the research process into unbounded crawling or automatic dataset promotion.

The pilot is intentionally bounded to six base devices spanning distinct STM32F1 product groups, and the runner enforces a hard maximum of 10 targets per manifest so this research path cannot silently become an unbounded crawler:

- STM32F100C8
- STM32F101C8
- STM32F102C8
- STM32F103ZE
- STM32F105RC
- STM32F107VC

The checked-in manifest is `stm32f1-acquisition-pilot-manifest.json`. The batch runner is `stm32f1_acquisition_pilot.py`.

## Architecture under test

```text
bounded pilot manifest (hard max: 10 targets)
        |
        v
sequential official ST acquisition
        |
        v
Phase 2.4 fail-closed parser
        |
        +--> acquisition status
        +--> exact ICPN candidate count
        +--> source provenance digest
        v
canonical catalog mapping classification
        |
        +--> unique / ambiguous / unmapped
        +--> OpenOCD CFG availability
        v
pilot KPI summary
```

The runner emits candidate evidence only. It never writes `stm32f1-commercial-icpn.csv` and never infers missing commercial order codes from datasheet grammar.

## Live official-source surface observation

The six canonical ST product pages were inspected directly on 2026-08-29. All six exposed a server-visible `Quality and Reliability` section with an explicit `Part Number` table.

| Base device | Official ST product page | Observed exact candidates | Count |
|---|---|---|---:|
| STM32F100C8 | https://www.st.com/en/microcontrollers-microprocessors/stm32f100c8.html | STM32F100C8T6B, STM32F100C8T6BTR, STM32F100C8T7B, STM32F100C8T7BTR | 4 |
| STM32F101C8 | https://www.st.com/en/microcontrollers-microprocessors/stm32f101c8.html | STM32F101C8T6, STM32F101C8T6TR, STM32F101C8U6, STM32F101C8U6TR | 4 |
| STM32F102C8 | https://www.st.com/en/microcontrollers-microprocessors/stm32f102c8.html | STM32F102C8T6, STM32F102C8T6TR | 2 |
| STM32F103ZE | https://www.st.com/en/microcontrollers-microprocessors/stm32f103ze.html | STM32F103ZEH6, STM32F103ZEH6TR, STM32F103ZEH7, STM32F103ZEH7TR, STM32F103ZET6, STM32F103ZET6TR, STM32F103ZET7 | 7 |
| STM32F105RC | https://www.st.com/en/microcontrollers-microprocessors/stm32f105rc.html | STM32F105RCT6, STM32F105RCT6TR, STM32F105RCT6V, STM32F105RCT6W, STM32F105RCT7 | 5 |
| STM32F107VC | https://www.st.com/en/microcontrollers-microprocessors/stm32f107vc.html | STM32F107VCH6, STM32F107VCT6, STM32F107VCT6TR, STM32F107VCT7 | 4 |
| **Total** |  |  | **26** |

These 26 strings are **candidate evidence**, not newly admitted canonical commercial ICPNs.

## Deterministic validation boundary

Normal pull-request CI remains offline with respect to `st.com`.

CI validates:

1. the Phase 2.4 fail-closed product-page parser;
2. pilot manifest schema, URL/base-device correspondence and the hard 10-target bound;
3. batch aggregation behavior for success and fail-closed cases using synthetic HTML;
4. unique mapping of the six pilot base devices into the checked-in canonical catalog;
5. mapping of those bases to `tcl/target/stm32f1x.cfg` capability evidence;
6. a successful acquisition with ambiguous canonical mapping is still classified as requiring intervention.

The checked-in canonical catalog deterministically resolves all six selected bases as unique `cmsis_device_name` rows and maps all six to `tcl/target/stm32f1x.cfg`:

```text
canonical mapping unique    6 / 6
OpenOCD CFG mapping         6 / 6
```

CI does **not** claim that live ST acquisition succeeded at CI execution time.

## KPI interpretation

For a real run of `stm32f1_acquisition_pilot.py`, the JSON summary reports:

```text
attempted
acquisition_success
acquisition_failure
exact_icpn_candidates
canonical_mapping.unique
canonical_mapping.ambiguous
canonical_mapping.unmapped
openocd_cfg_mapping
manual_intervention_required
```

`manual_intervention_required` is raised for any acquisition failure, non-unique canonical mapping, or missing OpenOCD CFG mapping. The CLI returns non-zero whenever this count is non-zero. It is not raised merely because a candidate has not yet been admitted to the commercial dataset.

This is intentionally fail-closed: network extraction success alone is not enough to classify a pilot target as clean.

## What this pilot proves

The live source inspection expands the Phase 2.4 observation from four STM32F103 pages to six additional STM32F1 bases across F100/F101/F102/F103/F105/F107. The same official evidence surface is present across all six sampled pages, including different candidate counts and suffix forms.

The batch runner converts the Phase 2.4 one-page probe into a bounded, auditable research operation with explicit KPI output and no automatic dataset mutation. The six selected bases also have deterministic canonical/OpenOCD capability mappings in the checked-in catalog.

## What this pilot does not prove

The current agent environment can inspect ST's official pages but does not expose the raw response bytes, ETag, or Last-Modified headers needed to execute the repository's `urllib` acquisition path end-to-end here. Therefore the live observations above validate the **source surface**, while the exact transport/digest path remains covered by deterministic unit tests rather than a recorded live batch execution in this PR.

This distinction is material: Phase 2.5 supports scaling the architecture, but a future unattended family sweep should first run the batch runner in an environment with direct ST network access and archive the resulting candidate evidence JSON outside the canonical dataset admission path.

## Scale-out gate after Phase 2.5

Do not immediately sweep all remaining STM32F1 bases. The next scale decision should require:

- zero unexplained parser-layout failures in a direct live pilot run;
- deterministic canonical mapping or explicit ambiguity classification;
- low manual-intervention rate;
- no need to generate commercial codes from grammar;
- evidence that request rate remains conservative and acceptable for ST infrastructure.

Only after those conditions are observed should the manifest expand from a controlled pilot to a broader STM32F1 research sweep.
