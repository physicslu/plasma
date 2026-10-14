# NXP ADR-0002 — Three approved implementation rules (Core / Driver / Metrics)

This v10 evidence-only extension to Draft PR #847 implements the three *newly approved*
requirements in `docs/adr/0002-openocd-software-qualified-catalog-visibility.md`.
No Production identity admission or user-facing public visibility change is implied.
No firmware, runtime, OpenOCD binary or hardware is executed.

## 1. Core-first classification

A separate reproducible **501-exact-ICPN** CSV contains `core_architecture`,
`core_model`, `debug_transport`, provider/version/commit, Target CFG,
Flash Driver C provenance, individual Flash source-operation stages,
exact device applicability, production identity and HIL evidence status.
Manufacturer **family-level** core evidence is labeled family-level, not exact
silicon proof. The four official NXP family sources are recorded in
`nxp-adr0002-core-source-v10.json`, and seven upstream OpenOCD Tcl/Driver
Git blobs in v9 are checked independently by CI. KL25 and K32L2 transport
is conservatively **UNKNOWN** rather than inferred from their Core.
LPC80x/LPC84x SWD derives from NXP family references and the pinned
`lpc1xxx.cfg`; the separate JTAG boundary-scan functionality is NOT a
JTAG Flash-programming transport qualification.

## 2. Driver-first qualification

OpenOCD upstream v0.12.0 source commit
`9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c` (from release manifest)
contains source-level `kinetis` and `lpc2000` probe/erase/write symbols.
The 501 ICPN records separately retain source-level operation symbols;
**all** have `operation_read_verify_qualification=UNKNOWN`,
`exact_icpn_applicability=UNVERIFIED`, unknown silicon revision and
`public_catalog_visibility_authorized=false`.
P0 source-linked Target/Driver pairing is a research priority only.
Same Cortex-M0+ does NOT imply same Flash Driver (KL25 vs LPC844).
P1 generic LPC8xx Target does not establish exact LPC802/804 IDs.
K32L2 family-level Kinetis driver clue does not establish Target CFG.

## 3. Core-aware metrics and denominators

`nxp-adr0002-core-aware-metrics-v10.json` separates:
- manufacturer exact research **501** (bounded, *not* all NXP SKUs);
  internal Production identity **224**, retained research queue **277**;
- **3** distinct upstream source-backed Target/Driver **research pairs**:
  KL25→kinetis, LPC84x→lpc2000, generic LPC80x→lpc2000.
  **These are not 3 software-qualified Device/Profile implementations.**
- P0 **27**, P1 **38**, P2 **436**; candidate **65** and unknown **436**.
- NXP family-referenced Cortex-M0+ **65**, Core UNKNOWN **436**;
  SWD-family-reference **33**, transport UNKNOWN **468**.
- Exact ICPNs newly SUPPORTED **0 in this v10 audit only**, not zero
  actual PLASMA support; present real Product Catalog visible count
  **UNKNOWN (null)** and HIL-tested configuration count **UNKNOWN (null)**.
- Cross-dimensional group counts by manufacturer × core_architecture /
  core_model × debug_transport × provider@version × flash_driver.

Do not claim ARM is the majority of OpenOCD-supported NXP ICs. These are
unqualified **research inventory** statistics with 436 unknown cores.

## CI and scope boundaries

Automated tests replay the v9 Git-blob-locked 501 identities, check the
approved ADR (source Git blob), recompute the entire v10 CSV and metrics,
pin the approved upstream commit and verify the original driver/target
source files. Tests reject support inference from Core/SWD/CFG, different
drivers for the same Core, unsupported exact silicon revisions,
UNKNOWN→ARM coercion, JTAG boundary scan→Flash-JTAG conflation and
Research priority→SUPPORTED promotion.

This is NXP ICPN *research* only. The cross-vendor public API/UI visibility
migration is tracked separately by Issue #849, and the independent
execution/runtime and physical HIL gates are unchanged. #847 remains Draft
and requires one explicit owner merge approval at the end.
