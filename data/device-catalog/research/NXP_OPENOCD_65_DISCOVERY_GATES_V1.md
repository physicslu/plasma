# NXP ADR-0002 — 65 Source-first Discovery Candidate Acceptance Gates

## Scope and authority

Continue the already implemented OpenOCD-first reverse-coverage work. **Do not replace the scanner, expand into NXP P2 parts, modify historical 501 priorities, or interpret a CFG or Flash-driver match as software-qualified \`SUPPORTED\`.** This PR creates a **research-only** readout from the three existing NXP discovery waves.

Pinned source: upstream OpenOCD **v0.12.0** commit \`9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c\`.

| Denominator / cohort | P0 | P1 | P2 | Total | Authority |
|---|---:|---:|---:|---:|---|
| Historical source-locked exact 501 | 27 | 38 | 436 | 501 | Existing v10 research classification, unchanged |
| Discovery Wave 2 | 27 | 0 | — | 27 | New outside-501 raw source observations |
| Discovery Wave 3 | 15 | 3 | — | 18 | New outside-501 raw source observations |
| Discovery Wave 4 | 18 | 2 | — | 20 | New outside-501 raw source observations |
| **Combined research leads, not admitted** | **87** | **43** | 436 archived | **566 observations** | Mixed **501 previously screened exact** + **65 provisional**; not a single approved exact-ICPN inventory |

**Critical:** 566 is a count of disjoint historical identities / newly observed **strings**, NOT 566 verified exact orderable ICPNs, not a globally exhaustive NXP Active count, and not an OpenOCD software-qualified count. P0/P1 in this table are **research priority leads**. New software \`SUPPORTED\` in this research PR: **0**. Newly admitted Production ICPNs: **0**.

## New reviewable machine-readable queue

- \`nxp-65-openocd-discovery-gates-v1.csv\`: 65 observed source strings and Wave, P0/P1 lead, NXP official source URI, original evidence-scope, pinned Target/Flash source, material/ordering caveats, and explicit per-row next verification gate.
- \`nxp_65_discovery_gates_v1.py\`: regenerates the CSV from **source SHA1/Git-blob-locked** Wave2/3/4 JSON and original 501 v10 CSV, checks 27/18/20, 60/5, disjointness, and all no-promotion boundaries.
- \`test_nxp_65_discovery_gates_v1.py\`: asserts mixed material lifecycle, JTAG-only research routes, weak product-level Active, and rejects fake support or original source changes.
- Dedicated CI validates exact deterministic replay. SHA1 here denotes *Git blob object hashes of PLASMA project-side records*, not SHA256-qualified original NXP web pages.

## Phase 1 entry gates (for each of the 65)

1. Confirm exact manufacturer **orderable** code, not merely the product heading, Package/Quality display string, silicon family or packing suffix. The raw display observations are **not** automatically valid Production identities.
2. Capture and source-lock original official manufacturer evidence bytes, independently crosswalk the ordering table and *material-level* lifecycle. All three waves currently state **no original NXP HTML binary custody**.
3. Retain pinned OpenOCD Target CFG → helper/include → Flash Driver, silicon-ID probe cases, relevant core, and **SWD/JTAG** transport distinction. No automatic P0-to-\`SUPPORTED\` transition is authorized.
4. Add exact IC Information fields to Phase 1 independently only after source scope is qualified. Flash erase/program/verify and software \`SUPPORTED\` decisions remain separate Phase 2 evidence.
5. Keep Socket, voltage fixture, PPU firmware/PL and HIL execution gates independent from software/catalog research.

### Explicit negative and scope cases

| Observed part(s) | Retained issue | Required follow-up |
|---|---|---|
| \`LPC1114FBD48/333J\` and \`LPC11U24FHI33/301Y\` | Slash-containing official display strings | Establish the official orderable code rather than normalizing by guess |
| \`LPC1769FBD100\` | Official product-level Active only | Find exact material-level Active source |
| \`LPC2148FBD64\` | Material \`,118\` NLM; \`,151\`/\`,157\` Active; ARM7 JTAG | Separate material lifecycles, exact ordering and transport |
| \`LPC2378FBD144\`, \`LPC2378FBD144K\` | NRND, ARM7 JTAG route | Do not infer applicability to the FPGA SWD site |
| \`LPC1549JBD100E\`, \`LPC1549JBD100K\` | P1: driver variant without pinned dedicated Target Config | Retain P1 until a credible complete source route is found |
| \`LPC832M101FDH20FP\`, \`LPC834M101FHI33Y\` | P1: generic Target, explicit Part ID not found in pinned driver | Retain P1 unless version-locked identity evidence resolves gap |

## Reproduction and stop rules

\`\`\`bash
python data/device-catalog/research/nxp_65_discovery_gates_v1.py
python -m unittest discover -s data/device-catalog/research \
  -p 'test_nxp_65_discovery_gates_v1.py' -v
\`\`\`

If any pinned project record changes, validation fails until separately reviewed. Never silently modify the historical 501, automatically promote source observations, publish all 65 to IC Selector/Production, or equate P0 with PLASMA PPU/Site programming capability. PR remains **Draft; merge requires separate owner approval**.

Related: [Issue #851](https://github.com/physicslu/plasma/issues/851), [ADR-0002 proposed vendor-agnostic research contract PR #895](https://github.com/physicslu/plasma/pull/895), [NXP Wave2 PR #887](https://github.com/physicslu/plasma/pull/887), [Wave3 PR #888](https://github.com/physicslu/plasma/pull/888), [Wave4 PR #891](https://github.com/physicslu/plasma/pull/891).
