# NXP — OpenOCD → Canonical Catalog Exact ICPN Coverage Gap v2

**Scope:** bounded, immutable-source **Path 1 / Gate 1** read-only reconciliation, not additional manufacturer discovery and not Level promotion. Repository base: `edf9f45f4ff4b58ba058bc5c29c496aa0bca1225` (2026-10-22). `main` can advance; all results are frozen to the source inventory at this baseline.

**Authority separation:** Historical NXP `P0/P1/P2` are *research investment priorities*, **not** ADR-0002 Catalog `L0/L1/L2/L3` levels. L1 needs official exact ICPN identity **and** source-backed, exact-applicable programming route. L2 needs reviewed `SUPPORTED` Programming Qualification for the pinned provider. L3 needs a versioned PLASMA configuration HIL PASS. No part is promoted by this report.

## 1. Evidence and immutable input scope

- Pinned OpenOCD upstream **0.12.0**, source commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`; `release/openocd.json` blob `08c884b1bf6f5999c6d34c090992a8b59d85971d`.
- 501 historical exact *research strings*, from `nxp-501-adr0002-core-transport-qualification-v10.csv` blob `9f0397fe6062356fd04cd5eb73133969e75d9bfb`. **277** are `RESEARCH_ONLY` according to v13 identity blob `4a0fbad8fa5f57580ba28e92f71b0793e12faf07`; these strings do not qualify as verified commercial ICPN in the current canonical domain.
- Previously reviewed [bounded reverse source v1](NXP_ADR0002_REVERSE_COVERAGE_V1.md), locked JSON blob `a8eeafc1f20abbc649030d38e345c695446d728d`: pinned target-directory **309** entries, filename-selected **48** NXP-relevant config/helper leads and two flash driver blobs, not exhaustive all-source capability. That review found **0 newly attested P0**, **not** zero globally supported NXP devices.
- Current **Canonical Production** `icpn-v1-manifest.json`: six NXP family source files, each verified with manifest Git blob and SHA-256. Source input is **241 Exact ICPNs**. Level counts are taken **only** from `ProgrammingQualificationRegistry` through `CatalogPromotionFramework`, not from research grades.
- Reproducible read-only script: `nxp_openocd_canonical_gap_v2.py`. It validates source blob pins, manufacturer/identity joins, exact counts, manifest hashes, current Catalog levels and disallows unsupported aggregate conclusions. Existing cross-manufacturer promotion CI tests its output and negative source-pin mutation.

## 2. Exact ICPN join: historical research vs current Catalog

| Cohort | Exact ICPNs | Interpretation |
| --- | ---: | --- |
| Historical source v10 | **501** | Bounded legacy discovery/research sample, not the NXP global catalog |
| Present both in historical v10 and current Canonical | **224** | All 224 were v13 `ADMITTED` |
| Present in current Canonical only | **17** | Newer officially reviewed LPC identities, not in that old 501 |
| Present in historical v10 only | **277** | All 277 were v13 `RESEARCH_ONLY`; not Production-admitted |
| Current Canonical total | **241** | 224 + 17; unique normalized Exact ICPN keys |

The 277 historical-only records split by **historical research priority**, which does **not** confer L1:

| Historical-only grade | Count | Next evidence gate |
| --- | ---: | --- |
| `P0` | **15** | LPC844 **7** + LPC845 **8**: actual target/flash-driver source clues exist, but exact commercial identity/original evidence admission was not granted by v13 |
| `P1` | **22** | K32L2 **4**, LPC802/LPC804 **18**: resolve official exact commercial identity and verify version-bound route applicability |
| `P2` | **240** | Archive or selectively reopen only on source-backed target/driver/official route evidence; not automatic unsupported |
| **Total** | **277** | No automatic Canonical admission |

Prior v1 research priority across all 501 was P0=27 / P1=38 / P2=436. Current Canonical L1=29 is **not** the successor of the old P0=27 count; the populations and gate definitions differ.

## 3. Current Canonical NXP levels and immediate blockers

| Family | Exact canonical | L0-only | L1-only | L2 | L3 | Evidence blocker |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| KL25 | 12 | 0 | 12 | 0 | 0 | Versioned `kl25.cfg` → `klx.cfg` → `kinetis.c` source-backed candidate; exact silicon/FCFG, operation-level qualifications and runtime/FCF safety unproven |
| LPC81X | 8 | 0 | 8 | 0 | 0 | Reviewed exact identity and source-backed `lpc8xx.cfg` candidate; not `SUPPORTED` |
| LPC11U6X | 8 | 0 | 8 | 0 | 0 | Reviewed exact identity and `lpc11xx.cfg` candidate; not `SUPPORTED` |
| LPC11U2X | 1 | 0 | 1 | 0 | 0 | Reviewed exact identity and `lpc11xx.cfg` candidate; not `SUPPORTED` |
| K32L2 | 16 | 16 | 0 | 0 | 0 | `kinetis.c` driver-only clue, **no admitted exact-applicable target/bank route** |
| MCX | 196 | 196 | 0 | 0 | 0 | Official exact identity proven, **no admitted pinned OpenOCD route**; cannot claim whole family unsupported |
| **Total** | **241** | **212** | **29** | **0** | **0** | 0 Job-selectable NXP ICPNs |

**Highest-value distinctions:**

1. **LPC844/LPC845 15**: not current L0; fix *identity admission* first. An old P0 label is insufficient.
2. **K32L2 16**: already canonical L0; source-backed `kinetis.c` evidence exists, but the missing target/Flash-bank applicability prevents L1. This is a **bounded L0→L1** follow-up, not an L2 request.
3. **MCX 196**: catalog is identity-only and has `no_mapping`; prioritize evidence-based Backend/Target feasibility triage **per family or actual Flash-controller architecture**. No blanket 196-part L1 promotion.
4. **KL25 12**: all already L1. Current `MKL25Z128VLK4` Host-only provenance and FCF source safety review do **not** authorize live SWD, Flash or L2; actual physical qualification is an independent workstream.
5. **17 newer LPC**: newly admitted L1, disjoint from the original 501 historical rows. Do not subtract them from the historical-only 277.

## 4. Limitations and suggested bounded next work

- Historic v1 sampled only root-level filenames by an NXP family filter. It did not prove an exhaustive global OpenOCD or vendor-fork capability inventory; **manufacturer-wide denominator unknown**.
- A source CONFIG or flash driver symbol is not automatically an operationally proven programming route. A family prefix match must not invent an Exact ICPN, silicon revision, flash geometry, or executable profile.
- Immediate engineering follow-up: **LPC84x 15 official Exact ICPN original-source/admission remediation**, **K32L2 16 target/driver/flash-bank source applicability review**, then **MCX partition by demonstrable vendor-neutral backend paths**. Output per-ICPN disposition with blocker and source pin. No promotion until independently reviewed and authorized.
- No catalog write, UI/Job change, runtime registration, OpenOCD execution, deployment, SWPC, Z2, DUT or physical Flash operation is authorized by this Gap Report.

### Reproduction

```bash
PYTHONPATH=software/python python data/device-catalog/research/nxp_openocd_canonical_gap_v2.py
PYTHONPATH=software/python python software/python/tests/test_catalog_promotion_framework.py
```

The existing GitHub-hosted `Catalog cross-manufacturer promotion framework` workflow executes the replay and source tamper negative test through the existing tests. All evidence remains host-only.
