# NXP ADR-0002 Phase 1 v26 — 31 MCX N exact-ICPN operating voltage domains

**Scope:** Phase 1 **01 IC Information** source evidence backfill (while ADR-0002's globally active implementation Phase is Phase 2). All changes confined to Research-owned manufacturer electrical data. This work does **not** qualify Flash Programming, installed OpenOCD runtime, PL/PPU, hardware power sequencing, Socket/Site/HIL, or user-selectable Production Catalog.

## Exact ordering identities and original Datasheet sources

| NXP original Datasheet | Revision | Exact ordering codes previously independently matched | Ordering Table | Normal operating supply evidence |
| --- | --- | ---: | --- | --- |
| [MCXN23x](https://www.nxp.com/docs/en/data-sheet/MCXN23x.pdf) | Rev 3, 21 Jan 2025 | **6** MCXN235/236 | Table 1, physical PDF p4 | §3.2.1 Table 9, physical PDF pp11–13 |
| [MCXNP184M150F70](https://www.nxp.com/docs/en/data-sheet/MCXNP184M150F70.pdf) | Rev 8.2, 11 Jun 2026 | **25** MCXN247/526/527/536/537/546/547/946/947 | Table 1, physical PDF pp5–6 | §3.2.1 Table 9, physical PDF pp15–16 |
| **Total** | | **31** existing admitted exact-ICPN observations | | |

The exact 31 commercial ordering strings, original doc IDs, Flash sizes and original NXP Table 1 page references match the already merged **v21 original 54-row crosswalk** and the unchanged v25 501-row baseline. There is **no newly admitted IC or inferred part-string family expansion**. No Active/EOL status is inferred from the electrical source.

### Electrical-domain interpretation (not a single global 3.3V rail)

The **normal operating** (not maximum rating) sections in both original NXP documents establish:

| Supply | Source evidence | Field mapping / constraints |
| --- | --- | --- |
| **VDD** (Port 0, Port 1, Flash, CMP) | Table 9: **1.71–3.6 V** | Primary `working_vdd` = 1.71 to 3.6 V, **VERIFIED**, but not VDD_SYS/core |
| **VDD_P2 / VDD_P3** | 1.71–3.6 V normal; optionally **1.14–1.32 V** only subject to special restrictions | `io_supply` includes low-voltage mode explicitly; 1.2V is **not** assumed universally available and requires VDD_CORE and sequencing checks |
| **VDD_P4** | **1.71–3.6 V** | Port-4 I/O rail; **not** silently equal VDD if independently sourced |
| **VDD_ANA** | Nominally equal VDD_P4, tolerance **±0.1 V**, stays in 1.71–3.6V bounds; VDD_P4 and VDD_ANA same nominal during POR | `vdda` **VERIFIED only for this relational constraint**. It is **not** an independently selectable generic 1.71–3.6V analog rail |
| **VDD_SYS** | Normal **1.71–1.98 V** | Stored in evidence note; fuse-programming **2.25–2.75V** is different mode and NOT the ordinary VDD parameter |
| **VDD_USB** | **3.0–3.6 V** | Separate source-side restriction, not used to populate generic `io_supply` or VDD |
| **VDD_CORE** | Internal/digital-domain operating mode dependent | Must not be populated with generic VDD or assumed externally programmable |

**Sequencing and package caveats:** Secondary I/O rails must either be tied to VDD or ramp after VDD_SYS; core supply must ramp after VDD; VDD_BAT must ramp before/with VDD_SYS; VDD_P4 and VDD_ANA must track at POR. The Rev 8.2 document further distinguishes **HLQFP100** (VDD_DCDC powered even when DCDC unused; DCDC_LX floating) from packages with dedicated VDD_DCDC (unused converter input to GND via a 10-kΩ resistor). These conditions are evidence notes, **not** PPU/Socket executable safety settings.

The **Absolute Maximum Ratings Table 8** is explicitly excluded as a normal-operation source. A generic device listing such as `Supply Voltage 1.7 to 3.6 V` does **not** replace Table 9's actual normal VDD minimum **1.71 V**.

### Quantified Phase-1 changes (224 existing admitted exact NXP ICPNs)

| Field | v25 VERIFIED / PARTIAL / UNKNOWN | v26 VERIFIED / PARTIAL / UNKNOWN |
| --- | --- | --- |
| Working VDD | 135 / 39 / 50 | **166 / 39 / 19** |
| GPIO I/O Supply | 119 / 16 / 89 | **150 / 16 / 58** |
| VDDA (NXP VDD_ANA relational) | 135 / 0 / 89 | **166 / 0 / 58** |
| RAM | 199 / 25 / 0 | **199 / 25 / 0** |

Across **all 501 research + admitted** source rows: Working VDD = 181 VERIFIED / 81 PARTIAL / 239 UNKNOWN; I/O Supply = 150 / 16 / 335; VDDA = 166 / 0 / 335. **Exactly 31 existing rows** receive new evidence values for only `working_vdd/unit/state`, `io_supply/state`, `vdda/state`; original RAM, Flash, Package, Pin Count, Temperature, identity, lifecycle, and all other v25 fields remain byte-exact.

### Evidence custody, replay and stop gates

Both **official NXP Datasheets were reviewed directly** for Table 1 exact ordering applicability and Table 9 electrical semantics; the original manufacturer PDF binaries are **not separately archived/SHA-256 verified** in this research chain. SHA-1 Git blob pins lock **our previously saved v21 exact-source table, v25 research ledger and new v26 transcription only**, NOT original manufacturer PDF bytes. Do not report source-PDF replay PASS or fake SHA.

Source-first artifacts:

- `nxp-31-mcxn-operating-rails-official-source-v26.csv`: exact 31 commercial ordering-code joins, original official document URLs/versions/table pages, per-rail values, source-scope and unsafe-inference caveats.
- `nxp-phase1-mcxn-operating-rails-lock-v26.json`: frozen v21+v25+v26 project-side Git blob identities and immutable v26 source contract.
- `nxp-501-phase1-mcxn-operating-rails-v26.csv`: exact 501-row full deterministic ledger, with per-device v26 provenance columns.
- `nxp-phase1-mcxn-operating-rails-coverage-v26.json`: separate admitted 224 vs source 501 denominator report.
- `nxp_phase1_mcxn_rails_v26.py` and `test_nxp_phase1_mcxn_rails_v26.py`: fail-closed source replay, exact 31 allowed modifications, rejection of invented source, wrong Flash, wrong supply source/table or fake hardware/software promotion.

```bash
python data/device-catalog/research/nxp_phase1_mcxn_rails_v26.py
python -m unittest discover -s data/device-catalog/research \
  -p 'test_nxp_phase1_mcxn_rails_v26.py' -v
```

**Remaining priority gaps:** 19 admitted Working VDD UNKNOWN (MCX E 15, MCX W 4), VDDA UNKNOWN 58 (K32L2B 12, MCX C 27, MCX E 15, MCX W 4), and GPIO I/O Supply UNKNOWN 58 (same cohort). Outstanding 25 RAM PARTIAL remain separate. No Product Catalog migration or claimed `openocd_software_support=SUPPORTED`.
