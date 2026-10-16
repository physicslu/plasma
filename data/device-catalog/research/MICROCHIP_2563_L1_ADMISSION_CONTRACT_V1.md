# Microchip 2,563 exact-ICPN L1 admission — bounded contract v1

Status: **proposed; no promotion authorized by this document**. Baseline: ADR-0002 and main commit `4a61856bc041fde9a443a1c26830fd64385be6cb`.

## Input population (Research, NOT Production)

Source: `MICROCHIP_OPENOCD_REVERSE_COVERAGE_V1.md`; source replay workflow run 38664576255; original-byte replay Artifact 11940412265. OpenOCD 0.12.0 source commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`.

| Target CFG | Research exact commercial ICPN candidate mappings | Review cohort |
| --- | ---: | --- |
| `pic32mx.cfg` | 1241 | Source-backed target/route applicability review |
| `at91samdXX.cfg` | 667 | Source-backed target/route applicability review |
| `atsame5x.cfg` | 354 | Source-backed target/route applicability review |
| `atsamv.cfg` | 175 | Source-backed target/route applicability review |
| `atsaml1x.cfg` | 126 | Target-only; verify that a **programming** path (not merely debug access) is supported by sources |
| **Total** | **2563** | **Admission queue, not L1 count** |

The old P0/P1 labels in locked Research inputs do not denote ADR-0002 Catalog Levels.

## Per-ICPN independent gate contract

Identity gate: manufacturer-authoritative **exact commercial ICPN** with original source locator/digest, unambiguous base-device relation, canonical key `(manufacturer, exact_icpn)`; no synthesis from DFP names, CFG strings, suffix rules or aggregate totals. An ICPN can be L0 without completed unrelated IC information fields. Historical research candidates not yet admitted remain outside Production projections.

Programming-route gate: independently source-backed provider/target/driver/algorithm/ROM-IAP/official programming path, source commit/version and immutable source locators/digests, and auditable applicability to the exact ICPN or its **proven** base device/family. CFG name alone or debug-only target does not automatically qualify. L1 does **not** require software flash operation qualification, erase/program/verify passes or hardware HIL.

Outputs **only through canonical** `ProgrammingQualificationRegistry` and `CatalogPromotionFramework`: identity-only remains L0 with `NO_PROGRAMMING_ROUTE_EVIDENCE`; admitted backend candidate route yields L1, evidence class `BACKEND_CANDIDATE_ROUTE`, blocker `BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED` unless a more specific existing canonical route/provider state applies. No Microchip-specific Level enum, Product API, visibility gate or blocker.

## Required implementation and replay acceptance

1. Independently retrieve and replay all 13 original source roots (one 16-batch archive plus 12 disjoint shards) and the DFP archive; verify source bytes, frozen manifests and per-ICPN linkage. Report unavailable originals as **unverified**, not as zero matches.
2. Produce one stable admission ledger per unique exact ICPN with original MCP source ID and SHA256, official base-device relation, DFP name and source ID, OpenOCD provider/version/CFG blob and resolved route evidence, applicability disposition and reason, identity disposition, and resulting canonical projection. Retain 2,563 input rows and a reconciliation by CFG, including duplicates/conflicts/quarantines.
3. Validate the two gates separately. Never infer manufacturer identity from OpenOCD. Never assume the 2,563 pass by count alone. Keep failed/unresolved rows research-only or canonical L0 as warranted by identity evidence.
4. Feed admitted evidence via a vendor-neutral route interface; preserve read-only ST H5/C5 candidate behavior and historical immutable Microchip 122 SAML1X admission until explicitly migrated.
5. Add automated tests for source tampering/missing inputs, ambiguous/repeated ICPN, base mismatch, CFG/driver applicability failure, target-only debug-only case, no unsupported legacy phase fields, and L3⊆L2⊆L1⊆L0.
6. Verify for each newly admitted L1: selector visible true, job selectable false, software qualification not SUPPORTED unless separately reviewed, execution authorization false. Verify existing 122 SAML1X remain unchanged until separate valid route admission.
7. Report final **actual** L0-only/L1-only/L2-only/L3-only counts and route blockers by Manufacturer from canonical framework, not the 2,563 Research denominator.

## Explicit non-goals

No blanket promotion of 2,563 Research mappings. No L2 SUPPORTED, L3 verified, program/erase/verify claims, installable runtime binding, flash algorithm changes, PPU/FPGA/HIL, Job/Batch entitlement, Microchip-specific public API, or main merge without owner approval.

## Gate A execution log (2026-10-16)

Gate A is **approved for implementation only**. Gate B (merge to main) has
**not** been granted. PR #965 remains Draft.

- Archived full original-byte replay report: Actions run 38664576255,
  Artifact 11940412265, file `microchip-full-reverse.json`, locked byte
  SHA-256 `548c1a61c311bdad1c153565e966c768785f7ecaf28311693bd19c212ae734f0`.
- Source replay attestation in that report: 13 source roots, 313 attested
  original batch archives, 8 quarantined, 23,276 unique source-replayed ICPN
  candidates, 2,563 CFG mapping candidates.
- `microchip_l1_admission_queue_v1.py` checks the pinned original report
  bytes, provider source commit, CFG source blobs, source-linked exact identity
  digests, all unique ICPNs, and the frozen per-CFG distribution. A **read-only
  Research review ledger** of 2,563 rows is emitted by a GitHub CI job.
- `route_evidence_admission.py` defines a reviewed evidence adapter constrained
  to exact canonical identities. `ProgrammingQualificationRegistry` now
  accepts multiple vendor-neutral candidate evidence providers and fails closed
  on overlapping candidate claims. Existing ST candidate registry remains
  the default; the Microchip adapter is **not** populated with unreviewed rows.
- Required next gate: independently review family/base applicability for
  the four static-driver cohorts (2,437 rows); identify a real programming
  path for the 126 target-only rows or preserve their L0 status. Canonical
  Production identity admission and the source-locked registry binding are
  still outstanding.

**Crucial status:** Successfully producing the 2,563-row review ledger is
**not** a completed L1 promotion. Microchip Production remains 122 L0-only,
0 L1-only, 0 L2-only, 0 L3-only until the independent canonical gates pass.
No consumer may use a `PENDING` research ledger row as Product authority.
