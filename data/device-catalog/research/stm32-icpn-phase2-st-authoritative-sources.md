# STM32 Commercial ICPN Phase 2 — ST-authoritative STM32F1 vertical slice

**Retrieval date:** 2026-08-29

**Implemented slice:** STM32F103C8 only (four exact order codes)

**Dataset:** `data/device-catalog/research/stm32f1-commercial-icpn.csv`

**Validator:** `data/device-catalog/research/validate_stm32f1_commercial_icpn.py`

## 1. Executive conclusion

**VERIFIED FACT.** The official STMicroelectronics STM32F103C8 product page explicitly lists four exact
commercial part numbers: `STM32F103C8T6`, `STM32F103C8T6TR`, `STM32F103C8T7`, and
`STM32F103C8T7TR`. These are the only commercial ICPNs admitted to this Phase 2 dataset.

**VERIFIED FACT.** ST datasheet DS5319 Rev 20 defines `C` as 48 pins, `8` as 64 KiB Flash, `T` as LQFP,
temperature suffix `6` as -40 to 85 °C, suffix `7` as -40 to 105 °C, and `TR` as tape-and-reel. The
datasheet's ordering scheme explains fields; it is not treated as evidence that every syntactically possible
combination is an available commercial product.

**DERIVED DETERMINISTIC MAPPING.** Removing only the package, temperature, and option fields identified by
DS5319 maps each of the four exact ICPNs to base device `STM32F103C8`. ST's versioned CMSIS Device F1 header
names `STM32F103C8`, and Plasma's existing canonical CSV contains exactly one `cmsis_device_name` row with
that identifier and `tcl/target/stm32f1x.cfg`.

**INFERENCE / UNRESOLVED.** This is a deliberately narrow vertical slice, not a complete STM32F1 commercial
catalog. No documented official ST bulk catalog/API was established in this pass. The other 94 STM32F1 base
identifiers in Plasma's 95-row F1 subset were not converted to commercial ICPNs and no codes were generated
from their names.

## 2. Authoritative ST sources

| Source | Official reference | Type | What it proves | What it does not prove | Completeness claim | Machine-readable |
|---|---|---|---|---|---|---|
| STM32F103C8 product page | <https://www.st.com/en/microcontrollers-microprocessors/stm32f103c8.html> | Official ST product page | The four exact order codes in this dataset; page-level active product context | All STM32F1 order codes; CMSIS identity; OpenOCD support | No explicit completeness claim; four codes are visibly listed for this page | Semi-structured HTML, not a documented bulk API |
| DS5319 Rev 20, STM32F103x8/xB datasheet | <https://www.st.com/resource/en/datasheet/stm32f103c8.pdf> | Official ST datasheet, ordering-information scheme | Meaning of the C/8/T/6/7/TR fields used by the four directly listed codes | Current availability of every syntactically legal combination; family-wide universal rule | Explicitly directs readers to ST for available options; no catalog-completeness claim | PDF; extractable text, but not a catalog API |
| STM32CubeF1 CMSIS Device header, tag v4.3.3 | <https://github.com/STMicroelectronics/cmsis-device-f1/blob/v4.3.3/Include/stm32f1xx.h> | Versioned ST-maintained CMSIS source | `STM32F103C8` is a named CMSIS/base-device identity in the STM32F103xB group | Exact commercial order codes, package/temperature options, availability, or OpenOCD capability | No commercial-catalog claim | Yes, C header source |

All sources were retrieved on 2026-08-29. The GitHub source is used only for the CMSIS identity it actually
declares; it is not used as commercial-part ground truth.

## 3. Source authority hierarchy

1. An official ST product page directly listing an exact part number is the commercial-identity authority for
   this slice.
2. The official ST datasheet supplies field semantics for an already-listed exact code. It does not authorize
   bulk expansion of the ordering scheme.
3. The official STM32Cube/CMSIS header supplies firmware identity only.
4. Plasma's local canonical CSV supplies existing catalog and OpenOCD-capability linkage only.

No distributor, community page, mirror, search snippet, or OpenOCD file is used as commercial-identity
authority.

## 4. STM32F1 ordering-code model

This model is evidence-backed for the STM32F103x8/xB scope of DS5319 only. It is not asserted as a universal
STM32F1 or STM32 rule.

```text
STM32 F 103 C 8 T 6 [TR]
│     │ │   │ │ │ │  └─ option: tape and reel when explicitly present
│     │ │   │ │ │ └──── temperature range: 6 or 7
│     │ │   │ │ └────── package: T = LQFP
│     │ │   │ └──────── flash: 8 = 64 KiB
│     │ │   └────────── pin-count code: C = 48 pins
│     │ └────────────── device subfamily: 103
│     └──────────────── product type: F
└────────────────────── STM32 device family
```

`STM32F103C8` is a base/CMSIS-style identity. `STM32F103C8T6` is an exact commercial ICPN. The latter
appears verbatim on the official ST product page; it was not generated from the former.

## 5. Exact ICPN examples with provenance

| Exact ICPN | Direct commercial evidence | Ordering-field evidence | Evidence class |
|---|---|---|---|
| `STM32F103C8T6` | STM32F103C8 official ST product page | DS5319 Rev 20 section 7 | VERIFIED FACT |
| `STM32F103C8T6TR` | STM32F103C8 official ST product page | DS5319 Rev 20 section 7 | VERIFIED FACT |
| `STM32F103C8T7` | STM32F103C8 official ST product page | DS5319 Rev 20 section 7 | VERIFIED FACT |
| `STM32F103C8T7TR` | STM32F103C8 official ST product page | DS5319 Rev 20 section 7 | VERIFIED FACT |

## 6. Canonical schema

The requested schema is used unchanged. Each row is one exact, non-wildcard ICPN. `option_suffix` is empty
for a standard code and `TR` only when `TR` occurs in the ST-listed code. `source_reference` records both the
direct exact-code page and the ordering-field datasheet. Missing evidence would remain empty rather than be
inferred.

`mapping_status = deterministic_pattern` means that an official ST ordering scheme deterministically reduces
the already-proven exact ICPN to a base identity which exactly matches the Plasma row. It does **not** mean
that a Plasma wildcard was expanded into a commercial code.

## 7. Mapping to the existing Plasma catalog

```text
official ST exact ICPN
    └─ DS5319 field decomposition → STM32F103C8
         └─ ST CMSIS Device F1 v4.3.3 → STM32F103C8 / STM32F103xB
              └─ openocd-parts-canonical.csv
                   part_number = STM32F103C8
                   identifier_kind = cmsis_device_name
                   mapping_status = mapping_candidate
                   validation_status = not_verified
```

**DERIVED DETERMINISTIC MAPPING.** All four dataset rows map to the same one canonical Plasma row. Commercial
identity remains in the Phase 2 dataset; the canonical OpenOCD-derived CSV is not modified.

## 8. Mapping to OpenOCD capability evidence

The matched Plasma row carries `target_config = tcl/target/stm32f1x.cfg`,
`openocd_distribution = upstream-openocd`, `mapping_status = mapping_candidate`, and
`validation_status = not_verified`.

**VERIFIED FACT.** This is what the existing Plasma CSV records.

**INFERENCE / UNRESOLVED.** It does not prove that a real STM32F103C8T6/T7 device was detected, erased,
programmed, verified, or read. No runtime silicon ID, OpenOCD execution, Z2 test, or target-electrical evidence
was collected. OpenOCD remains capability evidence, not commercial identity.

## 9. Deterministic validation statistics

Validator result for the checked-in working-tree dataset:

| Metric | Result |
|---|---:|
| Exact ICPN rows | 4 |
| Unique ICPNs | 4 |
| Duplicate ICPNs | 0 |
| Wildcard/invalid ICPNs | 0 |
| ICPNs lacking authoritative ST provenance | 0 |
| Direct-ST-evidence rows | 4 |
| Base devices | `STM32F103C8`: 4 |
| Packages | `LQFP`: 4 |
| CMSIS mapping coverage | 4/4 (100%) |
| Plasma canonical mapping coverage | 4/4 (100%) |
| OpenOCD CFG mapping coverage | 4/4 (100%) |
| Ambiguous mappings | 0 |
| Unmapped ICPNs | 0 |

These percentages describe only the four-row authoritative slice, never the full STM32F1 or STM32 product
universe.

## 10. Ambiguous and conflicting cases

No conflicting authoritative evidence was found among the three sources for these four exact codes. The
validator fails on duplicate ICPNs and on an asserted mapping that does not match the canonical Plasma row,
so conflicting duplicate rows cannot be silently collapsed.

No ambiguous mapping exists inside the four-row slice. The 94 other Plasma STM32F1 base identities are
**unresolved outside the dataset scope**, not silently classified as commercial ICPNs.

## 11. What remains unproven

- Completeness of the STM32F1 commercial product universe.
- Exact commercial ICPNs for the other 94 STM32F1 base identifiers in Plasma.
- A documented official ST bulk machine-readable catalog/API suitable for reproducible family-wide ingestion.
- Current lifecycle/orderability semantics beyond what the retrieved product page displays.
- Runtime silicon-ID correspondence to a commercial package/temperature/order option.
- OpenOCD execution, flash-driver success, Z2 behavior, or real-target programming.
- Applicability of the DS5319 STM32F103x8/xB ordering scheme to other STM32F1 or STM32 families.

## 12. Recommended scale-out strategy

1. Identify a documented official ST bulk export/API, or freeze a versioned set of official ST product-page
   records with retrieval metadata.
2. Admit an exact ICPN only when it occurs verbatim in that ST evidence.
3. Pair each product group with the applicable official datasheet ordering scheme; never reuse DS5319 rules
   across families without evidence.
4. Map exact ICPN → base device using versioned, per-datasheet parsers with fixtures.
5. Map base device → CMSIS identity using a pinned ST CMSIS release.
6. Join to Plasma without altering the OpenOCD-derived source catalog, preserving ambiguous and unmapped rows.
7. Validate one STM32F1 product group at a time before considering other STM32 families.

## 13. Exact commands and method

Research was restricted to official ST sources and the versioned ST-maintained CMSIS repository. The local
mapping source was read, not modified.

```bash
python3 data/device-catalog/research/validate_stm32f1_commercial_icpn.py
git diff --check
git status --short
```

Deterministic method:

1. Transcribe only the four exact part numbers displayed by the official STM32F103C8 product page.
2. Decode attributes only where DS5319 Rev 20 explicitly defines the corresponding field.
3. Confirm the base identity in ST CMSIS Device F1 tag v4.3.3.
4. Join `base_device` to `part_number` in `openocd-parts-canonical.csv` and require the stored
   `identifier_kind` and `target_config` to match the dataset.
5. Run the validator, which fails closed for wildcard/invalid ICPNs, missing direct ST provenance, duplicate
   ICPNs, unsupported mapping states, missing asserted canonical mappings, or identity/capability conflation.

No production code, canonical OpenOCD-derived data, deployment, service, FPGA, or hardware state was changed.
