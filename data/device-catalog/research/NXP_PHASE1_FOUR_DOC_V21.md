# NXP ADR-0002 Phase 1 v21 — 53 exact manufacturer RAM evidence rows

**Only 01 IC Information**, with no Programming or PLASMA Compatibility execution.

## Four original manufacturer ordering tables

Four official documents provide **54 exact manufacturer Part Number / Flash / SRAM observations**. Of these, **53** match existing admitted NXP identities and independently match their previous Flash capacity. One additional code, **MCXA255VLL**, is already present as Research-only; it is NOT newly admitted or assigned a verified field.

| Source | Official revision | Page | Exact source rows | Admitted matched |
|---|---|---:|---:|---:|
| [MCX A2 Family Factsheet](https://www.nxp.com/docs/en/fact-sheet/MCX-A2-FAMILY-MICROCONTROLLERS.pdf) | MCXA2FS Rev 0, March 2026 | PDF physical 2 | 16 | 15 |
| [MCX E31 Factsheet](https://www.nxp.com/docs/en/fact-sheet/MCXE31FS.pdf) | MCXE31FS Rev 1, October 2025 | PDF physical 2 | 7 | 7 |
| [MCX N23x Datasheet](https://www.nxp.com/docs/en/data-sheet/MCXN23x.pdf) | Rev 3, 21 January 2025 | PDF physical 4 | 6 | 6 |
| [MCX N2/N5/N9 Datasheet](https://www.nxp.com/docs/en/data-sheet/MCXNP184M150F70.pdf) | Rev 8.2, 11 June 2026 | PDF physical 5–6 | 25 | 25 |

## Crucial field distinction

For MCX N23/N2/N5/N9, SRAM **depends on exact ordering code**:
512 KB nominal yields 416 KB under ECC; 352 KB nominal yields
288 KB under ECC; 192 KB nominal yields 160 KB under ECC.
Phase 1 retains original **nominal SRAM** in the primary RAM field,
with a separate optional `sram_ecc_usable_capacity_kb_v21` value.
It is **incorrect** to put the ECC usable capacity into a generic
manufacturer `RAM` field without identifying the configuration.

K32L2B **12 existing admitted exact ordering codes** are the only
remaining unknown RAM group after this pass. Official
[NXP K32-L2 product documentation](https://www.nxp.com/products/K32-L2)
lists exact part applicability for K32L2B3x Rev 3, but its primary
datasheet content was not accessible in this session. We do **not**
infer SRAM 32/64/128 KB from Flash or family-level limits. Their
states remain UNKNOWN and are tracked as evidence blocked.

## Coverage of existing 224 admitted NXP ordering codes

| RAM state | v20 | v21 |
|---|---:|---:|
| VERIFIED | 146 | **199** |
| PARTIAL | 13 | **13** |
| UNKNOWN | 65 | **12** |

Across the full bounded 501 original order strings:
RAM 214 VERIFIED / 61 PARTIAL / 226 UNKNOWN.

## Source and safety contract

The original manufacturer's PDF files were read from official sources
but **not archived as original binary objects**, so source SHA256
does not claim original document authenticity. The 54-row exact
transcription and its 501-row deterministic derivative are separately
Git SHA-locked with field-level source reference, revision, physical
page, original Flash cross-check and source-limited trust state.

No `working_vdd`, `vdda`, `io_supply`, Package, Pin Count or
Production Identity fields are changed. Neither Phase 2 Flash
programming nor Phase 3 Socket/PPU/HIL is initiated. No Console
runtime/UI change, no Software SUPPORTED promotion.

Run source replay:
`python data/device-catalog/research/nxp_phase1_four_doc_v21.py`
and
`python -m unittest discover -s data/device-catalog/research -p 'test_nxp_phase1_four_doc_v21.py' -v`.
