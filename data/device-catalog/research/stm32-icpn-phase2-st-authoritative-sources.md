# STM32 Commercial ICPN Phase 2 — ST-authoritative STM32F1 vertical slice

**Retrieval date:** 2026-08-29

**Implemented slice:** `STM32F103C8` (4), `STM32F103CB` (6), `STM32F103RB` (9), and `STM32F103RE` (4): 23 exact commercial ICPNs total.

**Dataset:** `data/device-catalog/research/stm32f1-commercial-icpn.csv`

**Validator:** `data/device-catalog/research/validate_stm32f1_commercial_icpn.py`

## 1. Executive conclusion

**VERIFIED FACT.** The official STMicroelectronics STM32F103C8 product page explicitly lists four exact commercial part numbers: `STM32F103C8T6`, `STM32F103C8T6TR`, `STM32F103C8T7`, and `STM32F103C8T7TR`.

**VERIFIED FACT.** The official ST eStore page for STM32F103CB lists six active exact order codes in the retrieved page: `STM32F103CBT6`, `STM32F103CBT6TR`, `STM32F103CBT7`, `STM32F103CBT7TR`, `STM32F103CBU6`, and `STM32F103CBU6TR`. These strings are admitted because they occur verbatim in an official ST commercial source; none was synthesized from an ordering pattern.

**VERIFIED FACT.** The official STM32F103RB product page lists nine exact commercial order codes: `STM32F103RBH6`, `STM32F103RBH6R`, `STM32F103RBH6RTR`, `STM32F103RBH6TR`, `STM32F103RBH7`, `STM32F103RBT6`, `STM32F103RBT6TR`, `STM32F103RBT7`, and `STM32F103RBT7TR`. The official eStore identifies the `H` variants as TFBGA64 and the `T` variants as LQFP64.

**VERIFIED FACT.** The official STM32F103RE product page was used to admit four exact order codes: `STM32F103RET6`, `STM32F103RET6TR`, `STM32F103RET7`, and `STM32F103REY6TR`.

**VERIFIED FACT.** ST datasheet DS5319 Rev 20 defines the ordering fields used in this slice: `C` = 48 pins, `8` = 64 KiB Flash, `B` = 128 KiB Flash, `T` = LQFP, `U` = VFQFPN or UFQFPN, temperature suffix `6` = -40 to 85 °C, suffix `7` = -40 to 105 °C, and `TR` = tape-and-reel. The STM32F103CB eStore identifies the admitted `U6` variants specifically as UFQFPN 48. DS5319 explicitly directs readers to ST for available options, so the ordering grammar is never used as commercial-availability evidence.

**DERIVED DETERMINISTIC MAPPING.** The 23 exact ICPNs reduce, using only the applicable official ordering schemes, to base identities `STM32F103C8`, `STM32F103CB`, `STM32F103RB`, or `STM32F103RE`. Plasma's canonical OpenOCD-derived catalog contains exactly one asserted `cmsis_device_name` mapping for each base to `tcl/target/stm32f1x.cfg`.

**INFERENCE / UNRESOLVED.** This remains a deliberately narrow STM32F1 evidence slice, not a complete STM32F1 commercial catalog. No documented official ST bulk catalog/API has been established. The other 91 base identifiers in Plasma's 95-row STM32F1 subset remain outside the admitted commercial ICPN dataset.

## 2. Authoritative ST sources

| Source | Official reference | Type | What it proves | What it does not prove |
|---|---|---|---|---|
| STM32F103C8 product page | <https://www.st.com/en/microcontrollers-microprocessors/stm32f103c8.html> | Official ST product page | Four exact C8 commercial order codes | Complete STM32F1 catalog; CMSIS/OpenOCD capability |
| STM32F103CB eStore page | <https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-174-cortex-174-mcus/stm32-mainstream-mcus/stm32f1-series/stm32f103/stm32f103cb.html> | Official ST commercial/eStore page | Six exact CB order codes and displayed package/temperature data | Complete STM32F1 catalog or all historical CB variants |
| DS5319 Rev 20 | <https://www.st.com/resource/en/datasheet/stm32f103cb.pdf> | Official ST datasheet | Meaning of C/8/B/T/U/6/7/TR fields for STM32F103x8/xB | Availability of every syntactically legal combination |
| STM32F103RB product page | <https://www.st.com/en/microcontrollers-microprocessors/stm32f103rb.html> | Official ST product page | Nine exact RB commercial order codes | Complete STM32F1 catalog or all historical RB variants |
| STM32F103RB eStore page | <https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-174-cortex-174-mcus/stm32-mainstream-mcus/stm32f1-series/stm32f103/stm32f103rb.html> | Official ST commercial/eStore page | RB package and temperature data, including TFBGA64 and LQFP64 | Family-wide availability |
| DS5319 Rev 20 (RB reference) | <https://www.st.com/resource/en/datasheet/stm32f103rb.pdf> | Official ST datasheet | Meaning of R/B/H/T/6/7/R/TR fields in the STM32F103x8/xB scope | Availability of every syntactically legal combination |
| STM32F103RE product page | <https://www.st.com/en/microcontrollers-microprocessors/stm32f103re.html> | Official ST product page | Four exact RE commercial order codes | Complete STM32F1 catalog or all historical RE variants |
| DS5792 Rev 13 | <https://www.st.com/resource/en/datasheet/stm32f103re.pdf> | Official ST datasheet | Meaning of R/E/T/Y/6/7/TR fields for STM32F103xC/xD/xE | Availability of every syntactically legal combination |
| STM32CubeF1 CMSIS Device header, tag v4.3.3 | <https://github.com/STMicroelectronics/cmsis-device-f1/blob/v4.3.3/Include/stm32f1xx.h> | Versioned ST-maintained CMSIS source | Firmware/base-device identity evidence | Exact commercial order codes or OpenOCD support |

All commercial identity admitted by this dataset comes from official ST commercial pages. CMSIS and OpenOCD-derived data are used only for downstream identity/capability mapping.

## 3. Source authority hierarchy

1. Official ST commercial/product page that contains an exact order code verbatim.
2. Official ST datasheet for ordering-field semantics of an already-proven code.
3. Versioned ST CMSIS source for firmware/base-device identity.
4. Plasma canonical OpenOCD-derived catalog for existing programming-capability linkage.

Distributor, community, mirror, search-snippet, CMSIS, and OpenOCD data must not be promoted to commercial-part-number authority.

## 4. Ordering-code model within the proven DS5319 scope

```text
STM32 F 103 C 8 T 6 [TR]   -> STM32F103C8 base
STM32 F 103 C B T 6 [TR]   -> STM32F103CB base
STM32 F 103 C B U 6 [TR]   -> STM32F103CB base
STM32 F 103 R B H 6 [R][TR] -> STM32F103RB base
STM32 F 103 R B T 6 [TR]    -> STM32F103RB base
STM32 F 103 R E T 6 [TR]    -> STM32F103RE base
STM32 F 103 R E Y 6 TR      -> STM32F103RE base
```

For the admitted rows:

- `C` = 48 pins
- `8` = 64 KiB Flash
- `B` = 128 KiB Flash
- `T` = LQFP
- `U` = VFQFPN or UFQFPN in DS5319; ST eStore identifies the admitted CB U6 variants as UFQFPN
- `6` = -40 to 85 °C
- `7` = -40 to 105 °C
- `TR` = tape-and-reel
- `R` = 64 pins
- `E` = 512 KiB Flash (DS5792)
- `H` = BGA in the ordering scheme; the admitted RB products are identified by ST eStore as TFBGA64
- `Y` = WLCSP64 (DS5792)
- option `R` in the RB `H6R` codes is retained only because the exact strings are directly listed by ST

The ordering model decodes exact ST-listed products; it does not create products.

## 5. Exact commercial ICPNs admitted

### STM32F103C8

- `STM32F103C8T6`
- `STM32F103C8T6TR`
- `STM32F103C8T7`
- `STM32F103C8T7TR`

### STM32F103CB

- `STM32F103CBT6`
- `STM32F103CBT6TR`
- `STM32F103CBT7`
- `STM32F103CBT7TR`
- `STM32F103CBU6`
- `STM32F103CBU6TR`

### STM32F103RB

- `STM32F103RBH6`
- `STM32F103RBH6R`
- `STM32F103RBH6RTR`
- `STM32F103RBH6TR`
- `STM32F103RBH7`
- `STM32F103RBT6`
- `STM32F103RBT6TR`
- `STM32F103RBT7`
- `STM32F103RBT7TR`

### STM32F103RE

- `STM32F103RET6`
- `STM32F103RET6TR`
- `STM32F103RET7`
- `STM32F103REY6TR`

Separate CB, RB, and RE evidence notes record each product-specific source boundary.

## 6. Canonical schema and identity boundary

Each CSV row is one exact, non-wildcard commercial ICPN. `base_device`, `cmsis_device_name`, and `existing_identifier` are distinct from `icpn`. `openocd_target_config` is programming-capability evidence only.

`mapping_status = deterministic_pattern` means an already-authoritative exact ICPN is deterministically reduced to a base identity using the applicable ST ordering scheme. It does **not** mean a wildcard/pattern was expanded into an ICPN.

## 7. Mapping to Plasma and OpenOCD capability

```text
ST exact commercial ICPN
    -> applicable official datasheet field decomposition
        -> STM32F103C8, STM32F103CB, STM32F103RB, or STM32F103RE
            -> ST CMSIS/base identity
                -> Plasma openocd-parts-canonical.csv
                    -> identifier_kind = cmsis_device_name
                    -> target_config = tcl/target/stm32f1x.cfg
```

**DERIVED DETERMINISTIC MAPPING.** All 23 admitted rows map through their base identity to exactly one asserted canonical Plasma row and the STM32F1 OpenOCD target configuration.

**INFERENCE / UNRESOLVED.** This does not prove successful detection, erase, program, verify, or read on a physical target. No runtime silicon-ID, electrical, Z2, or real-IC validation is claimed.

## 8. Deterministic validation statistics

Local validation passed for the expanded dataset; the PR must also pass GitHub Actions `validate-device-catalog` before merge-ready.

| Metric | Result |
|---|---:|
| Exact ICPN rows | 23 |
| Unique ICPNs | 23 |
| Duplicate ICPNs | 0 |
| Wildcard/invalid ICPNs | 0 |
| ICPNs lacking authoritative ST provenance | 0 |
| Direct-ST-evidence rows | 23 |
| Base-device distribution | `STM32F103C8`: 4; `STM32F103CB`: 6; `STM32F103RB`: 9; `STM32F103RE`: 4 |
| Package distribution | `LQFP`: 15; `TFBGA`: 5; `UFQFPN`: 2; `WLCSP64`: 1 |
| CMSIS mapping coverage | 23/23 (100%) |
| Plasma canonical mapping coverage | 23/23 (100%) |
| OpenOCD CFG mapping coverage | 23/23 (100%) |
| Ambiguous mappings | 0 |
| Unmapped ICPNs | 0 |

These percentages describe only this 23-row evidence slice and must not be represented as STM32F1-wide coverage.

## 9. What remains unproven

- Completeness of the STM32F1 commercial product universe.
- Exact commercial ICPNs for the other 91 STM32F1 base identifiers in Plasma's current F1 subset.
- A documented official ST bulk machine-readable product catalog/API suitable for reproducible family-wide ingestion.
- Historical or lifecycle completeness of the retrieved commercial pages.
- Runtime silicon-ID correspondence to commercial package/temperature/packing variants.
- Real OpenOCD execution, flash-driver success, Z2 behavior, socket/electrical behavior, or physical programming.
- Applicability of DS5319 ordering semantics outside the STM32F103x8/xB scope it documents.

## 10. Scale-out strategy

1. Expand one official ST product group at a time.
2. Admit only exact strings present in official ST commercial evidence.
3. Pair each group with its applicable official datasheet; never generalize a naming grammar across families without evidence.
4. Run the fail-closed validator through GitHub Actions on every dataset change.
5. Preserve ambiguous/unmapped cases rather than forcing a capability join.
6. Periodically reassess whether ST exposes a documented bulk export/API before scaling to hundreds or thousands of exact order codes.

## 11. Validation command

```bash
python data/device-catalog/research/validate_stm32f1_commercial_icpn.py
```

The same command is executed by `.github/workflows/device-catalog-validation.yml` on pull requests. No canonical OpenOCD source data, production runtime code, deployment, FPGA configuration, or hardware state is changed by this research slice.
