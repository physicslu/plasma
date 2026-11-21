# NXP L0 → L1 route-evidence audit — 2026-10-16

**Status: research audit / no Product promotion.** Base `main` = `4a61856bc041fde9a443a1c26830fd64385be6cb` (PR #960). ADR-0002 and `ProgrammingQualificationRegistry` are the sole Product authorities. This file is not a second promotion engine.

## Production scope (exclusive levels)

| Manufacturer | L0-only | L1-only | L2-only | L3-only | Exact |
| --- | ---: | ---: | ---: | ---: | ---: |
| NXP | 212 | 12 | 0 | 0 | 224 |

Known Production decomposition: KL25 12 mapped L1; MCX 196 and K32L2 16 L0. Thus the NXP L0 → L1 blocker is `NO_PROGRAMMING_ROUTE_EVIDENCE: 212`. L1 → L2 currently comprises 12 mapped routes not provider-qualified. These are the existing Production baseline, not a new qualification or a freshly executed generated report.

**Important denominator:** `nxp_adr0002_phase1_phase2_canonical_v1.py` also builds a distinct **297-exact research projection** (269 L0 / 28 research L1). The 73 additional source-observed material identities are NOT thereby admitted to the 224-row Production Catalog. Its 16 driver-only K32L2 `CANDIDATE` labels are historical research signals; canonical Production has no admitted route for K32L2. Do not combine the two populations.

## OpenOCD reverse-coverage disposition

Pinned upstream OpenOCD: v0.12.0 at `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`.

| Cohort | Exact material evidence | Pinned source chain | Current decision |
| --- | --- | --- | --- |
| KL25, Production 12 | Production IDENTIFIED | `kl25.cfg`, `kinetis` | Already L1; next edge is provider qualification L1→L2, NOT a new L0→L1 |
| K32L2, Production 16 | Production IDENTIFIED | `kinetis` driver-only historical hint, no verified applicable target CFG | **Remain L0**; require explicit target/algorithm applicability or an official programming path |
| MCX, Production 196 | Production IDENTIFIED | No normalized applicable canonical route in current Production | **Remain L0**; investigate official NXP programming/provider route by proved exact Base/Family |
| LPC11U67 / LPC11U68, material-observed research cohort (3 + 5) | Official exact-material/12NC ledger; not part of 224 Production rows | `lpc11xx.cfg → lpc1xxx.cfg → lpc2000.c`; pinned driver contains LPC11U67 and LPC11U68 silicon cases | **Highest-value bounded new route-evidence review**, conditional on independent canonical Production identity admission and traceable exact-material→Base→driver applicability |
| LPC811/812 and LPC11U24 research leads | Official exact-material research | `lpc8xx.cfg` or `lpc11xx.cfg` → `lpc1xxx.cfg` → `lpc2000.c`; silicon cases observed | Next candidate after LPC11U67/U68; no Product upgrade yet |
| LPC832/LPC834 research leads | Official material research | Generic `lpc8xx.cfg`, explicit pinned `lpc2000.c` Part ID absent | Blocked from simple CFG-based admission; seek different source-backed route |
| LPC1769FBD100 research lead | Product-level Active only | `lpc17xx.cfg → lpc1xxx.cfg → lpc2000.c` | Material-level identity/ordering evidence still incomplete |

Research sources: `NXP_OPENOCD_SOURCE_FIRST_WAVE4_V1.md`, `nxp-openocd-source-first-wave4-v1.json`, `nxp-11-lpc11u-lpc83x-phase1-official-material-v1.csv`, `NXP_ADR0002_REVERSE_COVERAGE_V1.md`. Their historical P0/P1 nomenclature must **never** enter active Product payloads.

### Bounded next transaction: LPC11U67/U68

1. Re-validate the eight exact manufacturer material numbers (3 LPC11U67 + 5 LPC11U68), their 12NCs, package/quality evidence and official Base crosswalk independently of CFG filenames. Explicit example: `LPC11U68JBD48E → LPC11U68JBD48`.
2. Independently replay pinned `lpc11xx.cfg` include closure and `lpc2000.c` LPC11U67/LPC11U68 silicon cases; record exact commit, blob identities, driver route and applicability limits. No substring/family-prefix heuristic may be accepted as proof.
3. Separate two promotion gates: **identity admission** into canonical Production (if and only if eligibility and source authority pass), then **L0→L1 route admission** through existing canonical registry/evidence adapter. Neither follows automatically from this research document.
4. Require the common `CatalogPromotionFramework` to observe any approved state change and reconcile counts, evidence classes, blocker counts, selector visibility and Job Picker flags. New L1 must be `job_selectable=false` and `execution_authorized=false`.
5. Add negative tests rejecting missing exact material evidence, ambiguous Base crosswalk, altered source SHA, generic CFG-only mappings, provider `SUPPORTED` without qualification, and any runtime permission inference.
6. Keep `LPC11U68JBD48E` L0/internal-only until both gates pass. No UI visibility override to satisfy an expected search result.

### Legacy boundary findings

- `NXP_ADR0002_ONLY_LEGACY_RETIREMENT_V1.md` records retirement of ten historical priority-gating workflows. Historical v9/v10/wave inputs remain intentionally retained for forensic replay.
- The read-only `nxp_adr0002_phase1_phase2_canonical_v1.py` still contains a **separate 297-row research-level projection** and labels K32L2 driver-only cases as candidate. Treat it as research, **not** an alternative Product authority.
- Current `catalog_promotion_framework.py` is an observer; `ProgrammingQualificationRegistry` derives Product level from canonical mapped/backend/provider evidence. A Product promotion from this audit requires code and regression tests, not merely updated research counts.
- No NXP-specific Product enum/API, visibility rule, runtime gate or blocker code is authorized. Applicable L0 blocker is solely `NO_PROGRAMMING_ROUTE_EVIDENCE`.

**Execution/HIL:** no authorization, no new `SUPPORTED`, no L2/L3, no merge. This audit does not claim local replay of source downloads, Python tests, or generated framework report.
