# NXP ADR-0002 Phase 1 v27 — 15 MCX E Exact ICPNs, Supply Domains and SRAM Source Conflict

## Research scope and source authority

**01 IC Information** evidence backfill only; the global ADR-0002 **Phase 2 Programming remains current**. This work is **not** OpenOCD flash qualification, fixture voltage control, PL/PPU HIL, Socket/Site engineering, public Selector release or Production identity admission. Preserve all 501 prior records: **224 previously admitted exact manufacturer identities / 277 research-only**.

| Original NXP Primary Datasheet | Revision | Exact existing ICPNs | Exact ordering info | Normal operating rails |
|---|---|---:|---|---|
| [MCXE245/246/247 MCXEP144M112F70](https://www.nxp.com/docs/en/data-sheet/MCXEP144M112F70.pdf) | Rev 2, 14 Jul 2025 | **8** | §3.2 Ordering Information, physical PDF pp8–9/75 | §4.2 **Table 3**, physical PDF p11/75 |
| [MCXE315/316/317/31B MCXEP172M160FB0](https://www.nxp.com/docs/en/data-sheet/MCXEP172M160FB0.pdf) | Rev 4, 6 Apr 2026 | **7** | **Table 2**, physical PDF p6/81 | §5.2 **Table 4**, physical PDF p8/81 |
| Total | | **15** | No new or proposed exact commercial ICPNs | No Phase 2/HIL operation tests |

All 15 exact order codes, earlier Flash fields and manufacturer product URLs are joined to official ordering tables. The seven E31 exact codes are independently cross-checked against the prior archived **[MCX E31 Fact Sheet Rev 1](https://www.nxp.com/docs/en/fact-sheet/MCXE31FS.pdf)** project-side v21 transcription.

## Technical voltage observations and mandatory conditions

**MCX E24 8 ICPNs**:
- `working_vdd=2.7 to 5.5 V` **VERIFIED** from Table 3's normal VDD, not its Table 2 absolute maximum.
- For **MCXE247**, **2.7 V is valid when using internal FIRC**; with PLL engaged **at least 2.97 V** is guaranteed. MCXE245/246 operate from 2.7 V in all modes. Do not equate a family-wide 2.7 V minimum to *all 247 configurations*.
- `vdda` **VERIFIED**: **VDDA 2.7–5.5 V**; NXP requires **VDD and VDDA share the same source on PCB**. The ±0.1 V differential is **for RF-AC only**, not a separately-programmable DC supply range.
- GPIO open-drain pull-up voltage is VDD. **No independent GPIO VDDIO rail** is evidenced, therefore `io_supply` stores the VDD-domain note at **PARTIAL** rather than fabricated VDDIO VERIFIED.

**MCX E31 7 ICPNs**:
- `working_vdd=2.97 to 5.5 V` **VERIFIED** for **VDD_HV_A**, the external main I/O + analog supply.
- `io_supply` **VERIFIED** for described power domains: **VDD_HV_A** and **VDD_HV_B** where that separate pin exists (the MCXE31B package); each exact power pin still needs independent hardware mapping.
- `vdda` **VERIFIED as main analog rail semantics**: analog circuits use **VDD_HV_A**, **not** a separately proved `VDDA` pin. **VREFH** is an ADC reference, not the external analog power input. `V25` internal Flash/clock 2.5 V and `V11` internal core ~1.14 V are **not** the external VDD operating range.

No device has been confirmed as safe to program directly with 5.5 V debug signals or drive programmable fixture rails. **Vendor normal operating rails are not socket/SWD/programming pin electrical guarantees**.

## Explicit contrary manufacturer RAM evidence discovered — 2 ICPNs

A separate cross-document conflict must not remain silently `VERIFIED`:

| Exact ICPN | Older official NXP source (Rev 1, Oct 2025) | Current original NXP Datasheet (Rev 4, Apr 2026) | v27 response |
|---|---|---|---|
| `MCXE315MLF` | `MCXE31FS` exact-row SRAM **64 KB** | `MCXEP172M160FB0` Table 2 exact row **112 KB** | retain old numerical `ram=64`, change `ram_state` **VERIFIED → CONFLICT** |
| `MCXE315MPA` | Same 64 KB | Same 112 KB | retain 64, mark **CONFLICT** |

Until NXP provides memory-region/revision clarification, **neither 64 KB nor 112 KB is declared resolved in the canonical field**. Both original documents are cited and the new number is stored only in a v27 source-discrepancy column. This conflict is not evidence that an IC is unprogrammable or that its exact identity is invalid. No other RAM values are changed.

## Metrics: exactly 224 previously admitted exact NXP ICPNs

| Field | v26 VERIFIED / PARTIAL / UNKNOWN / CONFLICT | v27 VERIFIED / PARTIAL / UNKNOWN / CONFLICT |
|---|---|---|
| Working VDD | 166 / 39 / 19 / 0 | **181 / 39 / 4 / 0** |
| GPIO I/O Supply | 150 / 16 / 58 / 0 | **157 / 24 / 43 / 0** |
| VDDA / analog supply semantics | 166 / 0 / 58 / 0 | **181 / 0 / 43 / 0** |
| RAM | 199 / 25 / 0 / 0 | **197 / 25 / 0 / 2** |

**No new admitted manufacturer identity**. All **501** rows are preserved and independently replayable from v26 source-ledger plus 15 exact-source observations. All original fields are unchanged except seven explicit supply fields for precisely 15 rows and `ram_state` for the two flagged 315 codes; new v27 research provenance fields are blank for all others.

**Original PDF evidence custody caveat:** Original NXP Datasheet and Fact Sheet documents were reviewed as online primary sources. Their original binary bytes have **not** been archived/hashed; Git blob SHA locks bind only **PLASMA's prior v26/v21 internal sources and this new v27 transcription**. A future PDF byte-level archive or official datasheet revision may reopen the discrepancies, but must not fabricate current original-PDF SHA256.

## Research artifacts and validation

- `nxp-15-mcxe-normal-voltage-exact-source-v27.csv`: 15 reviewed order-code + normal-rail observations and per-device mode, supply, and RAM discrepancy provenance.
- `nxp-phase1-mcxe-operating-source-lock-v27.json`: fixed official document identities/pages/revisions, Git source blob and no-qualification gates.
- `nxp-501-phase1-mcxe-normal-voltage-v27.csv`: strict append-only provenance on 501 exact records; no Production changes.
- `nxp-phase1-mcxe-normal-voltage-coverage-v27.json`: admitted 224 versus total 501 field states.
- `nxp_phase1_mcxe_rails_v27.py`, `test_nxp_phase1_mcxe_rails_v27.py`: deterministic offline replay and negative tests for wrong supply/mode, fake independent VDDIO/VDDA, material drift, false original PDF SHA, RAM contradiction loss and unauthorized software/Production/HIL authority.

```bash
python data/device-catalog/research/nxp_phase1_mcxe_rails_v27.py
python -m unittest discover -s data/device-catalog/research \
  -p 'test_nxp_phase1_mcxe_rails_v27.py' -v
```

**Next admitted Phase 1 gaps after this source-scoped change:** MCX W has **4 UNKNOWN Working VDD**; VDDA and GPIO independent-domain visibility still have **43 UNKNOWN** each (K32L2B 12, MCX C 27, MCX W 4); **25 RAM PARTIAL and 2 MCXE315 RAM CONFLICT** remain unresolved. No automatic promotion of `SUPPORTED`, runtime capability or physical HIL.
