# ST Coverage Gap v0.4 — Dual Official-Source Structural Audit

**Reference date:** 2026-09-29. **Research-only; no Production, Active lifecycle, OpenOCD programming or physical validation claims.**

## Material finding

The ST official `STM32_open_pin_data` repository is a **subset of STM32CubeMX (MX1) internal configuration data**, not a complete manufacturer exact-commercial-MPN inventory. Its pinned `mcu` Git tree includes **2,240 XML files** but **232 are STM32MP (MPU)** and are explicitly excluded: the STM32 MCU-only structural footprint in that tree is **2,008 XML configuration patterns**. Many file names contain grouping expressions or `x` wildcards; they are not orderable ICPNs.

ST confirmed publicly that the MX2-only STM32C5 family is **not planned for inclusion in that MX1 XML repository**. For C5, the manufacturer directs users to JSON descriptors from the official [stm32c5xx-dfp](https://github.com/STMicroelectronics/stm32c5xx-dfp) repository. Its pinned `Descriptors/pinout` Git tree includes **46 C5 JSON configuration patterns**. ST's [official software portfolio](https://github.com/STMicroelectronics/STM32Cube_MCU_Overall_Offer) independently lists STM32C5 under HAL2.

Consequently: a single CubeMX1/MX1 export or one `STM32_open_pin_data` tree cannot establish an all-STM32 population. A multi-source acquisition/normalization strategy is necessary, *and even this official dual structural tree still cannot establish the count of Active exact commercial MPNs*.

ST employee clarification, 2026-05-06:
<https://community.st.com/stm32cubemx2-mcus-151/please-keep-updating-the-stm32-open-pin-data-repo-with-new-families-as-of-now-stm32c5xx-165392>

## Exact pinned manufacturer structural inputs

| Surface | ST upstream commit | Directory Git tree SHA | Scope |
| --- | --- | --- | --- |
| MX1 / open_pin_data | `7d1f1514ed5583ec5007ad91236b4e1d377295b1` | `d8715ae7453883f62377e87b529f94012323f062` | `mcu/` subtree, 2,240 XML |
| MX2 / C5 DFP | `a5f65bc64535cfa723e9d25f58d7ce23d0937aed` | `7068a7c4fb580c3f1e7f7d523d13693e54034fbd` | `Descriptors/pinout/` subtree, 46 JSON |
| ST software offer | `3ba0d378f9da6cb480d0293f0ce2fcb53c2f1a21` | README Git blob `6600232eee622f1f8a493b82da6c506468f08929` | Native named family structure incl. C5/H5/N6/WB0/WL3 |

The repo retains each manufacturer's Git tree entry `mode + SHA + filename` in its original tree order under `sources/`. `validate_st_multisource_structure.py` reconstructs and verifies the **Git tree object SHA** from those entries (not merely a freehand table), excludes the MCU/MPU overlap, derives nonoverlapping series pattern counts and validates the v0.2 ST Production source hashes independently.

## Five identified missing-family structural footprints

The five Active official exact-MPN absence sentinels were established in v0.2. Here, *only the additional manufacturer structural source counts* are reported:

| Unrepresented family | MX1 MCU XML pattern files | MX2 C5 pinout JSON pattern files | ST Production exact ICPNs |
| --- | ---: | ---: | ---: |
| STM32C5 | 0 (MX2-only) | 46 | 0 |
| STM32H5 | 151 | 0 | 0 |
| STM32N6 | 28 | 0 | 0 |
| STM32WB0 | 10 | 0 | 0 |
| STM32WL3 | 22 | 0 | 0 |

The five counts are **file/pattern counts**, not Active variants, package options, or commercial ordering numbers; no file-name wildcard is expanded into a guessed exact SKU. N6's pinned OpenOCD path remains a separate external-flash/programming-profile case and is never admitted by structural presence alone.

**Frozen Production ST:** 2,683 unique exact ICPNs / 23 families, original manifest blob `c8012b211a28b0a7811bfe978e7e697bc169c6f3`. The official MX1/XML and MX2/JSON source snapshots are not date-identical; do not sum them into a current commercial denominator.

## Production-safe next gate

1. Acquire a dated official **full exact-MPN + same-row marketing-lifecycle** list for the MX1-covered families and **independently include MX2-only C5**. Explicitly retain package/temperature/TR variants, filter disclosures, raw data, pagination/row-integrity and vendor provenance.
2. Cross-check family/scope completeness against both pinned structural sources, the ST portfolio family list, and the five v0.2 commercial Active sentinels. The pattern source is only a *coverage cross-check*, not an identity or lifecycle authority.
3. Run the existing `preflight_st_selector_export.py` on applicable official selector exports, keeping `actual_active_st_coverage_percent=null` until whole-population, same-date and exact-identity coverage is proven.
4. Derive separate `Active_Official - Plasma_Production` and `Plasma_Production - Active_Official` exact sets. Missing lifecycle evidence remains `UNKNOWN`, not `Obsolete`. Qualification for backend, metadata, production publishing, hardware and security remain independent approval gates.

**Replay:** `python data/device-catalog/research/validate_st_multisource_structure.py`.

**Sources:**
- ST MX1 subset: https://github.com/STMicroelectronics/STM32_open_pin_data/tree/7d1f1514ed5583ec5007ad91236b4e1d377295b1/mcu
- ST MX2 C5 JSON DFP: https://github.com/STMicroelectronics/stm32c5xx-dfp/tree/a5f65bc64535cfa723e9d25f58d7ce23d0937aed/Descriptors/pinout
- ST official current software offer: https://github.com/STMicroelectronics/STM32Cube_MCU_Overall_Offer/blob/3ba0d378f9da6cb480d0293f0ce2fcb53c2f1a21/README.md
