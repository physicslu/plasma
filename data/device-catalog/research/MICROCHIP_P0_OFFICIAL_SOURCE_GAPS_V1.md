# Microchip P0 Phase 1 — Official-source gaps and targeted acquisition v1

**Status: Research-only.** This is a source-observation and acquisition plan, not Phase 1 completion or a Production Catalog admission. User-approved scope remains exact **ICPN → manufacturer Base Device → OpenOCD Target CFG**, plus Phase 1 IC Information metadata; Flash Driver and programming verification are excluded.

## Actual original-source reverse checks

Independent original byte replay from the archived Microchip MCP, DFP index and MicrochipDirect 32-bit Chart produced:

| Result | Exact ICPN count |
| --- | ---: |
| P0 Microchip ICPN research cohort | **2,437** |
| Exact manufacturer MCP Base Device ↔ official Chart Base Device | **2,370** |
| Added Chart joins via the single reviewed manufacturer MCP/DFP alias | **0** |
| Unmatched official 32-bit Chart Base names | **67** |
| Distinct manufacturer MCP Base Devices in those 67 unresolved ICPNs | **27** |

**The reviewed `ATSAMD21G18` ↔ `ATSAMD21G18A` DFP alias does not solve the 67-row gap.** We now explicitly test that it cannot be used to fabricate an unsupported second family alias or silently extend exact-variant status. Any approved alias-derived chart parameter remains `PARTIAL`, with both the original manufacturer MCP response digest and chart original-byte digest attached.

The original Research ledger contains a machine-readable **27-row official evidence acquisition queue**: each entry lists its manufacturer MCP Base Device, exact ICPNs, corresponding CFG research group, and official-source work still missing. The queue doesn't manufacture URL patterns or silently parse suffixes.

### All 27 manufacturer Base Devices requiring additional official source

| OpenOCD Research CFG | Manufacturer Base Device : unresolved exact ICPNs |
| --- | --- |
| `at91samdXX.cfg` | ATSAMD21E15B: 1; ATSAMD21G17D: 4; ATSAMD21J17D: 1; ATSAMDA1G14A: 1; ATSAMDA1G15A: 1; ATSAMDA1G16A: 2; ATSAMDA1J15A: 1; ATSAMDA1J16A: 1 |
| `at91samdXX.cfg` | ATSAMR21E16A: 4; ATSAMR21E17A: 4; ATSAMR21E18A: 4; ATSAMR21E19A: 1; ATSAMR21G16A: 4; ATSAMR21G17A: 4; ATSAMR21G18A: 5 |
| `at91samdXX.cfg` | ATSAMR30E18A: 2; ATSAMR30G18A: 2 |
| `atsamv.cfg` | ATSAME70Q19B: 2; ATSAMS70N19B: 2; ATSAMS70Q19B: 3; ATSAMV70Q19B: 1; ATSAMV71N19B: 2; ATSAMV71N21B: 4 |
| `pic32mx.cfg` | PIC32MX130F064C: 4; PIC32MX150F128C: 2; PIC32MX230F064C: 1; PIC32MX250F128C: 4 |
| **Total** | **27 original Base identities, 67 distinct exact research ICPNs** |

This groups source-acquisition work into a few Microchip documentary families rather than 67 unrelated manufacturer searches, without claiming any unqueried source exists.

## Bounded exact-ordering evidence canary: SAM R30

Microchip official online documentation offers a potentially more precise source than the 32-bit parametric chart:

- [Microchip SAM R30E Section 3.1 original online ordering table](https://onlinedocs.microchip.com/oxy/GUID-4B3D771E-5647-4191-AD45-C897B0D23071-en-US-3/GUID-051A9F8A-61B6-46C4-B797-9AEEA6BDCC57.html)
- [Microchip SAM R30G Section 3.2 original online ordering table](https://onlinedocs.microchip.com/oxy/GUID-4B3D771E-5647-4191-AD45-C897B0D23071-en-US-3/GUID-FA1F01D6-601F-4646-B4E1-644BC34093EE.html)
- **PDF crosscheck target:** official *SAM R30 Data Sheet DS70005303B*, ordering information Tables 3-1 / 3-2, https://ww1.microchip.com/downloads/en/DeviceDoc/70005303B.pdf

The online tables explicitly describe four candidate order codes `ATSAMR30E18A-MU`, `ATSAMR30E18A-MUT`, `ATSAMR30G18A-MU`, `ATSAMR30G18A-MUT`, and exact ordering-row Flash/SRAM/Package values. **Do not assume these four strings are exactly the four ICPNs from the historical source replay until the commercial identity sets are compared.**

`microchip_phase1_p0_samr30_online_original_v1.py` now attempts **bounded source capture** from the exact two manufacturer URLs, validates the original HTML table structure and four separate code rows, records HTML bytes and SHA-256, and replays those saved original bytes offline. It explicitly denies field `VERIFIED` promotion until independent manufacturer **PDF** consistency is demonstrated. If either official web page is blocked/unavailable or altered, the source receipt remains `SOURCE_NOT_AVAILABLE`, and any success claim fails.

### How to evaluate a captured source

1. Review the **live canary step outcome and artifact manifest**, not just the overall green CI workflow. This live step has `continue-on-error`; offline unit test success does not prove online access.
2. If both official HTML source bytes were actually captured, cross-reference exact `icpn` strings against the independent Microchip MCP-derived 67-item gap queue. Never infer manufacturer Base Device or package/temperature solely from a suffix.
3. Independently retrieve the **official PDF original** and verify its source SHA, revision, page Table 3-1/3-2 ordering values and exact-applicability conditions before creating any commercial `VERIFIED` field promotion; retain any disagreement as `CONFLICT`.
4. Only then propose a separate phase-one evidence promotion PR, preserving source URL, original file/bytes, SHA-256, page/table/row locator, original units and exact ICPN key. No internal Production admission or UI publication happens automatically.

The workflow captures no live vendor sources from an unreviewed domain, never creates artificial data for blocked pages, and archives only Research source receipts in a temporary **90-day GitHub Artifact**. No durable/offsite storage claim or Phase 2/3 support has been made.
