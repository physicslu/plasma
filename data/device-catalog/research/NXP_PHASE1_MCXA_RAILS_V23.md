# NXP ADR-0002 Phase 1 v23 — 119 source-scoped MCX A operating rail records

**Only 01 IC Information.** No Programming, Console API/UI, Production
ICPN Admission, physical power sequencing tests, PPU/Socket or HIL.

## Why one generic Voltage field is insufficient

NXP official **Voltage and current operating requirement** tables
establish MCX A normal **VDD 1.71–3.6 V** (I/O, Flash, LDO).
Their **VDD_ANA** analog/ADC voltage is a *relative, bounded rail
constraint*: `VDD − 0.1 V ≤ VDD_ANA ≤ VDD + 0.1 V`, and the
**power-on reset sequencing section says VDD_ANA and VDD must use the
same voltage**. Do not turn that into a fabricated independent
VDDA/VDDIO min/max voltage; the primary `vdda` column explicitly names
NXP's `VDD_ANA` and preserves relative and POR constraints.

Exception on `MCXA144/145/146/154/155/156`: NXP
`MCXAP100M096F60` **Table 9**, physical page 13, shows
**VDD_P3** can use either *normal 1.71–3.6 V* or
*1.2 V mode 1.14–1.32 V*. The 26 exact admitted ICPNs in that
datasheet have this alternate rail recorded independently; it must
not be replaced with universal VDD. USB analog supply **VDD_USB
3.0–3.6 V** (if present) is also independent, not universal GPIO power.

For the other five source datasheets, their voltage table describes
GPIO supplies through shared `VDD`. The `io_supply` field is an
annotated rail description, **not a Socket/site power-readiness
boolean**. All 119 observed exact order codes remain
unqualified for fixture voltages, voltage-ramp control, and HIL.

## Official manufacturer documents

| Datasheet | Revision | Exact admitted ICPNs | Source |
|---|---|---:|---|
| `MCXAP064M096F30` | Rev 5.2 26 May 2026 | 22 | [A132/133/142/143/152/153](https://www.nxp.com/docs/en/data-sheet/MCXAP064M096F30.pdf), Table 9 physical page 12 |
| `MCXAP100M096F60` | Rev 10 26 May 2026 | 26 | [A144/145/146/154/155/156](https://www.nxp.com/docs/en/data-sheet/MCXAP100M96FS6.pdf), Table 9 physical page 13 |
| `MCXAP100M180F41` | Rev 3.0 6 Jul 2026 | 8 | [A173/174](https://www.nxp.com/docs/en/data-sheet/MCXAP100M180F41.pdf), Table 11 physical page 12 |
| `MCXAP144M240F61` | Rev 5 6 Jul 2026 | 31 | [A175/176/185/186/255/256/265/266](https://www.nxp.com/docs/en/data-sheet/MCXAP144M240F61.pdf), Table 11 physical page 15 |
| `MCXAP100M180F40` | Rev 4.0 6 Jul 2026 | 8 | [A343/344](https://www.nxp.com/docs/en/data-sheet/MCXAP100M180F40.pdf), Table 11 physical page 12 |
| `MCXAP144M240F60` | Rev 6 6 Jul 2026 | 24 | [A345/346/355/356/365/366](https://www.nxp.com/docs/en/data-sheet/MCXAP144M240F60.pdf), Table 11 physical page 15 |

**Exact manufacturer identity join**: source `nxp-119-mcxa-operating-rails-source-v23.csv`
pins the exact ICPN, source-model datasheet, revision, full official
URL, exact earlier NXP MCU options-table source, original Flash
cross-check, working rail values and mode-specific exceptions. An
exact SKU must be in the official original source and among the
previously admitted 224. No original manufacturer PDF binaries are
permanently archived or binary-SHA256-locked; Git-blobs lock our
transcribed observations **only**.

## Coverage of 224 admitted NXP ICPNs, v22 → v23

| Field | Before VERIFIED / PARTIAL / UNKNOWN | After VERIFIED / PARTIAL / UNKNOWN |
|---|---|---|
| Working VDD | 16 / 27 / 181 | **135 / 27 / 62** |
| VDDA (NXP VDD_ANA) | 16 / 0 / 208 | **135 / 0 / 89** |
| GPIO I/O Supply domain | 0 / 0 / 224 | **119 / 0 / 105** |

The original 501 source identities (224 admitted, 277 Research-only)
and RAM coverage remain unchanged. The remaining unknown source
cohorts include K32L2B, MCX C/E/N/W and require separate
voltage-domain review. A general family operating voltage is not
a Programming Profile or safe hardware supply decision.
