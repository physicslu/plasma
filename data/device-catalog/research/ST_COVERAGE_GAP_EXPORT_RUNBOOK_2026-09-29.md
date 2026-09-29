# ST Coverage Gap v0.3 — Official Selector Export Preflight

Status: **Research-only input bridge, validated using synthetic test files; full official snapshot is NOT acquired.** Date: 2026-09-29.

## Decision from ST documentation

ST explicitly documents **MCU Selector → Export to Excel** in STM32CubeMX 6.18.1:
<https://dev.st.com/stm32cube-docs/stm32cubemx/6.18.1/en/docs/markup/CubeMX_UserManual/chapters/04_4_stm32cubemx_user_interface.html>

The ST-MCU-FINDER-PC release notes describe an **Export to Excel** button producing one list worksheet and one filter worksheet:
<https://www.st.com/resource/en/release_note/rn0111-stmcufinderpc-release-610-stmicroelectronics.pdf>

The ST portfolio's **more than 4,500 commercial part numbers** marketing statement is available at:
<https://www.st.com/en/microcontrollers-microprocessors.html>

**Critical non-equivalence:** the tools may export an MCU configuration name such as `STM32F103C8Tx` rather than the exact commercial ordering identities (e.g. `STM32F103C8T6`, `STM32F103C8T6TR`). The Excel export feature is confirmed; its exact-MPN/lifecycle field completeness is **NOT confirmed**. Never use raw exported row count or the 4,500+ marketing statement as a verified current Active exact-MPN denominator. Do not expand wildcard `x` into guessed package, temperature, security, packing or orderable suffixes.

## One-time export procedure

1. Install/update the official STM32CubeMX (or ST-MCU-FINDER-PC) using ST's official distribution and accept the applicable vendor terms.
2. In STM32CubeMX, select **Help → Refresh Data** first, then **New Project → MCU Selector**. Ensure device mode is MCU, not Board or MPU. Include wireless STM32 MCUs. Clear product-feature restrictions; capture actual tool version and applied filter settings.
3. Include all marketing statuses where the tool permits, **without silently filtering for Active**. Export the MCU selector list to its native **Excel**. In ST-MCU-FINDER-PC, preserve both worksheets, including the filters worksheet. Record the acquisition time in UTC.
4. Preserve the raw exported file unmodified (CSV may be used if exported by the official tool or faithfully converted with conversion provenance). Calculate SHA-256 over the exact file bytes. On Windows:
   `(Get-FileHash .\stm32-selector-export.xlsx -Algorithm SHA256).Hash.ToLowerInvariant()`
   On Linux/macOS: `sha256sum stm32-selector-export.xlsx`.
5. Copy `st-selector-export-provenance.example.json` to a **new** provenance file outside the tracked repo or retained as an independently versioned research artifact; fill source kind, installed version, exact export time, original file SHA-256 and **actual** filters. Keep `full_portfolio_completeness_reviewed=false`. A self-declared unfiltered selection does not establish completeness.
6. From the Plasma repository root, run:

   ```bash
   python data/device-catalog/research/preflight_st_selector_export.py \
     --export /path/to/stm32-selector-export.xlsx \
     --provenance /path/to/stm32-selector-provenance.json \
     --output /path/to/stm32-selector-preflight.json
   ```

   If multiple workbook worksheets contain valid part-number headers, specify `--sheet "MCU Selector"`. The parser is offline, reads CSV or XLSX with Python standard library, and verifies the source SHA-256 before analysis.

## What the preflight validates

- Replays v0.2's full frozen ST Production baseline: **2,683 unique exact ICPNs / 23 integrity-bound manufacturer sources**, their Git blob/SHA-256 hashes and row counts. An unrelated additional non-ST Production source does not invalidate the historical ST baseline.
- Parses only one explicit table/sheet; never confuses a separate Board Selector or Filters worksheet with MCU commercial records.
- Preserves commercial suffixes (including `TR`) as distinct exact identities; does not invent substitutions for wildcard `x` (or `X`).
- Separates same-part repeated rows, non-Active lifecycle, conflicting status, unavailable status, wildcard/pattern, unrelated part and empty identity. Unknown or conflicting lifecycle is never implicitly `Active`.
- Computes **only the observed Active subset intersection** with the frozen Plasma ST catalog and lists observed Active exact MPNs not admitted. Absence of a Production SKU from a partial vendor export is **not** evidence of NRND, obsolete status or a missing Production admission.
- For every run, emits `actual_active_st_coverage_percent=null` and `actual_active_st_gap_count=null` until the separate **complete official exact-MPN + same-row lifecycle evidence/reviewer gate** exists.
- Runs **no live browsing, Production writes, admission, runtime execution, FPGA/PS operation, destructive security flow or physical/HIL claim**.

### Interpretation of exported input

| Observed input | Preflight disposition | Can establish full Active denominator? |
| --- | --- | --- |
| Complete-looking MPN + explicit `Active` | Exact Active observed subset, against admitted identities | **No**, unless independent population completeness reviewed |
| Exact MPN + NRND/Obsolete/Proposal/Evaluation/Preview | Retain separate lifecycle classification | No |
| `STM32F103C8Tx`, `xx` or other wildcard | Research pattern / nonexact, never expand | No |
| Missing Marketing Status column | Unknown lifecycle, no Active identity admitted from import | No |
| Duplicate exact MPN with contradicting statuses | Explicit conflict, not Active | No |
| Export filtered by series, package, other filter | Partial source, filter disclosure required | No |
| Source missing complete timestamp/official provenance/digest | Fail closed | No |

## Next true-coverage gate

Obtain a **manufacturer-authoritative complete dated exact commercial-MPN export with same-row lifecycle** across all scoped STM32 MCU + Wireless MCU families, including formerly missing H5, C5, N6, WB0 and WL3. Validate its export metadata, full pagination/selection, license, lifecycle and row integrity independently. Crosscheck all 23 admitted source families and the five verified missing-family sentinels. Only then compute:

```text
ST_Active_Exact = {official exact MPN where lifecycle is Active}
Overlap         = ST_Active_Exact ∩ Plasma_ST_Production
Missing         = ST_Active_Exact - Plasma_ST_Production
Stale/unknown   = Plasma_ST_Production - ST_Active_Exact (must independently confirm lifecycle)
Actual Coverage = |Overlap| / |ST_Active_Exact|
```

The five sentinels from v0.2 remain a **proven minimum**, not a complete count. A backend or external-flash profile constraint (notably STM32N6) remains a separate later gate.
